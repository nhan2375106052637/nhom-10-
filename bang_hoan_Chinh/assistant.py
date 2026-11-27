"""Trợ lý AI của Kho Vận DSS.

Hai tầng:
1. LocalAssistant  – bộ máy hiểu câu hỏi tiếng Việt (có/không dấu) và tra cứu trực tiếp
   trên kết quả mô hình: tồn kho, đề xuất nhập, What-If, rủi ro giao trễ, Seller, chỉ số mô hình,
   thuật ngữ. Chạy offline, không cần API key.
2. LLM (tuỳ chọn) – nếu có API key (Anthropic Claude hoặc API tương thích OpenAI), câu hỏi
   được ẩn danh PII rồi gửi kèm dữ kiện do LocalAssistant truy xuất để LLM trả lời tự nhiên hơn.
   Lỗi / hết thời gian -> tự quay về câu trả lời nội bộ.
"""
import json, math, os, re, time, unicodedata, urllib.request, urllib.error

# ------------------------------------------------------------------ helpers
def norm(s: str) -> str:
    s = (s or "").lower().replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()

def vn(x, d=0):
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def has(t, *words):
    return any(w in t for w in words)

Z = {0.90: 1.2816, 0.95: 1.6449, 0.975: 1.96, 0.99: 2.3263}
STATUS = {"crit": "Nguy cơ hết hàng", "warn": "Dưới ROP", "ok": "An toàn", "over": "Tồn dư"}
SEV = {"crit": 0, "warn": 1, "over": 2, "ok": 3}

def plan(r, L=1.0, z=1.6449, dm=0.0, stock=None):
    """Chính sách order-up-to: SS = z·σ·√(L+R); ROP = ŷ·L + SS; S = ŷ·(L+R) + SS; Q = max(S − tồn, 0)."""
    stock = r["on_hand_sim"] if stock is None else stock
    R = 1.0
    yhat = r["forecast_week"] * (1 + dm / 100)
    ss = z * r["sigma"] * math.sqrt(L + R)
    rop = yhat * L + ss
    S = yhat * (L + R) + ss
    q = max(S - stock, 0)
    if stock < yhat * L: st = "crit"
    elif stock < rop: st = "warn"
    elif stock > 1.3 * S: st = "over"
    else: st = "ok"
    return {"yhat": yhat, "ss": ss, "rop": rop, "S": S, "q": q, "st": st, "stock": stock,
            "cover": stock / max(yhat, 0.1), "capital": q * r["avg_price"]}

# extra Vietnamese keywords -> category
EXTRA_ALIASES = {
    "bed_bath_table": ["giuong", "chan ga", "khan tam", "bed bath"],
    "health_beauty": ["suc khoe", "lam dep", "my pham"],
    "sports_leisure": ["the thao", "giai tri"],
    "furniture_decor": ["noi that trang tri", "trang tri", "decor"],
    "computers_accessories": ["phu kien may tinh", "may tinh", "computer"],
    "housewares": ["do gia dung", "gia dung"],
    "watches_gifts": ["dong ho", "qua tang"],
    "telephony": ["dien thoai"],
    "garden_tools": ["lam vuon", "dung cu lam vuon"],
    "auto": ["o to", "oto", "xe hoi"],
    "toys": ["do choi"],
    "cool_stuff": ["do doc la", "cool stuff"],
    "perfumery": ["nuoc hoa"],
    "baby": ["me va be", "me & be", "em be", "tre em"],
    "electronics": ["dien tu"],
    "stationery": ["van phong pham"],
    "fashion_bags_accessories": ["tui xach", "phu kien thoi trang", "tui"],
    "pet_shop": ["thu cung", "pet"],
    "office_furniture": ["noi that van phong", "noi that vp"],
    "unknown": ["chua phan loai"],
}

