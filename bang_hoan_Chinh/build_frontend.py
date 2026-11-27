"""Tạo static/index.html từ dashboard gốc + thêm khung chat Trợ lý AI. (Chỉ cần chạy khi sửa giao diện.)"""
import os, re
BASE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(BASE, "frontend", "dashboard_src.html"), encoding="utf-8").read()

CHAT_CSS = r"""
/* ---------- AI assistant drawer ---------- */
.ai-fab{position:fixed;right:max(20px,env(safe-area-inset-right,0px));bottom:calc(20px + env(safe-area-inset-bottom,0px));z-index:40;display:flex;align-items:center;gap:8px;
  background:var(--side);color:#fff;border:0;border-radius:999px;padding:11px 16px 11px 12px;font:600 13.5px var(--font);cursor:pointer;box-shadow:0 6px 20px rgba(16,35,63,.28)}
.ai-fab:hover{background:var(--side-active)} .ai-fab:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ai-fab .dot{width:26px;height:26px;border-radius:50%;background:var(--accent);display:grid;place-items:center;font:700 11px var(--mono)}
.ai{position:fixed;top:0;right:0;bottom:0;width:min(420px,100vw);z-index:45;background:var(--panel);border-left:1px solid var(--line);display:flex;flex-direction:column;
  box-shadow:-10px 0 30px rgba(0,0,0,.12);padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
.ai-h{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--line)}
.ai-h .ic{width:32px;height:32px;border-radius:9px;background:var(--side);color:#fff;display:grid;place-items:center;font:700 12px var(--mono)}
.ai-h b{font-size:14.5px;display:block} .ai-h small{font-size:11.5px;color:var(--muted)}
.ai-h .mode{margin-left:auto;font-size:11px;font-weight:600;padding:3px 8px;border-radius:999px;background:var(--good-bg);color:var(--good-fg);white-space:nowrap}
.ai-h .mode.local{background:var(--accent-soft);color:var(--accent)}
.ai-h .x{all:unset;cursor:pointer;width:30px;height:30px;border-radius:8px;display:grid;place-items:center;color:var(--fg2);font-size:18px}
.ai-h .x:hover{background:var(--panel2)} .ai-h .x:focus-visible{outline:2px solid var(--accent)}
.ai-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;background:var(--bg)}
.msg{max-width:92%;font-size:13.4px;line-height:1.55;padding:10px 12px;border-radius:12px;overflow-wrap:anywhere}
.msg.u{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:4px}
.msg.a{align-self:flex-start;background:var(--panel);border:1px solid var(--line);border-bottom-left-radius:4px}
.msg.a p{margin:0 0 6px} .msg.a p:last-child{margin-bottom:0}
.msg.a ul{margin:4px 0 6px;padding-left:18px} .msg.a li{margin:2px 0}
.msg .meta{margin-top:6px;font-size:11px;color:var(--muted)}
.msg .acts2{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.msg .acts2 button{all:unset;cursor:pointer;font-size:12px;font-weight:600;color:var(--accent);border:1px solid var(--line);border-radius:7px;padding:4px 9px;background:var(--panel2)}
.msg .acts2 button:hover{background:var(--accent-soft)} .msg .acts2 button:focus-visible{outline:2px solid var(--accent)}
.typing{display:inline-flex;gap:4px} .typing i{width:6px;height:6px;border-radius:50%;background:var(--muted);animation:bl 1s infinite}
.typing i:nth-child(2){animation-delay:.15s} .typing i:nth-child(3){animation-delay:.3s}
@keyframes bl{0%,100%{opacity:.25}50%{opacity:1}}
@media (prefers-reduced-motion:reduce){.typing i{animation:none}}
.ai-sug{display:flex;gap:6px;flex-wrap:wrap;padding:10px 16px 0}
.ai-sug button{all:unset;cursor:pointer;font-size:12px;padding:5px 10px;border-radius:999px;border:1px solid var(--line);color:var(--fg2);background:var(--panel)}
.ai-sug button:hover{border-color:var(--accent);color:var(--accent)} .ai-sug button:focus-visible{outline:2px solid var(--accent)}
.ai-f{display:flex;gap:8px;padding:12px 16px 14px;align-items:flex-end}
.ai-f textarea{flex:1;resize:none;font:inherit;font-size:13.5px;padding:9px 11px;border-radius:10px;border:1px solid var(--line);background:var(--panel2);color:var(--fg);max-height:120px;min-height:40px}
.ai-f textarea:focus{outline:2px solid var(--accent);outline-offset:-1px}
.ai-f button{all:unset;cursor:pointer;background:var(--accent);color:#fff;font-weight:600;font-size:13px;padding:10px 14px;border-radius:10px}
.ai-f button[disabled]{opacity:.5;cursor:default}
.ai-note{font-size:11px;color:var(--muted);padding:0 16px 10px}
nav button.ai-nav i{background:#2a78d6;color:#fff}
@media (min-width:1100px){body.ai-open main{margin-right:420px}}
.ai-sug.done{display:none}
"""

