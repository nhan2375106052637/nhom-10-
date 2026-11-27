"""Tầng dịch vụ: đọc kết quả đã huấn luyện, tính các số cho Dashboard và công cụ của tác tử AI."""
import math
import re
import unicodedata
import warnings

import joblib
import numpy as np
import pandas as pd

import agents as A
import config as C
import engine as E
from train import RISK_FEATURES

warnings.filterwarnings("ignore", message="X does not have valid feature names")
vn = A.vn
B = None
FEATURE_VI = {"promised_days": "Số ngày giao đã hứa", "distance_km": "Khoảng cách Seller – KH (km)", "freight": "Phí vận chuyển (đ)",
              "price": "Giá trị hàng (đ)", "freight_ratio": "Tỷ lệ phí ship / giá", "weight": "Tổng khối lượng (g)", "n_items": "Số sản phẩm",
              "same_state": "Cùng bang", "limit_days": "Hạn Seller bàn giao (ngày)", "state_late_rate": "Tỷ lệ trễ lịch sử bang KH",
              "day_of_week": "Thứ đặt hàng"}
FC_VI = {"r1": "Nhu cầu 1 tuần trước", "r2": "2 tuần trước", "r3": "3 tuần trước", "r4": "4 tuần trước", "r5": "5 tuần trước",
         "r6": "6 tuần trước", "r7": "7 tuần trước", "r8": "8 tuần trước", "r_rm8": "Xu hướng 8/4 tuần", "cv4": "Biến động 4 tuần",
         "woy": "Tuần trong năm", "pchg": "Thay đổi giá", "logscale": "Quy mô danh mục"}
DAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def load():
    global B
    if B is None:
        B = joblib.load(C.ARTIFACT_DIR / "bundle.joblib")
    return B


def clean(x):
    if isinstance(x, dict): return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [clean(v) for v in x]
    if isinstance(x, np.integer): return int(x)
    if isinstance(x, (float, np.floating)): return None if math.isnan(x) or math.isinf(x) else round(float(x), 4)
    if isinstance(x, np.bool_): return bool(x)
    if isinstance(x, pd.Timestamp): return str(x)
    return x