GLOSSARY = {
    "safety stock": ("Safety Stock (tồn kho an toàn – SS)",
        "Lượng hàng dự phòng để chống sai số dự báo và biến động lead time.\n"
        "Công thức trong hệ thống: **SS = z × σ × √(L + R)**, trong đó σ là sai số dự báo của mô hình cho từng danh mục, "
        "z là hệ số theo mức phục vụ (95% → 1,645), L là lead time, R là chu kỳ xem xét (1 tuần).\n"
        "Danh mục càng khó dự báo (σ lớn) thì SS càng lớn."),
    "rop": ("ROP – Điểm đặt hàng lại (Reorder Point)",
        "Mức tồn kho mà khi xuống dưới thì phải đặt hàng: **ROP = ŷ × L + SS** (nhu cầu trong thời gian chờ hàng + tồn an toàn)."),
    "order up to": ("S – Mức tồn tối đa (order-up-to)",
        "Mức tồn mà hệ thống muốn đạt sau khi nhập: **S = ŷ × (L + R) + SS**. Lượng nhập đề xuất **Q = max(S − tồn hiện tại, 0)**."),
    "lead time": ("Lead time (L)",
        "Thời gian từ lúc đặt hàng đến lúc hàng về kho. Mặc định 1 tuần. Lead time dài hơn làm ROP và SS tăng (SS tăng theo √(L+R))."),
    "muc phuc vu": ("Mức phục vụ (service level)",
        "Xác suất không thiếu hàng trong một chu kỳ. 90% → z = 1,282; 95% → 1,645; 97,5% → 1,960; 99% → 2,326. "
        "Từ 95% lên 99% làm Safety Stock tăng khoảng 41%."),
    "wape": ("WAPE (Weighted Absolute Percentage Error)",
        "WAPE = Σ|thực tế − dự báo| / Σ thực tế. Ví dụ thực tế 100 và 200, dự báo 90 và 230 → sai số 40/300 = 13,3%. "
        "Càng thấp càng tốt. Mô hình Gradient Boosting đạt 25,34% theo tuần."),
    "mae": ("MAE", "Sai số tuyệt đối trung bình: trung bình của |thực tế − dự báo|, cùng đơn vị với nhu cầu."),
    "rmse": ("RMSE", "Căn bậc hai của sai số bình phương trung bình; phạt nặng các sai số lớn. Hệ thống dùng RMSE kiểm định làm σ để tính SS."),
    "auc": ("AUC-ROC", "Khả năng mô hình xếp một đơn trễ có điểm cao hơn một đơn đúng hạn. 0,5 = đoán ngẫu nhiên, 1 = hoàn hảo. "
        "Mô hình rủi ro giao trễ đạt khoảng 0,69 – 0,71."),
    "recall": ("Recall (độ nhạy)", "Tỷ lệ đơn trễ thật được mô hình bắt được. Gradient Boosting: 61,4% ở ngưỡng 0,5."),
    "precision": ("Precision (độ chính xác dương)", "Trong các đơn bị cảnh báo, bao nhiêu % trễ thật. Gradient Boosting: 16,7% (khoảng 1/6)."),
    "f1": ("F1-score", "Trung bình điều hoà của Precision và Recall."),
    "shap": ("SHAP (giá trị Shapley)",
        "Phương pháp giải thích mô hình dựa trên lý thuyết trò chơi: chia điểm rủi ro của một đơn cho từng đặc trưng. "
        "Thanh đỏ làm tăng rủi ro, thanh xanh làm giảm. Hệ thống tính chính xác trên 2^11 = 2.048 tổ hợp đặc trưng."),
    "silhouette": ("Silhouette Score", "Đo mức tách biệt giữa các cụm (−1 đến 1). K-Means 4 cụm Seller đạt 0,185 – các cụm chồng lấn một phần."),
    "k means": ("K-Means", "Thuật toán phân cụm: đặt K tâm, gán mỗi Seller vào tâm gần nhất, dời tâm về giữa nhóm, lặp đến khi ổn định. "
        "Dữ liệu được chuẩn hoá StandardScaler trước khi chạy."),
    "naive": ("Naive (mô hình cơ sở)", "Dự báo tuần tới bằng đúng nhu cầu tuần này. Dùng làm mốc so sánh; WAPE 25,87%."),
    "gradient boosting": ("Gradient Boosting", "Tập hợp nhiều cây quyết định nhỏ, cây sau sửa lỗi cây trước. Dùng HistGradientBoosting của scikit-learn."),
    "random forest": ("Random Forest", "Tập hợp nhiều cây quyết định huấn luyện trên các mẫu ngẫu nhiên rồi lấy trung bình."),
    "dss": ("DSS – Hệ hỗ trợ ra quyết định", "Hệ thống cung cấp dữ liệu, dự báo, giải thích, mô phỏng và đề xuất; người quản trị là người quyết định cuối cùng."),
    "what if": ("What-If", "Mô phỏng kịch bản: đổi lead time, mức phục vụ, nhu cầu giả định, tồn kho để xem SS, ROP, lượng nhập và vốn thay đổi ra sao."),
    "stock out": ("Stock-out", "Tình trạng hết hàng, không đáp ứng được nhu cầu → mất doanh thu."),
    "overstock": ("Overstock", "Tồn kho vượt mức cần thiết (trong hệ thống: tồn > 1,3 × S) → đọng vốn, tốn chi phí lưu kho."),
}
GLOSS_ALIASES = {
    "safety stock": ["safety stock", "ton kho an toan", "ton an toan", " ss "],
    "rop": ["rop", "diem dat hang", "reorder"],
    "order up to": ["order up to", "muc ton toi da"],
    "lead time": ["lead time", "leadtime", "thoi gian cho hang"],
    "muc phuc vu": ["muc phuc vu", "service level"],
    "wape": ["wape"], "mae": ["mae"], "rmse": ["rmse"], "auc": ["auc", "roc"],
    "recall": ["recall", "do nhay"], "precision": ["precision"], "f1": ["f1"],
    "shap": ["shap", "shapley"], "silhouette": ["silhouette"], "k means": ["k-means", "kmeans", "k means"],
    "naive": ["naive"], "gradient boosting": ["gradient boosting", "histgb", "xgboost"], "random forest": ["random forest"],
    "dss": ["dss", "he ho tro ra quyet dinh"], "what if": ["what-if", "what if", "whatif"],
    "stock out": ["stock-out", "stockout", "het hang la"], "overstock": ["overstock", "ton du la"],
}

