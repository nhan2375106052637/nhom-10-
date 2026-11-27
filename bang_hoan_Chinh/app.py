"""Kho Vận DSS (Nhóm 10): chạy `python app.py` rồi mở http://127.0.0.1:5050"""
import threading
import webbrowser

from flask import Flask, jsonify, render_template, request

import agents as A
import config as C
import services as S
import train

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False   # giữ đúng thứ tự mô hình như báo cáo
PAGES = [("/", "overview", "01", "Tổng quan & Cảnh báo"), ("/du-bao", "forecast", "02", "Dự báo & Nhập hàng"),
         ("/what-if", "whatif", "03", "Mô phỏng tình huống"), ("/rui-ro", "risk", "04", "Rủi ro giao hàng"),
         ("/seller", "seller", "05", "Nhà bán hàng (Seller)"), ("/bao-cao", "report", "06", "Báo cáo tuần"),
         ("/tro-ly", "assistant", "AI", "Trợ lý AI"), ("/cai-dat", "settings", "⚙", "Cài đặt AI")]


def page(name):
    b = S.load()
    title = next(p[3] for p in PAGES if p[1] == name)
    return render_template(f"{name}.html", pages=PAGES, active=name, title=title, ai=A.ai_ready(), sample=b["sample_data"], week=b["forecast"]["next_week"])


for url, name, _, _ in PAGES:
    app.add_url_rule(url, name, lambda name=name: page(name))


def num(key, default):
    v = request.args.get(key)
    return float(v) if v not in (None, "") else default


@app.errorhandler(KeyError)
def not_found(e):
    return jsonify(error=str(e).strip("'\"")), 404


@app.get("/api/overview")
def api_overview():
    return jsonify(S.overview())


@app.post("/api/narrator")
def api_narrator():
    return jsonify(S.clean(A.narrator(S.summary())))


@app.get("/api/forecast")
def api_forecast():
    return jsonify(S.forecast(request.args.get("cat")))


@app.get("/api/whatif")
def api_whatif():
    cat = request.args.get("cat")
    base = S.whatif_calc(cat, C.LEAD_TIME, C.SERVICE_LEVEL, 0)
    sc = S.whatif_calc(cat, num("lead", C.LEAD_TIME), num("service", C.SERVICE_LEVEL), num("demand", 0), num("stock", None))
    only_lead = S.whatif_calc(cat, num("lead", C.LEAD_TIME), C.SERVICE_LEVEL, 0)
    only_sl = S.whatif_calc(cat, C.LEAD_TIME, num("service", C.SERVICE_LEVEL), 0)
    return jsonify(S.clean({"base": base, "scenario": sc, "only_lead": only_lead, "only_service": only_sl}))


@app.post("/api/whatif/note")
def api_whatif_note():
    d = request.get_json()
    return jsonify(S.purchase_note(d["cat"], float(d.get("lead", 1)), float(d.get("service", .95)), float(d.get("demand", 0)),
                                   None if d.get("stock") in (None, "") else float(d["stock"])))


@app.get("/api/risk")
def api_risk():
    return jsonify(S.risk_page())


@app.get("/api/order/<oid>")
def api_order(oid):
    return jsonify(S.order_detail(oid))


@app.post("/api/order/<oid>/explain")
def api_explain(oid):
    return jsonify(S.explain(oid))


@app.get("/api/seller")
def api_seller():
    return jsonify(S.seller_page())


@app.get("/api/seller/<sid>")
def api_seller_detail(sid):
    return jsonify(S.seller_detail(sid))


@app.post("/api/seller/<sid>/note")
def api_seller_note(sid):
    return jsonify(S.seller_note(sid))


@app.get("/api/report")
def api_report():
    return jsonify(text=S.report_text(), week=S.load()["forecast"]["next_week"])


@app.post("/api/report/ai")
def api_report_ai():
    return jsonify(S.report_ai())


@app.post("/api/chat")
def api_chat():
    d = request.get_json()
    q = (d.get("question") or "").strip()
    if not q:
        return jsonify(error="Câu hỏi trống"), 400
    return jsonify(S.clean(A.chat(q[:2000], d.get("history") or [], S.TOOLS, S.TOOL_SCHEMAS)))


@app.post("/api/decision")
def api_decision():
    """Người quản trị duyệt hoặc từ chối. Chỉ ghi Audit log, không thực thi thật."""
    d = request.get_json()
    row = A.audit("decision", decision=d.get("decision"), target=d.get("target"), action=d.get("action"), agent=d.get("agent"),
                  edited=(d.get("text") or "") != (d.get("original") or ""), source_audit=d.get("audit_id"))
    return jsonify(ok=True, id=row["id"])


@app.get("/api/settings")
def api_settings():
    s = A.settings()
    return jsonify(provider=s["provider"], models=",".join(s["models"]), base_url=s["base_url"], ready=A.ai_ready(),
                   key_hint=("••••" + s["api_key"][-4:]) if len(s["api_key"]) > 8 else ("đã lưu" if s["api_key"] else ""),
                   providers={k: {"label": v["label"], "base": v["base"], "models": v["models"]} for k, v in A.PROVIDERS.items()})


@app.post("/api/settings")
def api_save_settings():
    d = request.get_json()
    if any("\n" in str(d.get(k, "")) for k in ("api_key", "models", "base_url")):
        return jsonify(error="Giá trị không hợp lệ"), 400
    A.save_settings(d.get("provider", "gemini"), d.get("api_key", ""), d.get("models", ""), d.get("base_url", ""))
    return jsonify(ok=True, ready=A.ai_ready())


@app.post("/api/settings/test")
def api_test():
    try:
        r = A.call_llm([{"role": "user", "content": "Trả lời đúng một từ: OK"}], timeout=30, cache=False)
        return jsonify(ok=True, model=r["model"], reply=r["content"][:80], fallbacks=r["fallbacks"])
    except A.LLMError as e:
        return jsonify(ok=False, error=str(e)[:400])


@app.get("/api/audit")
def api_audit():
    rows = A.read_audit(1000)
    calls = [r for r in rows if r.get("number_check")]
    dec = [r for r in rows if r["event"] == "decision"]
    stats = {"calls": len([r for r in rows if r["event"] in ("llm_call", "chat")]), "checked": len(calls),
             "faithful": (sum(r["number_check"]["score"] for r in calls) / len(calls)) if calls else None,
             "decisions": len(dec), "approved": sum(r.get("decision") == "approve" for r in dec), "edited": sum(bool(r.get("edited")) for r in dec),
             "rag": A.KB.recall_at(3)}
    return jsonify(rows=rows[:60], stats=stats)


if __name__ == "__main__":
    if not (C.ARTIFACT_DIR / "bundle.joblib").exists():
        print("Lần chạy đầu: đang chuẩn bị dữ liệu và huấn luyện mô hình (khoảng 1 phút)...")
        train.build()
    S.load()
    url = f"http://127.0.0.1:{C.PORT}"
    print(f"\nKho Vận DSS đang chạy tại {url}  (Ctrl+C để dừng)\n")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=C.PORT, debug=False)