def _norm(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


# ---------------- Tổng quan & cảnh báo ----------------
def plan():
    return load()["forecast"]["plan"]


def watchlist():
    t = load()["seller"]["table"]
    return t[t["group"].isin(["Slow", "Risky"])].sort_values("late_rate", ascending=False)


def summary():
    """Bộ số gọn cho Narrator, báo cáo tuần và trợ lý."""
    b = load()
    p = plan()
    r = b["risk"]["recent"]
    cnt = pd.Series([x["status"] for x in p]).value_counts()
    return clean({"week": b["forecast"]["next_week"], "stockout": int(cnt.get(E.STATUS[0], 0)), "below_rop": int(cnt.get(E.STATUS[1], 0)),
                  "overstock": int(cnt.get(E.STATUS[2], 0)), "safe": int(cnt.get(E.STATUS[3], 0)),
                  "total_q": round(sum(x["q"] for x in p)), "capital": round(sum(x["q"] * x["price"] for x in p)),
                  "late_2018": round(b["overview"]["late_2018"] * 100, 1), "high_risk_orders": int((r["risk"] >= C.RISK_ALERT).sum()),
                  "watch_sellers": int(len(watchlist()))})


def overview():
    b = load()
    o, p, s = b["overview"], plan(), summary()
    dm = o["demand_month"]
    last, prev = dm[-1], dm[-2]
    kpis = [{"label": "Đơn đã giao", "value": vn(o["delivered"], 0), "note": f"trong {o['months']} tháng"},
            {"label": "Giá trị giao dịch", "value": vn(o["gmv"] / 1e9, 2) + " tỷ đ", "note": "giá + phí vận chuyển"},
            {"label": f"Nhu cầu {last['month']}", "value": vn(last["value"], 0), "note": f"{'+' if last['value'] >= prev['value'] else ''}{vn((last['value'] / prev['value'] - 1) * 100)}% so với tháng trước"},
            {"label": "Danh mục có cảnh báo", "value": f"{len(p) - s['safe']}/{len(p)}", "note": f"{s['stockout']} nguy cơ hết hàng", "alert": s["stockout"] > 0},
            {"label": "Tỷ lệ giao trễ 2018", "value": vn(o["late_2018"] * 100) + "%", "note": f"{s['high_risk_orders']} đơn rủi ro ≥ {int(C.RISK_ALERT * 100)}%"},
            {"label": "Nhà bán hàng cần theo dõi", "value": str(s["watch_sellers"]), "note": "nhóm chậm xử lý và hay hủy đơn"}]
    alerts = []
    sev = {E.STATUS[0]: 0, E.STATUS[1]: 2, E.STATUS[2]: 3}
    for x in p:
        if x["status"] in sev:
            alerts.append({"sev": sev[x["status"]], "kind": "Tồn kho", "status": x["status"], "title": x["name"],
                           "detail": f"Tồn {vn(x['stock'], 0)} · ROP {vn(x['rop'], 0)} · đề xuất nhập {vn(x['q'], 0)}", "link": f"/what-if?cat={x['category']}"})
    r = b["risk"]["recent"]
    for _, x in r[r["risk"] >= C.RISK_ALERT].head(8).iterrows():
        alerts.append({"sev": 1, "kind": "Giao hàng", "status": "Rủi ro cao", "title": f"Đơn {x['order_id'][:8]} · {x['seller_state']} → {x['customer_state']}",
                       "detail": f"Điểm rủi ro {vn(x['risk'] * 100)}%", "link": f"/rui-ro?order={x['order_id'][:8]}"})
    t = b["seller"]["table"]
    for _, x in t[t["cancel_rate"] > C.CANCEL_LIMIT].sort_values("cancel_rate", ascending=False).head(6).iterrows():
        alerts.append({"sev": 1, "kind": "Seller", "status": "Hay hủy đơn", "title": f"Nhà bán hàng {x['short_id']}",
                       "detail": f"Tỷ lệ hủy {vn(x['cancel_rate'] * 100)}% (ngưỡng {int(C.CANCEL_LIMIT * 100)}%)", "link": f"/seller?id={x['short_id']}"})
    alerts.sort(key=lambda a: a["sev"])
    return clean({"kpis": kpis, "alerts": alerts, "demand": dm, "late": o["late_month"], "review": o["review_delay"],
                  "week": b["forecast"]["next_week"], "summary": s})


# ---------------- Dự báo & nhập hàng ----------------
def forecast(cat=None):
    f = load()["forecast"]
    cats = [x["category"] for x in f["plan"]]
    cat = cat if cat in f["series"] else cats[0]
    s = f["series"][cat]
    p = next(x for x in f["plan"] if x["category"] == cat)
    return clean({"cat": cat, "categories": [{"id": x["category"], "name": x["name"]} for x in f["plan"]], "series": s, "next": p["yhat"],
                  "plan": f["plan"], "table": f["table"], "better": f["by_cat_better"], "n_cat": f["n_cat"], "split": f["split"],
                  "importance": sorted([{"label": FC_VI[k], "value": v} for k, v in f["importance"].items()], key=lambda z: -z["value"]),
                  "sim": f["sim"], "trace": f["traces"][cat], "week": f["next_week"], "name": p["name"]})


def whatif_calc(cat, lead, service, demand_pct, stock=None):
    p = next(x for x in plan() if x["category"] == cat)
    st = p["stock"] if stock is None else stock
    yh = p["yhat"] * (1 + demand_pct / 100)
    inv = E.inventory(yh, p["sigma"], st, service=service, lead=lead)
    return {**p, "yhat": yh, "stock": st, **inv, "capital": inv["q"] * p["price"], "lead": lead, "service_pct": service * 100, "demand_pct": demand_pct}


def purchase_note(cat, lead, service, demand_pct, stock):
    x = whatif_calc(cat, lead, service, demand_pct, stock)
    facts = {k: round(float(x[k]), 1) for k in ("yhat", "sigma", "stock", "ss", "rop", "s", "q", "capital", "lead", "service_pct", "demand_pct")}
    return clean(A.purchase_note({"name": x["name"], "status": x["status"], **facts}))


# ---------------- Rủi ro giao hàng ----------------
def risk_page():
    r = load()["risk"]
    rec = r["recent"].head(60)
    rows = [{"id": x["order_id"], "short": x["order_id"][:8], "route": f"{x['seller_state']} → {x['customer_state']}",
             "risk": float(x["risk"]), "actual": "Trễ" if x["is_late"] else "Đúng hạn"} for _, x in rec.iterrows()]
    return clean({"orders": rows, "table": r["table"], "gain": r["gain"], "gain_curve": r["gain_curve"], "split": r["split"],
                  "importance": sorted([{"label": FEATURE_VI[k], "value": v} for k, v in r["importance"].items()], key=lambda z: -z["value"]),
                  "n_high": int((r["recent"]["risk"] >= C.RISK_ALERT).sum()), "n_recent": len(r["recent"])})


def _order(oid):
    rec = load()["risk"]["recent"]
    hit = rec[rec["order_id"].str.startswith(str(oid))]
    if hit.empty:
        raise KeyError("Không tìm thấy đơn trong danh sách tháng 7–8/2018")
    return hit.iloc[0]


def _show(f, v):
    if f == "same_state": return "Có" if v else "Không"
    if f == "day_of_week": return DAYS[int(v) % 7]
    if f in ("state_late_rate", "freight_ratio"): return vn(v * 100) + "%"
    if f in ("n_items",): return str(int(v))
    return vn(v, 1)


def order_detail(oid):
    r = load()["risk"]
    x = _order(oid)
    vals = np.array([float(x[f]) for f in RISK_FEATURES])
    pred = lambda a: r["model"].decision_function(pd.DataFrame(a, columns=RISK_FEATURES))
    base, phi = E.exact_shap(pred, vals, r["background"])
    rows = sorted([{"feature": f, "label": FEATURE_VI[f], "value": _show(f, vals[i]), "log_odds": float(phi[i])} for i, f in enumerate(RISK_FEATURES)],
                  key=lambda z: -abs(z["log_odds"]))
    total = base + phi.sum()
    return clean({"id": x["order_id"], "short": x["order_id"][:8], "route": f"{x['seller_state']} → {x['customer_state']}", "risk": float(x["risk"]),
                  "base": base, "base_prob": 1 / (1 + math.exp(-base)), "total": total, "shap": rows, "actions": E.risk_actions(rows),
                  "actual": "Trễ" if x["is_late"] else "Đúng hạn", "seller": x["seller_id"][:8]})


def explain(oid):
    d = order_detail(oid)
    facts = {"risk_pct": round(d["risk"] * 100, 1), "route": d["route"], "base_prob_pct": round(d["base_prob"] * 100, 1),
             "shap": [{"label": z["label"], "value": z["value"], "log_odds": round(z["log_odds"], 2)} for z in d["shap"][:5]],
             "actions": d["actions"]}
    return clean(A.explain_order(facts))


# ---------------- Seller ----------------
def seller_page():
    s = load()["seller"]
    t = s["table"]
    groups = []
    for g in ["Star", "Premium", "Slow", "Risky"]:
        x = t[t["group"] == g]
        groups.append({"id": g, "name": E.SELLER_NAME[g], "policy": E.SELLER_POLICY[g], "n": len(x), "orders": float(x["orders"].median()),
                       "prep": float(x["prep_median"].mean()), "handoff": float(x["handoff_late"].mean()), "late": float(x["late_rate"].mean()),
                       "cancel": float(x["cancel_rate"].mean()), "review": float(x["avg_review"].mean()), "price": float(x["avg_price"].mean())})
    pts = [{"x": float(r["pc1"]), "y": float(r["pc2"]), "label": f"{r['short_id']} ({r['group']})", "id": r["short_id"], "g": r["group"]} for _, r in t.iterrows()]
    w = [_seller_row(r) for _, r in watchlist().iterrows()]
    return clean({"groups": groups, "points": pts, "watch": w, "curve": s["curve"], "silhouette": s["silhouette"], "pca_var": s["pca_var"], "n": len(t)})


def _seller_row(r):
    return {"id": r["short_id"], "group": r["group"], "orders": int(r["orders"]), "prep": float(r["prep_median"]), "handoff": float(r["handoff_late"]),
            "late": float(r["late_rate"]), "cancel": float(r["cancel_rate"]), "review": float(r["avg_review"]), "state": r["state"]}


def seller_detail(sid):
    t = load()["seller"]["table"]
    hit = t[t["short_id"] == sid]
    if hit.empty:
        raise KeyError("Không tìm thấy Seller")
    r = hit.iloc[0]
    return clean({**_seller_row(r), "name": E.SELLER_NAME[r["group"]], "policy": E.SELLER_POLICY[r["group"]], "restrict": bool(r["cancel_rate"] > C.CANCEL_LIMIT)})


def seller_note(sid):
    d = seller_detail(sid)
    return clean(A.seller_note({"short_id": d["id"], "group": d["name"], "orders": d["orders"], "prep_days": round(d["prep"], 1),
                                "handoff_late_pct": round(d["handoff"] * 100, 1), "late_pct": round(d["late"] * 100, 1),
                                "cancel_pct": round(d["cancel"] * 100, 1), "avg_review": round(d["review"], 2)}))


# ---------------- Báo cáo khuyến nghị ----------------
def report_facts():
    b = load()
    s, p, o = summary(), plan(), b["overview"]
    urgent = [x for x in p if x["status"] == E.STATUS[0]][:5]
    dm = o["demand_month"]
    w = watchlist()
    return clean({**s, "urgent": [{"name": x["name"], "q": round(x["q"]), "capital": round(x["q"] * x["price"])} for x in urgent],
                  "demand_last_month": dm[-1]["month"], "demand_last": dm[-1]["value"], "demand_change_pct": round((dm[-1]["value"] / dm[-2]["value"] - 1) * 100, 1),
                  "gain_top20_pct": round(b["risk"]["gain"][2]["caught"] * 100, 1),
                  "slow": int((w["group"] == "Slow").sum()), "risky": int((w["group"] == "Risky").sum()),
                  "top_watch": [{"seller": r["short_id"], "late_pct": round(r["late_rate"] * 100, 1), "cancel_pct": round(r["cancel_rate"] * 100, 1)} for _, r in w.head(3).iterrows()]})


def report_text():
    f = report_facts()
    u = "\n".join(f"- {x['name']}: nhập {vn(x['q'], 0)} đơn vị, khoảng {vn(x['capital'], 0)} đồng" for x in f["urgent"]) or "- Không có danh mục nguy cơ hết hàng"
    w = "\n".join(f"- Seller {x['seller']}: trễ {vn(x['late_pct'])}%, hủy {vn(x['cancel_pct'])}%" for x in f["top_watch"])
    return (f"BÁO CÁO KHUYẾN NGHỊ TUẦN {f['week']}\n\n"
            f"1. Tóm tắt\n{f['stockout']} danh mục nguy cơ hết hàng, {f['below_rop']} danh mục dưới ROP, {f['overstock']} danh mục tồn dư. "
            f"Tổng lượng nhập đề xuất {vn(f['total_q'], 0)} đơn vị, vốn khoảng {vn(f['capital'], 0)} đồng.\n\n"
            f"2. Nhập hàng ưu tiên\n{u}\n\n"
            f"3. Nhu cầu\nNhu cầu tháng {f['demand_last_month']} là {vn(f['demand_last'], 0)} dòng sản phẩm ({'+' if f['demand_change_pct'] >= 0 else ''}{vn(f['demand_change_pct'])}% so với tháng trước).\n\n"
            f"4. Rủi ro giao hàng\nTỷ lệ giao trễ năm 2018 là {vn(f['late_2018'])}%. Có {f['high_risk_orders']} đơn tháng 7–8 có điểm rủi ro từ {int(C.RISK_ALERT * 100)}%; "
            f"kiểm tra 20% đơn rủi ro nhất phát hiện {vn(f['gain_top20_pct'])}% đơn trễ.\n\n"
            f"5. Nhà bán hàng\n{f['watch_sellers']} Seller cần theo dõi ({f['slow']} chậm xử lý, {f['risky']} hay hủy đơn). Ưu tiên làm việc với:\n{w}\n\n"
            f"6. Đề xuất quyết định\nDuyệt nhập cho nhóm nguy cơ hết hàng trong tuần; đặt hàng chu kỳ này cho nhóm dưới ROP; gửi thư nhắc các Seller trong danh sách theo dõi.\n\n"
            "Quyết định cuối cùng thuộc về nhà quản trị.")


def report_ai():
    return clean(A.weekly_report(report_facts(), report_text()))


# ---------------- Công cụ chỉ đọc cho tác tử ----------------
def t_summary():
    return summary()


def t_plan(status=None, limit=8):
    p = plan()
    if status:
        p = [x for x in p if _norm(status) in _norm(x["status"])]
    return [{"category": x["name"], "status": x["status"], "forecast": round(x["yhat"]), "stock": round(x["stock"]), "rop": round(x["rop"]),
             "order_qty": round(x["q"]), "capital_vnd": round(x["q"] * x["price"])} for x in p[:min(int(limit), 20)]]


def t_category(name):
    q = _norm(name)
    for x in plan():
        if q in _norm(x["name"]) or q in _norm(x["category"]):
            s = load()["forecast"]["series"][x["category"]]
            return {"category": x["name"], "status": x["status"], "forecast_next_week": round(x["yhat"], 1), "sigma": round(x["sigma"], 1),
                    "stock": round(x["stock"]), "safety_stock": round(x["ss"]), "rop": round(x["rop"]), "order_up_to": round(x["s"]),
                    "order_qty": round(x["q"]), "wape_gb_pct": round(s["wape_gb"] * 100, 1), "wape_naive_pct": round(s["wape_naive"] * 100, 1)}
    return {"error": "Không tìm thấy danh mục", "categories": [x["name"] for x in plan()]}


def t_risky(limit=5):
    r = load()["risk"]["recent"].head(min(int(limit), 10))
    return [{"order": x["order_id"][:8], "route": f"{x['seller_state']}->{x['customer_state']}", "risk_pct": round(float(x["risk"]) * 100, 1)} for _, x in r.iterrows()]


def t_order(order):
    try:
        d = order_detail(str(order)[:8])
    except KeyError as e:
        return {"error": str(e)}
    return {"risk_pct": round(d["risk"] * 100, 1), "route": d["route"], "top_factors": [{"factor": z["label"], "value": z["value"], "log_odds": round(z["log_odds"], 2)} for z in d["shap"][:3]],
            "suggested_actions": d["actions"]}


def t_sellers():
    p = seller_page()
    return {"groups": [{"group": g["name"], "count": g["n"], "late_pct": round(g["late"] * 100, 1), "cancel_pct": round(g["cancel"] * 100, 2),
                        "policy": g["policy"]} for g in p["groups"]],
            "watchlist_top": [{"seller": w["id"], "group": w["group"], "late_pct": round(w["late"] * 100, 1)} for w in p["watch"][:5]]}


def t_policy(query):
    return [{"id": d["id"], "title": d["title"], "text": d["text"]} for d in A.KB.search(query, 3)]


def t_prefetch(question):
    """Đoán các công cụ chắc chắn cần dùng để tra sẵn, giúp LLM trả lời trong 1 lượt."""
    q = _norm(question)
    calls = [("get_summary", {}), ("search_policy", {"query": question})]
    for x in plan():
        if _norm(x["name"]) in q or _norm(x["category"]) in q:
            calls.append(("get_category", {"name": x["name"]}))
            break
    m = re.search(r"\b[0-9a-f]{8}", question.lower())
    if m:
        calls.append(("get_order_risk", {"order": m.group(0)}))
    elif "rui ro" in q or re.search(r"\btre\b", q):
        calls.append(("list_risky_orders", {"limit": 5}))
    if "seller" in q or "nguoi ban" in q:
        calls.append(("seller_summary", {}))
    if "nhap gap" in q or "can nhap" in q or "het hang" in q:
        calls.append(("list_purchase_plan", {}))
    return calls


TOOLS = {"get_summary": t_summary, "list_purchase_plan": t_plan, "get_category": t_category, "list_risky_orders": t_risky,
         "get_order_risk": t_order, "seller_summary": t_sellers, "search_policy": t_policy, "_prefetch": t_prefetch}


def _tool(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


TOOL_SCHEMAS = [
    _tool("get_summary", "Tóm tắt tuần: số danh mục nguy cơ hết hàng, dưới ROP, tổng lượng nhập, vốn, tỷ lệ trễ, số Seller cần theo dõi"),
    _tool("list_purchase_plan", "Bảng đề xuất nhập hàng tuần tới, có thể lọc theo trạng thái", {"status": {"type": "string"}, "limit": {"type": "integer"}}),
    _tool("get_category", "Dự báo, Safety Stock, ROP, lượng nhập của một danh mục (tên tiếng Việt hoặc tiếng Anh)", {"name": {"type": "string"}}, ["name"]),
    _tool("list_risky_orders", "Các đơn tháng 7-8/2018 có rủi ro giao trễ cao nhất", {"limit": {"type": "integer"}}),
    _tool("get_order_risk", "Điểm rủi ro, yếu tố SHAP và gợi ý xử lý của một đơn theo 8 ký tự đầu mã đơn", {"order": {"type": "string"}}, ["order"]),
    _tool("seller_summary", "4 cụm Seller, chính sách và danh sách Seller cần theo dõi"),
    _tool("search_policy", "Tìm quy định nội bộ liên quan", {"query": {"type": "string"}}, ["query"]),
]