HELP = ("Mình là trợ lý của **Kho Vận DSS**, tra cứu trực tiếp trên kết quả mô hình. Bạn có thể hỏi:\n"
        "- **Tồn kho & nhập hàng:** \"Danh mục nào cần nhập gấp?\", \"Đồ chơi cần nhập bao nhiêu?\", \"Tổng vốn nhập tuần này?\"\n"
        "- **What-If:** \"Nếu lead time 2 tuần, mức phục vụ 99% thì nước hoa nhập bao nhiêu?\"\n"
        "- **Rủi ro giao hàng:** \"Đơn nào rủi ro cao?\", \"Bang nào giao trễ nhiều nhất?\"\n"
        "- **Seller:** \"Seller nào xử lý chậm?\", \"Các cụm Seller là gì?\"\n"
        "- **Mô hình:** \"Mô hình dự báo nào tốt nhất?\", \"AUC là gì?\", \"ROP tính thế nào?\"\n"
        "- **Tổng quan:** \"KPI tổng quan\", \"Tháng nào nhu cầu cao nhất?\"")

SUGGEST = ["Danh mục nào cần nhập gấp?", "Đồ chơi cần nhập bao nhiêu?", "Nếu lead time 2 tuần thì nước hoa nhập bao nhiêu?",
           "Đơn nào rủi ro cao?", "Seller nào xử lý chậm?", "ROP tính thế nào?"]


