/* Hàm dùng chung và thư viện biểu đồ SVG nhỏ, không cần mạng khi demo */
const $=s=>document.querySelector(s);
function el(tag,attrs={},...kids){
  const n=document.createElement(tag);
  for(const[k,v]of Object.entries(attrs||{})){
    if(k.startsWith('on'))n[k]=v;
    else if(k==='selected'||k==='disabled'){n[k]=!!v}
    else if(v!=null)n.setAttribute(k,v);
  }
  n.append(...kids.flat().filter(k=>k!=null&&k!==false));
  return n;
}
const num=(v,d=0)=>Number(v).toLocaleString('vi-VN',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmt={num,int:v=>num(v,0),money:v=>num(v,0)+' đ',pct:(v,d=1)=>num(v,d)+'%',score:v=>num(v,2)};
async function api(url,body){
  const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(d.error||`Lỗi ${r.status}`);
  return d;
}
function fill(box,...kids){box.replaceChildren(...kids.filter(k=>k!=null))}
/* Bảng thuật ngữ: thêm dấu ? giải thích bằng lời thường */
const GLOSSARY={
  'WAPE':'Sai số dự báo tính theo %: tổng phần đoán lệch chia tổng số bán thật. Càng thấp càng tốt.',
  'σ':'Độ lệch dự báo: mô hình thường đoán lệch khoảng bao nhiêu sản phẩm mỗi tuần. Càng lớn càng cần để dành nhiều hàng.',
  'SS':'Tồn kho an toàn (Safety Stock): lượng hàng để dành phòng khi bán nhiều hơn dự báo.',
  'ROP':'Điểm đặt hàng (Reorder Point): khi tồn kho xuống dưới mức này thì phải đặt hàng.',
  'Q':'Lượng nên nhập trong tuần để đủ bán tới lần nhập sau.',
  'S':'Mức tồn tối đa: đủ bán tới lần nhập kế tiếp cộng phần an toàn.',
  'z':'Hệ số an toàn theo mức phục vụ: 95% → 1,645; 99% → 2,326.',
  'Mức phục vụ':'Tỷ lệ số tuần không bị hết hàng mà bạn muốn đạt. 95% nghĩa là chấp nhận hết hàng khoảng 1 trong 20 tuần.',
  'Lead time':'Thời gian từ lúc đặt hàng đến lúc hàng về kho.',
  'MAE':'Sai số tuyệt đối trung bình: trung bình mỗi tuần đoán lệch bao nhiêu sản phẩm.',
  'RMSE':'Giống MAE nhưng phạt nặng các tuần đoán lệch nhiều.',
  'Xu hướng lệch':'Mô hình có xu hướng đoán cao (+) hay thấp (−) hơn thực tế.',
  'AUC':'Khả năng xếp đơn trễ lên trên đơn đúng hạn: 0,5 là đoán bừa, 1 là hoàn hảo.',
  'PR-AUC':'Độ chính xác khi tìm đơn trễ, phù hợp khi đơn trễ chiếm ít.',
  'Precision':'Trong các đơn bị cảnh báo, bao nhiêu % thật sự trễ.',
  'Recall':'Trong các đơn trễ thật, hệ thống bắt được bao nhiêu %.',
  'F1':'Điểm cân bằng giữa Precision và Recall.',
  'SHAP':'Cách giải thích mô hình: cho biết mỗi yếu tố đẩy rủi ro lên (đỏ) hay kéo xuống (xanh) bao nhiêu.',
  'Silhouette':'Điểm đánh giá các nhóm tách nhau rõ hay không: càng cao càng rõ.',
  'Naive':'Cách đoán đơn giản nhất: tuần sau bán bằng tuần này. Dùng để so sánh.',
};
function termKey(t){t=String(t);return Object.keys(GLOSSARY).sort((a,b)=>b.length-a.length).find(k=>new RegExp('(^|[\\s(])'+k.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'($|[\\s)/:-])').test(t))}
function term(label){const k=termKey(label);if(!k)return label;
  const q=el('span',{class:'q',tabindex:0,'aria-label':GLOSSARY[k]},'?');
  q.onpointerenter=q.onfocus=e=>{const t=$('#tip');t.replaceChildren(el('b',{},k),el('div',{},GLOSSARY[k]));t.hidden=false;const r=q.getBoundingClientRect();
    t.style.left=Math.min(innerWidth-t.offsetWidth-10,r.left)+'px';t.style.top=(r.bottom+6)+'px'};
  q.onpointerleave=q.onblur=()=>{$('#tip').hidden=true};
  return el('span',{class:'term'},label,q)}
function stat(l,v){return el('div',{class:'stat'},el('span',{},term(l)),el('b',{},String(v)))}
function tierBadge(t){return el('span',{class:'badge '+t.key},t.name)}
function table(sel,head,rows,onRow){
  $(sel).replaceChildren(el('thead',{},el('tr',{},...head.map(h=>el('th',{},h)))),
    el('tbody',{},...rows.map((r,i)=>el('tr',onRow?{class:'click',onclick(){onRow(i)},title:'Bấm để xem chi tiết'}:{},...r.map(c=>el('td',{},c instanceof Node?c:String(c)))))));
  $(sel).querySelectorAll('th').forEach(th=>{const t=th.textContent;if(termKey(t))th.replaceChildren(term(t))});
}
const ST={'Nguy cơ hết hàng':'critical','Dưới ROP':'medium','Tồn dư':'serious','An toàn':'low'};
const ST_VI={'Dưới ROP':'Sắp hết (dưới ROP)','Tồn dư':'Tồn quá nhiều'};
function statusBadge(s){return el('span',{class:'badge st '+(ST[s]||''),title:s},ST_VI[s]||s)}
/* Hiện văn bản AI: giữ xuống dòng, hỗ trợ **đậm** */
function rich(t){
  const box=el('div',{class:'rich'});
  t.split('\n').forEach(line=>{
    const p=el('p');line.split(/(\*\*[^*]+\*\*)/).forEach(s=>p.append(/^\*\*/.test(s)?el('strong',{},s.slice(2,-2)):s));
    box.append(p);
  });
  return box;
}
function aiMeta(r){
  const label={ai:`AI: ${r.model||''}`,offline:'Bản theo mẫu (chưa có key)',fallback:'Bản theo mẫu (LLM lỗi)'}[r.mode];
  const box=el('div',{class:'meta'},el('span',{class:'badge '+(r.mode==='ai'?'':'serious')},label));
  if(r.secs)box.append(el('span',{class:'badge'},`${r.secs}s`));
  (r.sources||[]).forEach(s=>box.append(el('span',{class:'badge'},s)));
  if(r.pii_masked)box.append(el('span',{class:'badge'},`Privacy Agent đã ẩn ${r.pii_masked} định danh`));
  if(r.check){const bad=r.check.unsupported.length;
    box.append(el('span',{class:'badge '+(bad?'critical':'low')},bad?`Cảnh báo: ${bad} con số không có trong dữ kiện (${r.check.unsupported.map(n=>num(n,n%1?1:0)).join('; ')})`:'Số liệu khớp dữ kiện'))}
  if(r.error)box.append(el('span',{class:'small err'},r.error));
  return box;
}
/* Gọi AI, hiện kết quả và khung duyệt của con người */
async function aiCall(out,btn,fn,opt={}){
  const box=$(out),b=btn&&$(btn),t=b&&b.textContent;
  if(b){b.disabled=true;b.textContent='Đang xử lý...'}
  const tip=el('p',{class:'muted'},'AI đang soạn... 0s'),t0=Date.now(),tick=setInterval(()=>tip.textContent=`AI đang soạn... ${Math.round((Date.now()-t0)/1000)}s`,1000);
  box.replaceChildren(tip);
  try{
    const r=await fn();clearInterval(tick);r.secs=((Date.now()-t0)/1000).toFixed(1);
    const body=opt.edit?el('textarea',{class:'draft',rows:10,'aria-label':'Bản nháp'}):rich(r.text);
    if(opt.edit)body.value=r.text;
    box.replaceChildren(el('div',{class:'airesult'},opt.review?el('h3',{},opt.review.title):null,body,aiMeta(r),
      r.masked_prompt?el('details',{},el('summary',{},'Xem dữ liệu đã ẩn danh gửi cho LLM'),el('pre',{},r.masked_prompt)):null,
      opt.review?review(r,opt.review,()=>opt.edit?body.value:r.text):null));
  }catch(e){clearInterval(tick);box.replaceChildren(el('p',{class:'err'},e.message))}
  if(b){b.disabled=false;b.textContent=t}
}
/* Nhớ trạng thái ẩn/hiện của hộp hướng dẫn cho từng trang */
(()=>{const g=$('#guide');if(!g)return;const k='guide:'+g.dataset.page;
  try{if(localStorage.getItem(k)==='closed')g.open=false}catch(e){}
  g.ontoggle=()=>{try{localStorage.setItem(k,g.open?'open':'closed')}catch(e){}}})();
function review(r,rv,getText){
  const msg=el('span',{class:'small'});
  const send=async(decision)=>{
    await api('/api/decision',{decision,target:rv.target,action:rv.action,agent:rv.agent,text:getText(),original:r.text,audit_id:r.audit_id});
    wrap.replaceChildren(el('span',{class:'badge '+(decision==='approve'?'low':'serious')},decision==='approve'?'Đã duyệt, đã ghi Audit log (mô phỏng, chưa gửi thật)':'Đã từ chối, đã ghi Audit log'));
  };
  const wrap=el('div',{class:'actions'},el('button',{class:'btn primary',onclick(){send('approve')}},'Duyệt và Thực thi'),el('button',{class:'btn',onclick(){send('reject')}},'Từ chối'),msg);
  return wrap;
}
const btn=$('#themeBtn');
if(btn)btn.onclick=()=>{
  const dark=document.documentElement.dataset.theme?document.documentElement.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme=dark?'light':'dark';
  try{localStorage.setItem('theme',document.documentElement.dataset.theme)}catch(e){}
  Charts.redraw();
};

/* ---------- Biểu đồ ---------- */
const Charts=(()=>{
  const NS='http://www.w3.org/2000/svg',tip=$('#tip');let jobs={};
  const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const s=(t,a={},...k)=>{const n=document.createElementNS(NS,t);for(const[x,y]of Object.entries(a))n.setAttribute(x,y);n.append(...k);return n};
  const text=(x,y,t,a={})=>s('text',{x,y,'font-size':12,fill:css('--muted'),...a},t);
  function nice(max,min=0){const span=(max-min)||1,step=Math.pow(10,Math.floor(Math.log10(span/4))),m=[1,2,2.5,5,10].find(f=>span/(f*step)<=5)*step,out=[];
    for(let v=Math.floor(min/m)*m;v<=Math.ceil(max/m)*m+1e-9;v+=m)out.push(+v.toFixed(6));return out}
  function showTip(e,nodes){tip.replaceChildren(...nodes);tip.hidden=false;const w=tip.offsetWidth;
    tip.style.left=Math.min(innerWidth-w-10,e.clientX+14)+'px';tip.style.top=(e.clientY+14)+'px'}
  const hide=()=>{tip.hidden=true};
  const tipRow=(k,v,c)=>el('div',{class:'tr'},c?el('i',{style:`background:${c}`}):null,el('b',{},v),el('span',{},k));
  const short=v=>Math.abs(v)>=1e6?num(v/1e6,1)+' tr':Math.abs(v)>=1e3?num(v/1e3,0)+' N':num(v,Math.abs(v)<10&&v%1?1:0);
  function reg(sel,fn){jobs[sel]=fn;fn()}
  function canvas(sel){const b=$(sel);if(!b)return null;b.replaceChildren();const W=Math.max(b.clientWidth,260),H=b.clientHeight||240;const v=s('svg',{viewBox:`0 0 ${W} ${H}`,width:W,height:H,role:'img'});b.append(v);return{v,W,H,b}}
  function legend(b,items){if(items.length<2)return;b.prepend(el('div',{class:'legend'},...items.map(i=>el('span',{},el('i',{class:(i.dash?'dash ':'')+(i.dot?'dot':''),style:`--c:${i.c}`}),i.name))))}

  function line(sel,o){reg(sel,()=>{
    const c=canvas(sel);if(!c)return;const{v,W,H,b}=c,P=o.colors||[css('--s1'),css('--s2'),css('--s3'),css('--s4')];
    const all=[...o.series.flatMap(z=>z.values),...(o.band?[...o.band.lo,...o.band.hi]:[])].filter(x=>x!=null);
    const lo=Math.min(0,...all),ticks=nice(Math.max(...all),lo),ymax=ticks.at(-1),ymin=Math.min(ticks[0],lo);
    const L=58,R=14,T=10,Bt=26,iw=W-L-R,ih=H-T-Bt,n=o.x.length,X=i=>L+(n>1?i*iw/(n-1):iw/2),Y=y=>T+ih-(y-ymin)/(ymax-ymin||1)*ih;
    ticks.forEach(t=>{v.append(s('line',{x1:L,x2:W-R,y1:Y(t),y2:Y(t),stroke:css('--grid')}),text(L-8,Y(t)+4,short(t),{'text-anchor':'end'}))});
    const every=Math.ceil(n/Math.max(2,Math.floor(iw/70)));
    o.x.forEach((x,i)=>{if(i%every===0||i===n-1&&n<8)v.append(text(X(i),H-8,x,{'text-anchor':'middle'}))});
    if(o.band){const idx=o.x.map((_,i)=>i).filter(i=>o.band.lo[i]!=null);
      if(idx.length){const d=idx.map((i,k)=>`${k?'L':'M'}${X(i)},${Y(o.band.hi[i])}`).join('')+idx.slice().reverse().map(i=>`L${X(i)},${Y(o.band.lo[i])}`).join('')+'Z';
      v.append(s('path',{d,fill:css('--s2'),opacity:.16}))}}
    const items=[];
    o.series.forEach((z,k)=>{const col=P[k];items.push({name:z.name,c:col,dash:z.dash});let d='',pen=false;
      z.values.forEach((y,i)=>{if(y==null){pen=z.dash?pen:false;return}d+=`${pen?'L':'M'}${X(i)},${Y(y)}`;pen=true});
      v.append(s('path',{d,fill:'none',stroke:col,'stroke-width':2,'stroke-linejoin':'round','stroke-dasharray':z.dash?'5 4':''}));
      if(z.dots)z.values.forEach((y,i)=>{if(y!=null)v.append(s('circle',{cx:X(i),cy:Y(y),r:3.5,fill:col,stroke:css('--card'),'stroke-width':1.5}))});
    });
    if(o.band)items.push({name:o.band.name,c:css('--s2')});
    legend(b,items);
    if(o.marker!=null){const m=Math.min(n-1,Math.max(0,o.marker));v.append(s('line',{x1:X(m),x2:X(m),y1:T,y2:T+ih,stroke:css('--ink'),'stroke-dasharray':'3 3'}),text(X(m)+6,T+12,o.markerLabel||'Ngưỡng',{fill:css('--ink')}))}
    const hair=s('line',{y1:T,y2:T+ih,stroke:css('--muted'),visibility:'hidden'});v.append(hair);
    const hit=s('rect',{x:L,y:T,width:iw,height:ih,fill:'transparent'});v.append(hit);
    hit.onpointermove=e=>{const r=v.getBoundingClientRect(),i=Math.max(0,Math.min(n-1,Math.round((e.clientX-r.left-L)/iw*(n-1))));
      hair.setAttribute('x1',X(i));hair.setAttribute('x2',X(i));hair.setAttribute('visibility','visible');
      const rows=[el('div',{class:'th'},o.x[i])];o.series.forEach((z,k)=>{if(z.values[i]!=null)rows.push(tipRow(z.name,o.fmt(z.values[i]),P[k]))});
      if(o.band&&o.band.lo[i]!=null)rows.push(tipRow(o.band.name,`${o.fmt(o.band.lo[i])} – ${o.fmt(o.band.hi[i])}`));showTip(e,rows)};
    hit.onpointerleave=()=>{hair.setAttribute('visibility','hidden');hide()};
  })}

  function bars(sel,data,o){const box=$(sel);if(!box)return;
    reg(sel,()=>{const max=Math.max(...data.map(d=>Math.abs(d.value)),1e-9),neg=data.some(d=>d.value<0);
      box.replaceChildren(...data.map(d=>{const w=Math.abs(d.value)/max*(neg?50:100);
        const f=el('div',{class:'fill'+(d.value<0?' neg':''),style:`width:${w}%;${neg?(d.value<0?`margin-left:${50-w}%`:'margin-left:50%'):''}`});
        const row=el('div',{class:'bar',tabindex:0},el('span',{class:'bl',title:d.label},d.label),el('div',{class:'track'},f),el('b',{},o.fmt(d.value)));
        if(o.note){row.onpointermove=e=>showTip(e,[el('div',{class:'th'},d.label),tipRow(o.note(d),o.fmt(d.value))]);row.onpointerleave=hide}
        return row}));
    })}

  function waterfall(sel,rows,base,o={}){reg(sel,()=>{
    const c=canvas(sel);if(!c)return;const{v,W}=c,u=o.unit||'';const h=26,H=(rows.length+2)*h+8;v.setAttribute('viewBox',`0 0 ${W} ${H}`);v.setAttribute('height',H);c.b.style.height=H+'px';
    const LW=Math.min(W*.44,250),L=LW+6,R=64,iw=W-L-R;let cum=base;const pts=[base];rows.forEach(r=>{cum+=r.value;pts.push(cum)});
    const lo=Math.min(...pts),hi=Math.max(...pts),X=x=>L+(x-lo)/((hi-lo)||1)*iw;
    const label=(y,t,b)=>{const mx=Math.floor(LW/6.3),n=text(LW,y,t.length>mx?t.slice(0,mx-1)+'…':t,{'text-anchor':'end',fill:css(b?'--ink':'--muted'),'font-weight':b?600:400});n.append(s('title',{},t));v.append(n)};
    let y=4;const end=H-h;
    label(y+17,'Mức nền',true);v.append(s('line',{x1:X(base),x2:X(base),y1:y,y2:end+h-8,stroke:css('--grid')}),text(X(base)+6,y+17,num(base,2)+u,{fill:css('--ink')}));y+=h;
    cum=base;rows.forEach(r=>{const a=cum,b=cum+r.value,x=Math.min(X(a),X(b)),w=Math.max(2,Math.abs(X(a)-X(b))),col=r.value>=0?css('--up'):css('--down');
      label(y+17,r.label);v.append(s('rect',{x,y:y+5,width:w,height:h-11,rx:3,fill:col}));
      const tx=Math.max(X(a),X(b))+6,right=tx+50>W;v.append(text(right?Math.min(X(a),X(b))-6:tx,y+17,(r.value>0?'+':'')+num(r.value,2),{'text-anchor':right?'end':'start',fill:css('--ink')}));cum=b;y+=h});
    label(y+17,'Dự đoán',true);const far=X(cum)+6+(num(cum,2)+u).length*7>W;v.append(s('rect',{x:X(cum)-1.5,y:y+3,width:3,height:h-7,fill:css('--ink')}),text(far?X(cum)-6:X(cum)+6,y+17,num(cum,2)+u,{fill:css('--ink'),'font-weight':600,'text-anchor':far?'end':'start'}));
  })}

  function scatter(sel,groups,o){reg(sel,()=>{
    const c=canvas(sel);if(!c)return;const{v,W,H,b}=c,P=o.colors||[css('--s1'),css('--s2'),css('--s3'),css('--s4')],pts=groups.flatMap(g=>g.points);
    const xs=nice(Math.max(...pts.map(p=>p.x)),Math.min(0,...pts.map(p=>p.x))),ys=nice(Math.max(...pts.map(p=>p.y)),Math.min(...pts.map(p=>p.y)));
    const L=46,R=14,T=10,Bt=42,iw=W-L-R,ih=H-T-Bt,X=x=>L+(x-xs[0])/(xs.at(-1)-xs[0])*iw,Y=y=>T+ih-(y-ys[0])/(ys.at(-1)-ys[0])*ih;
    ys.forEach(t=>v.append(s('line',{x1:L,x2:W-R,y1:Y(t),y2:Y(t),stroke:css('--grid')}),text(L-8,Y(t)+4,num(t,1),{'text-anchor':'end'})));
    xs.forEach(t=>v.append(text(X(t),T+ih+16,num(t,Math.abs(t)<10&&t%1?1:0),{'text-anchor':'middle'})));
    v.append(text(L+iw/2,H-6,o.xlabel,{'text-anchor':'middle'}),text(14,T+ih/2,o.ylabel,{'text-anchor':'middle',transform:`rotate(-90 14 ${T+ih/2})`}));
    groups.forEach((g,k)=>g.points.forEach(p=>{const d=s('circle',{cx:X(p.x),cy:Y(p.y),r:o.r||5,fill:P[k],stroke:css('--card'),'stroke-width':1.5,tabindex:0,style:'cursor:pointer'});
      d.onpointermove=e=>showTip(e,[el('div',{class:'th'},p.label),tipRow(o.xlabel,num(p.x,1)),tipRow(o.ylabel,num(p.y,2))]);d.onpointerleave=hide;d.onclick=()=>o.onClick&&o.onClick(p);v.append(d)}));
    legend(b,groups.map((g,k)=>({name:g.name,c:P[k],dot:true})));
  })}
  let t;addEventListener('resize',()=>{clearTimeout(t);t=setTimeout(()=>Object.values(jobs).forEach(f=>f()),150)});
  return{line,bars,waterfall,scatter,redraw:()=>Object.values(jobs).forEach(f=>f())};
})();