CHAT_HTML = r"""
<button class="ai-fab" id="ai-fab" aria-controls="ai" aria-expanded="false"><span class="dot">AI</span>Hỏi trợ lý</button>
<div class="ai" id="ai" role="dialog" aria-label="Trợ lý AI" hidden>
  <div class="ai-h"><span class="ic">AI</span><div><b>Trợ lý Kho Vận</b><small>Tra cứu tồn kho, dự báo, rủi ro, Seller</small></div>
    <span class="mode local" id="ai-mode">Đang kết nối…</span><button class="x" id="ai-close" aria-label="Đóng trợ lý">×</button></div>
  <div class="ai-msgs" id="ai-msgs" aria-live="polite"></div>
  <div class="ai-sug" id="ai-sug"></div>
  <form class="ai-f" id="ai-form"><textarea id="ai-in" rows="1" placeholder="Hỏi ví dụ: Đồ chơi cần nhập bao nhiêu?" aria-label="Câu hỏi cho trợ lý"></textarea><button id="ai-send" type="submit">Gửi</button></form>
  <div class="ai-note">Trợ lý chỉ đề xuất; quyết định cuối cùng thuộc về bạn. Thông tin cá nhân được ẩn trước khi gửi ra LLM.</div>
</div>
"""

CHAT_JS = r"""
/* ---------- AI assistant ---------- */
const AI = {hist: [], busy: false};
function esc(s) { return String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); }
function md(text) {
  const lines = esc(text).split("\n"); let html = "", inList = false;
  const inline = s => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  for (const ln of lines) {
    const m = ln.match(/^\s*[-•*]\s+(.*)/);
    if (m) { if (!inList) { html += "<ul>"; inList = true; } html += "<li>" + inline(m[1]) + "</li>"; continue; }
    if (inList) { html += "</ul>"; inList = false; }
    if (ln.trim()) html += "<p>" + inline(ln) + "</p>";
  }
  if (inList) html += "</ul>";
  return html;
}
function addMsg(role, text, extra = {}) {
  const box = $("#ai-msgs"); const d = document.createElement("div"); d.className = "msg " + (role === "user" ? "u" : "a");
  if (role === "user") d.textContent = text; else d.innerHTML = md(text);
  if (extra.actions && extra.actions.length) {
    const a = document.createElement("div"); a.className = "acts2";
    extra.actions.forEach(act => { const b = document.createElement("button"); b.textContent = act.label; b.addEventListener("click", () => applyAction(act)); a.appendChild(b); });
    d.appendChild(a);
  }
  if (extra.meta) { const m = document.createElement("div"); m.className = "meta"; m.textContent = extra.meta; d.appendChild(m); }
  box.appendChild(d); box.scrollTop = box.scrollHeight; return d;
}
function applyAction(a) {
  if (a.tab === "whatif") {
    if (a.cat) wiCat = a.cat; wiInit();
    if (a.L != null) $("#wi-lt").value = a.L;
    if (a.sl != null) $("#wi-sl").value = String(a.sl === 0.9 ? "0.90" : a.sl);
    if (a.dm != null) $("#wi-dm").value = a.dm;
    if (a.stock != null) { const st = $("#wi-st"); if (+st.max < a.stock) st.max = Math.ceil(a.stock * 1.2); st.value = a.stock; }
  }
  if (a.tab === "dubao" && a.cat) fcCat = a.cat;
  if (a.tab === "ruiro" && a.order) riskSel = a.order;
  go(a.tab);
  if (innerWidth < 900) toggleAI(false);
}
function toggleAI(open) {
  const p = $("#ai"), f = $("#ai-fab"); p.hidden = !open; f.hidden = open; f.setAttribute("aria-expanded", open);
  document.body.classList.toggle("ai-open", open); setTimeout(() => render(cur), 60);
  if (open) { setTimeout(() => $("#ai-in").focus(), 50); }
}
async function ask(q) {
  q = q.trim(); if (!q || AI.busy) return;
  AI.busy = true; $("#ai-send").disabled = true; $("#ai-in").value = "";
  addMsg("user", q); $("#ai-sug").classList.add("done");
  const wait = addMsg("assistant", ""); wait.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
  try {
    const r = await fetch("/api/chat", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({message: q, history: AI.hist})});
    const d = await r.json(); wait.remove();
    if (!r.ok) { addMsg("assistant", d.error || "Máy chủ báo lỗi. Thử lại sau."); }
    else {
      addMsg("assistant", d.answer, {actions: d.actions, meta: (d.source === "llm" ? "Trả lời bởi LLM, dựa trên dữ liệu DSS" : "Tra cứu trực tiếp từ dữ liệu DSS") + (d.note ? " · " + d.note : "")});
      AI.hist.push({role: "user", content: q}, {role: "assistant", content: d.answer}); AI.hist = AI.hist.slice(-12);
    }
  } catch (e) { wait.remove(); addMsg("assistant", "Không kết nối được máy chủ. Kiểm tra cửa sổ đang chạy **python app.py** rồi thử lại."); }
  AI.busy = false; $("#ai-send").disabled = false;
}
async function initAI() {
  $("#ai-fab").addEventListener("click", () => toggleAI(true));
  $("#ai-close").addEventListener("click", () => toggleAI(false));
  $("#t-ai").addEventListener("click", () => toggleAI($("#ai").hidden));
  $("#ai-form").addEventListener("submit", e => { e.preventDefault(); ask($("#ai-in").value); });
  $("#ai-in").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask($("#ai-in").value); } });
  $("#ai-in").addEventListener("input", e => { e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px"; });
  addEventListener("keydown", e => { if (e.key === "Escape" && !$("#ai").hidden) toggleAI(false); });
  try {
    const s = await (await fetch("/api/assistant/status")).json();
    const m = $("#ai-mode"); m.textContent = s.mode === "llm" ? s.label : "Offline · nội bộ"; m.classList.toggle("local", s.mode !== "llm");
    $("#ai-sug").innerHTML = ""; s.suggestions.forEach(q => { const b = document.createElement("button"); b.textContent = q; b.addEventListener("click", () => ask(q)); $("#ai-sug").appendChild(b); });
  } catch (e) { $("#ai-mode").textContent = "Mất kết nối"; }
  addMsg("assistant", "Xin chào! Mình tra cứu được **đề xuất nhập hàng, tồn kho, What-If, rủi ro giao hàng, Seller** và giải thích các chỉ số. Chọn một câu gợi ý hoặc gõ câu hỏi của bạn.");
}
"""