class LocalAssistant:
    def __init__(self, data):
        self.D = data
        self.reco = {r["category"]: r for r in data["reco"]}
        self.vn = data["vn"]
        self.alias = []  # (normalized alias, category)
        for c in data["top"]:
            names = {norm(c.replace("_", " ")), norm(self.vn.get(c, c)), norm(self.vn.get(c, c).replace("-", " "))}
            names |= {norm(a) for a in EXTRA_ALIASES.get(c, [])}
            for n in names:
                if len(n) >= 3: self.alias.append((n, c))
        self.alias.sort(key=lambda x: -len(x[0]))

    # ---------------------------------------------------------- entity extraction
    def find_cats(self, t):
        found, used = [], t
        for a, c in self.alias:
            if re.search(r"(?<![a-z])" + re.escape(a) + r"(?![a-z])", used) and c not in found:
                found.append(c); used = used.replace(a, " ")
        return found

    def find_order(self, raw):
        for m in re.findall(r"[0-9a-f]{6,32}", raw.lower()):
            for o in self.D["risk"]["orders"]:
                if o["id"].startswith(m[:10]) or m.startswith(o["id"][:len(m)]): return o
        return None

    def find_seller(self, raw):
        for m in re.findall(r"[0-9a-f]{6,32}", raw.lower()):
            for s in self.D["sellers"]:
                if s["id"].startswith(m[:8]) or m.startswith(s["id"]): return s
        return None

    def recos(self):
        rs = [(r, plan(r, z=self.D["z"])) for r in self.D["reco"]]
        rs.sort(key=lambda x: (SEV[x[1]["st"]], -x[1]["q"]))
        return rs

    def C(self, c): return self.vn.get(c, c)

    # ---------------------------------------------------------- answer builders
    def ans_category(self, c):
        r = self.reco[c]; p = plan(r, z=self.D["z"])
        s = self.D["series"][c]
        ae = an = sd = 0
        for k, w in enumerate(s["tweeks"]):
            a = s["demand"][s["weeks"].index(w)]; ae += abs(a - s["gb"][k]); an += abs(a - s["naive"][k]); sd += a
        txt = (f"**{self.C(c)}** – tuần lập kế hoạch 20/08/2018 (mức phục vụ 95%, lead time 1 tuần):\n"
               f"- Nhu cầu dự báo: **{vn(p['yhat'])} đv/tuần** (4 tuần tới ≈ {vn(r['forecast_4w'])} đv); sai số σ = {vn(r['sigma'], 1)}\n"
               f"- Tồn hiện tại (mô phỏng): **{vn(r['on_hand_sim'])}** → đủ bán khoảng {vn(p['cover'], 1)} tuần\n"
               f"- Safety Stock: {vn(p['ss'])} · ROP: {vn(p['rop'])} · Mức tồn tối đa S: {vn(p['S'])}\n"
               f"- **Đề xuất nhập: {vn(p['q'])} đv** (≈ {vn(p['capital'])} BRL theo giá bán TB {vn(r['avg_price'], 2)} BRL)\n"
               f"- Trạng thái: **{STATUS[p['st']]}**\n"
               f"- Độ chính xác trên 15 tuần kiểm thử: WAPE Gradient Boosting {vn(ae / sd * 100, 1)}% so với Naive {vn(an / sd * 100, 1)}%")
        return txt, [{"label": f"Mở What-If: {self.C(c)}", "tab": "whatif", "cat": c},
                     {"label": "Xem biểu đồ dự báo", "tab": "dubao", "cat": c}]

    def ans_list(self, which):
        rs = self.recos()
        if which == "urgent":
            sel = [x for x in rs if x[1]["st"] in ("crit", "warn")]
            head = f"Có **{sum(1 for x in sel if x[1]['st']=='crit')} danh mục nguy cơ hết hàng** và **{sum(1 for x in sel if x[1]['st']=='warn')} danh mục dưới ROP** (trên {len(rs)} danh mục):"
            sel = sel[:10]
        elif which == "ok":
            sel = [x for x in rs if x[1]["st"] in ("ok", "over")]
            head = f"Có {len(sel)} danh mục đang an toàn hoặc tồn dư:" if sel else "Không có danh mục nào ở trạng thái an toàn."
        else:
            sel = rs[:10]; head = "Top 10 danh mục theo mức độ ưu tiên nhập hàng:"
        lines = [f"- **{self.C(r['category'])}**: tồn {vn(r['on_hand_sim'])}, ROP {vn(p['rop'])} → nhập **{vn(p['q'])}** đv ({STATUS[p['st']]})" for r, p in sel]
        tot = sum(p["q"] for _, p in rs); cap = sum(p["capital"] for _, p in rs)
        tail = f"\nTổng lượng nhập đề xuất cho 20 danh mục: **{vn(tot)} đv**, vốn ước tính **{vn(cap / 1000, 1)} nghìn BRL**."
        return head + "\n" + "\n".join(lines) + tail, [{"label": "Mở bảng đề xuất nhập hàng", "tab": "dubao"}]

    def ans_totals(self):
        rs = self.recos(); tot = sum(p["q"] for _, p in rs); cap = sum(p["capital"] for _, p in rs)
        big = sorted(rs, key=lambda x: -x[1]["capital"])[:3]
        return (f"Tuần 20/08/2018, tổng lượng nhập đề xuất là **{vn(tot)} đơn vị**, vốn ước tính **{vn(cap / 1000, 1)} nghìn BRL** (theo giá bán bình quân).\n"
                f"Ba danh mục cần nhiều vốn nhất: " + ", ".join(f"{self.C(r['category'])} ({vn(p['capital'] / 1000, 1)} nghìn BRL)" for r, p in big) + "."), \
               [{"label": "Mở bảng đề xuất", "tab": "dubao"}]

    def ans_whatif(self, raw, t, cats):
        c = cats[0] if cats else self.recos()[0][0]["category"]
        r = self.reco[c]
        L = 1.0; sl = 0.95; dm = 0.0; stock = r["on_hand_sim"]
        m = re.search(r"(?:lead ?time|thoi gian cho)[^\d]{0,12}(\d+(?:[.,]\d+)?)", t) or re.search(r"(\d+(?:[.,]\d+)?)\s*tuan", t)
        if m: L = min(max(float(m.group(1).replace(",", ".")), 0.5), 8)
        m = re.search(r"(?:muc phuc vu|service level|phuc vu)[^\d]{0,10}(\d{2}(?:[.,]\d)?)", t)
        if m: sl = float(m.group(1).replace(",", ".")) / 100
        m = re.search(r"(tang|giam|\+|-)\s*(\d+(?:[.,]\d+)?)\s*%", t)
        if m: dm = float(m.group(2).replace(",", ".")) * (-1 if m.group(1) in ("giam", "-") else 1)
        m = re.search(r"ton(?: kho)?(?: hien tai| con| la| =)?\s*(\d+)", t)
        if m: stock = float(m.group(1))
        sl = min(Z, key=lambda k: abs(k - sl))
        b = plan(r, z=self.D["z"]); s = plan(r, L=L, z=Z[sl], dm=dm, stock=stock)
        rows = [("Nhu cầu/tuần", b["yhat"], s["yhat"]), ("Tồn kho", b["stock"], s["stock"]), ("Safety Stock", b["ss"], s["ss"]),
                ("ROP", b["rop"], s["rop"]), ("Mức tồn tối đa S", b["S"], s["S"]), ("Lượng nhập", b["q"], s["q"]), ("Vốn (BRL)", b["capital"], s["capital"])]
        txt = (f"Kịch bản cho **{self.C(c)}**: lead time **{vn(L, 1)} tuần**, mức phục vụ **{vn(sl * 100, 1)}%**, nhu cầu **{'+' if dm >= 0 else ''}{vn(dm)}%**, tồn **{vn(stock)}**.\n"
               + "\n".join(f"- {k}: {vn(a)} → **{vn(c2)}**" for k, a, c2 in rows)
               + f"\n- Trạng thái: {STATUS[b['st']]} → **{STATUS[s['st']]}**")
        if L != 1: txt += f"\nRiêng lead time {vn(L, 1)} tuần làm SS thay đổi {vn((math.sqrt((L + 1) / 2) - 1) * 100)}% so với 1 tuần."
        return txt, [{"label": "Mở What-If với kịch bản này", "tab": "whatif", "cat": c, "L": L, "sl": sl, "dm": dm, "stock": stock}]

    def shap_text(self, o, k=3):
        labs = self.D["risk"]["labels"]
        idx = sorted(range(len(o["phi"])), key=lambda i: -abs(o["phi"][i]))[:k]
        return "\n".join(f"- {labs[i]} = {vn(o['x'][i], 2) if abs(o['x'][i]) < 10 else vn(o['x'][i])}: {'tăng' if o['phi'][i] > 0 else 'giảm'} rủi ro ({'+' if o['phi'][i] > 0 else ''}{vn(o['phi'][i], 2)})" for i in idx)

    def ans_order(self, o):
        pb = 1 / (1 + math.exp(-o["base"])); pf = 1 / (1 + math.exp(-(o["base"] + sum(o["phi"]))))
        txt = (f"Đơn **{o['id']}…** ({o['date']}, {o['cat'].replace('_', ' ')}, tuyến {o['sstate']} → {o['cstate']}): điểm rủi ro trễ **{vn(o['risk'] * 100, 1)}%** "
               f"(mức nền {vn(pb * 100, 1)}%).\nBa yếu tố ảnh hưởng mạnh nhất (SHAP):\n{self.shap_text(o)}\n"
               f"Thực tế: {'giao trễ ' + vn(o['delay'], 1) + ' ngày' if o['late'] else 'giao đúng hạn'} – điểm rủi ro là xác suất, không phải kết luận.")
        return txt, [{"label": "Xem SHAP của đơn này", "tab": "ruiro", "order": o["id"]}]

    def ans_risk(self, t):
        R = self.D["risk"]; M = R["metrics"]["Gradient Boosting (HistGB)"]
        if has(t, "bang", "khu vuc", "dia phuong", "tinh"):
            st = self.D["state"]
            top = "\n".join(f"- **{s}**: {vn(r, 1)}% ({vn(n)} đơn)" for s, r, n in list(zip(st["s"], st["rate"], st["n"]))[:6])
            low = ", ".join(f"{s} ({vn(r, 1)}%)" for s, r in list(zip(st["s"], st["rate"]))[-3:])
            return f"Các bang có tỷ lệ giao trễ cao nhất (trung bình toàn sàn ≈ 8,1%):\n{top}\nThấp nhất: {low}.", [{"label": "Mở phân hệ Rủi ro", "tab": "ruiro"}]
        os_ = R["orders"][:5]
        lines = "\n".join(f"- **{o['id']}…** {o['date']} · {o['sstate']} → {o['cstate']} · {o['cat'].replace('_', ' ')}: **{vn(o['risk'] * 100, 1)}%**" for o in os_)
        return (f"Mô hình Gradient Boosting chấm điểm rủi ro ngay khi đặt hàng (AUC {vn(M['AUC'], 3)}, Recall {vn(M['Recall'] * 100, 1)}%). "
                f"Kiểm tra 20% đơn rủi ro nhất phát hiện {vn(R['lift']['top20%'], 1)}% đơn trễ.\nĐơn rủi ro cao gần đây (07–08/2018):\n{lines}\n"
                f"Hỏi \"đơn {os_[0]['id']}\" để xem lý do chi tiết."), [{"label": "Mở phân hệ Rủi ro", "tab": "ruiro"}]

    def ans_seller(self, t, s=None):
        CL = self.D["clusters"]; P = {p["cluster"]: p for p in self.D["profile"]}
        if s:
            return (f"Seller **{s['id']}…** (bang {s['st']}) thuộc cụm **{CL[str(s['c'])]}**:\n- {vn(s['n'])} đơn, chuẩn bị hàng {vn(s['prep'], 1)} ngày\n"
                    f"- Giao trễ {vn(s['late'] * 100, 1)}%, bàn giao quá hạn {vn(s['lh'] * 100, 1)}%, hủy {vn(s['canc'] * 100, 1)}%\n- Review trung bình {vn(s['review'], 2)}"), [{"label": "Mở Seller Intelligence", "tab": "seller"}]
        if has(t, "cham", "tre", "slow"):
            W = sorted([x for x in self.D["sellers"] if x["c"] == 0], key=lambda x: -x["late"])[:6]
            p = P[0]
            return (f"Cụm **Slow Seller (Chậm xử lý)** có {p['n_sellers']} Seller: chuẩn bị hàng TB {vn(p['prep_days'], 2)} ngày, "
                    f"{vn(p['late_handover'] * 100, 1)}% bàn giao quá hạn, giao trễ {vn(p['late_rate'] * 100, 1)}%. Trễ nhiều nhất:\n"
                    + "\n".join(f"- {x['id']}… ({x['st']}): trễ {vn(x['late'] * 100, 1)}%, chuẩn bị {vn(x['prep'], 1)} ngày, review {vn(x['review'], 2)}" for x in W)
                    + "\nĐề xuất: đặt mục tiêu bàn giao ≤ 2 ngày, giảm ưu tiên khi hàng khan hiếm."), [{"label": "Mở danh sách theo dõi", "tab": "seller"}]
        if has(t, "huy", "cancel"):
            W = sorted([x for x in self.D["sellers"] if x["c"] == 2], key=lambda x: -x["canc"])[:6]
            p = P[2]
            return (f"Cụm **Risky Seller (Hay hủy đơn)** có {p['n_sellers']} Seller, tỷ lệ hủy TB {vn(p['cancel_rate'] * 100, 2)}%. Hủy nhiều nhất:\n"
                    + "\n".join(f"- {x['id']}… ({x['st']}): hủy {vn(x['canc'] * 100, 1)}%, {vn(x['n'])} đơn" for x in W)
                    + "\nĐề xuất: yêu cầu cập nhật tồn kho đăng bán; hạn chế nếu hủy > 5%."), [{"label": "Mở Seller Intelligence", "tab": "seller"}]
        lines = []
        for c in [1, 3, 0, 2]:
            p = P[c]
            lines.append(f"- **{CL[str(c)]}** – {p['n_sellers']} Seller: chuẩn bị {vn(p['prep_days'], 2)} ngày, trễ {vn(p['late_rate'] * 100, 1)}%, hủy {vn(p['cancel_rate'] * 100, 2)}%, review {vn(p['avg_review'], 2)}")
        return ("818 Seller (≥ 20 đơn) được K-Means chia 4 cụm (Silhouette 0,185):\n" + "\n".join(lines)), [{"label": "Mở Seller Intelligence", "tab": "seller"}]

    def ans_models(self):
        fm = self.D["fc_metrics"]; rm = self.D["risk"]["metrics"]; pol = self.D["policy"]; pn = list(pol)
        a = "\n".join(f"- {k}: WAPE **{vn(v['WAPE'], 2)}%**, RMSE {vn(v['RMSE'], 2)}" for k, v in fm.items())
        b = "\n".join(f"- {k}: AUC **{vn(v['AUC'], 3)}**, Recall {vn(v['Recall'] * 100, 1)}%, Precision {vn(v['Precision'] * 100, 1)}%" for k, v in rm.items())
        return (f"**Dự báo nhu cầu theo tuần** (15 tuần × 20 danh mục):\n{a}\n→ Gradient Boosting tốt nhất, hơn Naive khoảng 2%.\n\n"
                f"**Rủi ro giao trễ** (51.607 đơn 2018):\n{b}\n\n"
                f"**Chính sách tồn kho (mô phỏng):** số tuần thiếu hàng {pol[pn[0]]['stockout_weeks']} → {pol[pn[2]]['stockout_weeks']}, "
                f"nhu cầu không đáp ứng {vn(100 - pol[pn[0]]['fill_rate'], 2)}% → {vn(100 - pol[pn[2]]['fill_rate'], 2)}%."), [{"label": "Mở so sánh mô hình", "tab": "dubao"}]

    def ans_overview(self):
        m = self.D["monthly"]; n = len(m["ym"]); mom = (m["demand"][-1] / m["demand"][-2] - 1) * 100
        rs = self.recos(); nc = sum(1 for _, p in rs if p["st"] == "crit"); nw = sum(1 for _, p in rs if p["st"] == "warn")
        late18 = sum(m["late"][12:]) / len(m["late"][12:])
        return (f"**Tổng quan 01/2017 – 08/2018:**\n- {vn(sum(m['orders']))} đơn đã giao, giá trị giao dịch {vn(sum(m['value']) / 1e6, 2)} triệu BRL\n"
                f"- Nhu cầu tháng 08/2018: {vn(m['demand'][-1])} dòng SP ({'+' if mom >= 0 else ''}{vn(mom, 1)}% so với tháng trước)\n"
                f"- Cảnh báo tồn kho: {nc} nguy cơ hết hàng, {nw} dưới ROP\n- Tỷ lệ giao trễ TB 2018: {vn(late18, 1)}%\n"
                f"- Seller cần theo dõi: {sum(1 for s in self.D['sellers'] if s['c'] in (0, 2))}"), [{"label": "Mở Tổng quan", "tab": "tongquan"}]

    def ans_trend(self):
        m = self.D["monthly"]; i = max(range(len(m["demand"])), key=lambda k: m["demand"][k]); j = min(range(len(m["demand"])), key=lambda k: m["demand"][k])
        k = max(range(len(m["late"])), key=lambda q: m["late"][q])
        return (f"- Nhu cầu cao nhất: **{m['ym'][i]}** với {vn(m['demand'][i])} dòng SP (Black Friday); thấp nhất {m['ym'][j]} ({vn(m['demand'][j])}).\n"
                f"- Năm 2017 tăng nhanh, năm 2018 đi ngang ở mức 7–8 nghìn dòng/tháng.\n- Tỷ lệ giao trễ cao nhất: **{m['ym'][k]}** ({vn(m['late'][k], 1)}%)."), [{"label": "Mở Tổng quan", "tab": "tongquan"}]

    def ans_glossary(self, keys):
        out = []
        for k in keys[:2]:
            title, body = GLOSSARY[k]; out.append(f"**{title}**\n{body}")
        return "\n\n".join(out), []

    # ---------------------------------------------------------- router
    def answer(self, raw):
        t = " " + norm(raw) + " "
        cats = self.find_cats(t)
        gl = [k for k, al in GLOSS_ALIASES.items() if any(a in t for a in al)]
        asks_def = has(t, " la gi", "nghia la", "giai thich", "khai niem", "dinh nghia", "cong thuc", "tinh the nao", "tinh nhu the nao", "y nghia", "what is")
        if not t.strip() or has(t, "xin chao", "hello", " hi ", "chao ban", "giup toi", "huong dan", "ban lam duoc gi", "ban co the", " help "):
            return HELP, [], "help"
        if gl and (asks_def or not (cats or has(t, "don ", "seller"))):
            if not has(t, " neu ", "gia su", "kich ban") or asks_def:
                a, act = self.ans_glossary(gl); return a, act, "glossary"
        o = self.find_order(raw)
        if o and not self.find_seller(raw) or (o and has(t, "don")):
            a, act = self.ans_order(o); return a, act, "order"
        s = self.find_seller(raw)
        if s:
            a, act = self.ans_seller(t, s); return a, act, "seller"
        if has(t, " neu ", "gia su", "kich ban", "what if", "what-if", "whatif") or (cats and has(t, "lead time", "muc phuc vu", "tang ", "giam ")):
            a, act = self.ans_whatif(raw, t, cats); return a, act, "whatif"
        if cats:
            if len(cats) > 1:
                parts = []
                for c in cats[:4]:
                    r = self.reco[c]; p = plan(r, z=self.D["z"])
                    parts.append(f"- **{self.C(c)}**: dự báo {vn(p['yhat'])}/tuần (σ {vn(r['sigma'], 1)}), tồn {vn(r['on_hand_sim'])}, SS {vn(p['ss'])}, ROP {vn(p['rop'])}, "
                                 f"nhập **{vn(p['q'])}** đv ≈ {vn(p['capital'])} BRL – {STATUS[p['st']]}")
                return "So sánh các danh mục (tuần 20/08/2018, mức phục vụ 95%):\n" + "\n".join(parts), [{"label": f"Mở What-If: {self.C(c)}", "tab": "whatif", "cat": c} for c in cats[:3]], "category"
            a, act = self.ans_category(cats[0]); return a, act, "category"
        if has(t, "tong", "bao nhieu tien", "von") and has(t, "nhap", "von"):
            a, act = self.ans_totals(); return a, act, "totals"
        if has(t, "nhap gap", "het hang", "canh bao ton", "duoi rop", "can nhap", "danh sach nhap", "nen nhap", "uu tien nhap", "stock out", "stock-out", "thieu hang", "nhap hang"):
            a, act = self.ans_list("urgent"); return a, act, "list"
        if has(t, "an toan", "ton du", "overstock", "du hang"):
            a, act = self.ans_list("ok"); return a, act, "list"
        if has(t, "rui ro", "giao tre", "don tre", "tre hang", "giao cham", "van chuyen"):
            a, act = self.ans_risk(t); return a, act, "risk"
        if has(t, "seller", "nha ban", "nguoi ban", "doi tac", "cum"):
            a, act = self.ans_seller(t); return a, act, "seller"
        if has(t, "mo hinh", "do chinh xac", "tot nhat", "so sanh", "auc", "wape", "danh gia"):
            a, act = self.ans_models(); return a, act, "models"
        if has(t, "xu huong", "thang nao", "black friday", "cao nhat", "mua vu", "theo thang"):
            a, act = self.ans_trend(); return a, act, "trend"
        if has(t, "tong quan", "kpi", "doanh thu", "gia tri giao dich", "bao nhieu don", "nhu cau", "tinh hinh", "bao cao"):
            a, act = self.ans_overview(); return a, act, "overview"
        if gl:
            a, act = self.ans_glossary(gl); return a, act, "glossary"
        return ("Mình chưa chắc bạn muốn tra cứu gì. " + HELP), [], "unknown"

    def context_summary(self):
        """Ngữ cảnh gọn cho LLM (không có dữ liệu cá nhân)."""
        rs = self.recos()
        tbl = "\n".join(f"{self.C(r['category'])}: dự báo {vn(p['yhat'])}/tuần, tồn {vn(r['on_hand_sim'])}, SS {vn(p['ss'])}, ROP {vn(p['rop'])}, nhập {vn(p['q'])}, {STATUS[p['st']]}" for r, p in rs)
        return (self.ans_overview()[0] + "\n\nĐề xuất nhập hàng tuần 20/08/2018 (mức phục vụ 95%, L=1 tuần, R=1 tuần):\n" + tbl
                + "\n\n" + self.ans_models()[0] + "\n\n" + self.ans_seller("")[0])


# ------------------------------------------------------------------ privacy
PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?84|0)\d{9,10}(?!\d)"), "[PHONE]"),
    (re.compile(r"\b[0-9a-f]{32}\b"), "[HASHED_ID]"),
    (re.compile(r"\b\d{9,12}\b"), "[ID_NUMBER]"),
]
def mask_pii(text):
    found = 0
    for pat, rep in PII_PATTERNS:
        text, n = pat.subn(rep, text); found += n
    return text, found


# ------------------------------------------------------------------ LLM
SYSTEM_PROMPT = """Bạn là trợ lý AI của "Kho Vận DSS" – hệ hỗ trợ ra quyết định dự báo nhu cầu và tối ưu tồn kho (đồ án Nhóm 10, dữ liệu Olist Brazil 01/2017–08/2018).
Quy tắc:
- Trả lời bằng tiếng Việt, ngắn gọn, rõ ràng; dùng gạch đầu dòng khi liệt kê; in đậm bằng **...**.
- CHỈ dùng số liệu trong phần DỮ KIỆN và NGỮ CẢNH bên dưới. Không bịa số. Nếu không có dữ liệu, nói rõ là hệ thống chưa có.
- Tồn kho hiện tại là số mô phỏng (Olist không có dữ liệu tồn kho). Tiền tệ là BRL.
- Bạn chỉ đề xuất; quyết định cuối cùng thuộc về nhà quản trị.
- Có thể giải thích khái niệm (Safety Stock, ROP, WAPE, AUC, SHAP, K-Means...) bằng kiến thức chung."""