out = src
out = out.replace("const D = /*DATA*/null;", "let D = null;")
out = out.replace('go((location.hash || "").slice(1) || "tongquan");',
    'fetch("/api/data").then(r => r.json()).then(d => { D = d; go((location.hash || "").slice(1) || "tongquan"); })\n'
    '  .catch(() => { document.querySelector("main").innerHTML = "<p style=\\"padding:40px\\">Không tải được dữ liệu. Hãy chạy <b>python app.py</b> rồi mở http://localhost:8000</p>"; });\n'
    + CHAT_JS + "\ninitAI();")
out = out.replace("</style>", CHAT_CSS + "</style>", 1)
out = out.replace('<button role="tab" id="t-baocao" data-tab="baocao"><i>06</i>Báo cáo khuyến nghị</button>',
                  '<button role="tab" id="t-baocao" data-tab="baocao"><i>06</i>Báo cáo khuyến nghị</button>\n      <button id="t-ai" class="ai-nav" type="button"><i>AI</i>Trợ lý AI</button>')
out = out.replace('<div id="tip" hidden></div>', '<div id="tip" hidden></div>' + CHAT_HTML)
out = out.replace('document.querySelectorAll("nav button").forEach(b => b.addEventListener("click", () => go(b.dataset.tab)));',
                  'document.querySelectorAll("nav button[data-tab]").forEach(b => b.addEventListener("click", () => go(b.dataset.tab)));')
out = out.replace('document.querySelectorAll("nav button").forEach(b => b.setAttribute("aria-selected", b.dataset.tab === tab));',
                  'document.querySelectorAll("nav button[data-tab]").forEach(b => b.setAttribute("aria-selected", b.dataset.tab === tab));')
out = out.replace('<span class="chip">Lead time: <b>1 tuần</b></span>', '<span class="chip">Lead time: <b>1 tuần</b></span><span class="chip">Máy chủ: <b>localhost</b></span>')
html = ('<!doctype html>\n<html lang="vi">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
        '<style>[hidden]{display:none!important}body{margin:0}</style>\n' + out.replace("<meta name=\"claude:viewport-fit-sides\" content=\"cover\">\n", "") + "\n</body>\n</html>\n")
# move title/links/style into head: everything before first <div class="shell"> goes to head
i = html.index('<div class="shell">')
html = html[:i] + "</head>\n<body>\n" + html[i:]
os.makedirs(os.path.join(BASE, "static"), exist_ok=True)
open(os.path.join(BASE, "static", "index.html"), "w", encoding="utf-8").write(html)
assert "let D = null;" in html and "initAI();" in html and 'id="t-ai"' in html
print("static/index.html:", len(html) // 1024, "KB")