class LLMClient:
    def __init__(self):
        self.provider = None
        if os.getenv("ANTHROPIC_API_KEY"):
            self.provider = "anthropic"; self.key = os.getenv("ANTHROPIC_API_KEY")
            self.model = os.getenv("LLM_MODEL", "claude-haiku-5-5")
        elif os.getenv("OPENAI_API_KEY"):
            self.provider = "openai"; self.key = os.getenv("OPENAI_API_KEY")
            self.base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout = float(os.getenv("LLM_TIMEOUT", "25"))

    @property
    def label(self):
        if self.provider == "anthropic": return f"Claude ({self.model})"
        if self.provider == "openai": return f"LLM ({self.model})"
        return "Trợ lý nội bộ (offline)"

    def chat(self, system, history, user):
        msgs = [m for m in history if m.get("role") in ("user", "assistant") and m.get("content")][-8:] + [{"role": "user", "content": user}]
        if self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            body = {"model": self.model, "max_tokens": 900, "system": system, "messages": msgs}
            headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        else:
            url = self.base + "/chat/completions"
            body = {"model": self.model, "max_tokens": 900, "messages": [{"role": "system", "content": system}] + msgs}
            headers = {"Authorization": "Bearer " + self.key, "content-type": "application/json"}
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            d = json.loads(r.read().decode())
        if self.provider == "anthropic":
            return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()
        return d["choices"][0]["message"]["content"].strip()


class Assistant:
    def __init__(self, data, audit_path):
        self.local = LocalAssistant(data)
        self.llm = LLMClient()
        self.audit_path = audit_path
        self.ctx = self.local.context_summary()

    def status(self):
        return {"mode": "llm" if self.llm.provider else "local", "label": self.llm.label, "suggestions": SUGGEST}

    def audit(self, rec):
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def ask(self, question, history=None):
        t0 = time.time()
        question = (question or "").strip()[:1000]
        local_ans, actions, intent = self.local.answer(question)
        result = {"answer": local_ans, "actions": actions, "source": "local", "intent": intent}
        masked, n_pii = mask_pii(question)
        if self.llm.provider:
            try:
                hist = [{"role": m.get("role"), "content": mask_pii(str(m.get("content", "")))[0]} for m in (history or [])]
                system = SYSTEM_PROMPT + "\n\nNGỮ CẢNH CHUNG:\n" + self.ctx
                user = f"DỮ KIỆN TRA CỨU ĐƯỢC CHO CÂU HỎI NÀY (ưu tiên dùng):\n{local_ans}\n\nCÂU HỎI: {masked}"
                text = self.llm.chat(system, hist, user)
                if text:
                    result.update(answer=text, source="llm")
            except urllib.error.HTTPError as e:
                why = {401: "API key không hợp lệ", 403: "API key không có quyền", 404: "sai tên model", 429: "vượt giới hạn gọi API"}.get(e.code, f"HTTP {e.code}")
                result["note"] = f"LLM lỗi ({why}), dùng câu trả lời nội bộ."
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as e:
                result["note"] = f"Không kết nối được LLM ({type(e).__name__}), dùng câu trả lời nội bộ."
        self.audit({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "intent": intent, "source": result["source"],
                    "pii_masked": n_pii, "question": masked, "ms": int((time.time() - t0) * 1000)})
        return result
