"""HTML dashboard generator."""
from __future__ import annotations

import json
from typing import Any, Dict

_TEMPLATE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Storytelling Data Lake — __ENTITY__</title>
<style>
  :root {
    --navy: #1E2761; --ice: #CADCFC; --accent: #F96167; --green: #2C9F5F;
    --amber: #B58A00; --grey: #94A3B8; --bg: #F5F7FA; --card: #FFFFFF;
    --text: #0F172A; --muted: #475569; --border: #E2E8F0;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }
  header { background: var(--navy); color: white; padding: 24px 32px; display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center; }
  header .eyebrow { font-size: 11px; letter-spacing: 4px; text-transform: uppercase; color: var(--ice); margin-bottom: 4px; }
  header h1 { margin: 0; font-size: 28px; font-weight: 700; }
  header .meta { font-size: 13px; color: var(--ice); margin-top: 6px; }
  .decision-badge { padding: 14px 20px; border-radius: 8px; min-width: 220px; text-align: center; font-weight: 700; letter-spacing: 1px; }
  .decision-badge.continue { background: var(--green); color: white; }
  .decision-badge.watch    { background: var(--amber); color: white; }
  .decision-badge.pause    { background: #C2410C; color: white; }
  .decision-badge.terminate{ background: var(--accent); color: white; }
  .decision-badge .label { font-size: 11px; opacity: 0.8; letter-spacing: 3px; }
  .decision-badge .name  { font-size: 22px; margin-top: 4px; text-transform: uppercase; }
  .decision-badge .why   { font-size: 11px; opacity: 0.85; margin-top: 6px; font-weight: 400; letter-spacing: 0; }
  main { max-width: 1280px; margin: 24px auto; padding: 0 24px; }
  .toolbar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 20px; padding: 14px 18px; background: var(--card); border: 1px solid var(--border); border-radius: 8px; }
  .toolbar input[type=search] { flex: 1; min-width: 220px; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px; }
  .toolbar select { padding: 7px 12px; border: 1px solid var(--border); border-radius: 6px; background: white; font-size: 13px; cursor: pointer; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .kpi { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; border-left: 3px solid var(--navy); }
  .kpi .v { font-size: 26px; font-weight: 700; color: var(--navy); }
  .kpi .l { font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: var(--muted); margin-top: 4px; }
  .tabs { display: flex; gap: 4px; border-bottom: 2px solid var(--border); margin-bottom: 16px; }
  .tab { padding: 10px 18px; cursor: pointer; font-size: 14px; font-weight: 600; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -2px; }
  .tab.active { color: var(--navy); border-bottom-color: var(--accent); }
  .panel { display: none; }
  .panel.active { display: block; }
  .layer-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
  .layer-head { padding: 14px 18px; display: flex; align-items: center; gap: 12px; cursor: pointer; user-select: none; }
  .layer-head:hover { background: #FBFCFD; }
  .layer-num { width: 32px; height: 32px; border-radius: 16px; background: var(--navy); color: white; display: grid; place-items: center; font-weight: 700; font-size: 14px; flex-shrink: 0; }
  .layer-title { flex: 1; font-weight: 600; font-size: 15px; }
  .layer-stats { font-size: 12px; color: var(--muted); display: flex; gap: 10px; }
  .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
  .pill.green { background: #E6F5EE; color: var(--green); }
  .pill.red   { background: #FDE7E8; color: var(--accent); }
  .pill.grey  { background: #ECEFF3; color: var(--muted); }
  .layer-body { padding: 0 18px 18px 62px; display: none; }
  .layer-card.open .layer-body { display: block; }
  .layer-card.open .arrow { transform: rotate(90deg); }
  .arrow { width: 0; height: 0; border-style: solid; border-width: 5px 0 5px 7px; border-color: transparent transparent transparent var(--muted); transition: transform 0.15s; }
  .subcat { margin-bottom: 14px; }
  .subcat-name { font-size: 13px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
  .fact { border-left: 3px solid var(--grey); padding: 8px 12px; margin-bottom: 6px; background: #FAFBFD; border-radius: 0 4px 4px 0; font-size: 13px; }
  .fact.green { border-left-color: var(--green); background: #F4FAF7; }
  .fact.red   { border-left-color: var(--accent); background: #FEF6F6; }
  .fact .src { font-size: 11px; color: var(--muted); margin-top: 4px; }
  .fact .src a { color: var(--navy); text-decoration: none; }
  .fact .meta { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .red-cat { color: var(--accent); font-weight: 600; }
  .timeline { position: relative; padding-left: 24px; }
  .timeline::before { content: ""; position: absolute; left: 7px; top: 0; bottom: 0; width: 2px; background: var(--border); }
  .tl-item { position: relative; padding-bottom: 18px; }
  .tl-item::before { content: ""; position: absolute; left: -22px; top: 4px; width: 12px; height: 12px; border-radius: 6px; background: var(--navy); border: 2px solid white; box-shadow: 0 0 0 1px var(--border); }
  .tl-date { font-size: 12px; color: var(--accent); font-weight: 700; letter-spacing: 1px; }
  .tl-text { font-size: 14px; margin-top: 2px; }
  .tl-meta { font-size: 11px; color: var(--muted); margin-top: 3px; }
  table.facts { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; overflow: hidden; border: 1px solid var(--border); font-size: 13px; }
  table.facts th { background: var(--navy); color: white; text-align: left; padding: 10px 12px; font-size: 11px; letter-spacing: 1px; text-transform: uppercase; }
  table.facts td { padding: 10px 12px; border-top: 1px solid var(--border); vertical-align: top; }
  table.facts tr.hidden { display: none; }
  footer { margin-top: 32px; padding: 16px 24px; text-align: center; font-size: 12px; color: var(--muted); }
</style>
</head>
<body>
<header>
  <div>
    <div class="eyebrow">Storytelling Data Lake · v0.2</div>
    <h1>__ENTITY_TITLE__</h1>
    <div class="meta">Сгенерировано: __GENERATED_AT__</div>
  </div>
  <div class="decision-badge __DECISION__" title="__RATIONALE__">
    <div class="label">Recommendation</div>
    <div class="name">__DECISION__</div>
    <div class="why">__RATIONALE__</div>
  </div>
</header>
<main>
  <div class="kpis">
    <div class="kpi"><div class="v">__COVERAGE__%</div><div class="l">Coverage</div></div>
    <div class="kpi"><div class="v">__FACT_COUNT__</div><div class="l">Facts</div></div>
    <div class="kpi" style="border-left-color:var(--green)"><div class="v">__GREEN_COUNT__</div><div class="l">Green flags</div></div>
    <div class="kpi" style="border-left-color:var(--accent)"><div class="v">__RED_COUNT__</div><div class="l">Red flags</div></div>
    <div class="kpi" style="border-left-color:var(--grey)"><div class="v">__GREY_COUNT__</div><div class="l">Grey</div></div>
    <div class="kpi"><div class="v">__FRESHNESS__ дн.</div><div class="l">Freshness P50</div></div>
  </div>
  <div class="tabs">
    <div class="tab active" data-panel="story">По слоям</div>
    <div class="tab" data-panel="timeline">Таймлайн</div>
    <div class="tab" data-panel="facts">Все факты</div>
  </div>
  <div class="panel active" id="panel-story">
    <div class="toolbar">
      <input type="search" id="story-search" placeholder="Поиск…">
      <select id="story-flag-filter"><option value="">Все флаги</option><option value="green">🟢 Green</option><option value="red">🔴 Red</option><option value="grey">⚪ Grey</option></select>
    </div>
    <div id="story-container"></div>
  </div>
  <div class="panel" id="panel-timeline">
    <div class="toolbar">
      <input type="search" id="tl-search" placeholder="Поиск по событиям…">
      <select id="tl-sort"><option value="asc">Старые сверху</option><option value="desc">Новые сверху</option></select>
    </div>
    <div class="timeline" id="timeline-container"></div>
  </div>
  <div class="panel" id="panel-facts">
    <div class="toolbar">
      <input type="search" id="facts-search" placeholder="Поиск…">
      <select id="facts-flag-filter"><option value="">Все флаги</option><option value="green">Green</option><option value="red">Red</option><option value="grey">Grey</option></select>
      <select id="facts-source-filter"><option value="">Все источники</option><option value="online_interview">online_interview</option><option value="offline_interview">offline_interview</option><option value="online_research">online_research</option><option value="archival">archival</option></select>
    </div>
    <table class="facts"><thead><tr><th>Слой</th><th>Подкатегория</th><th>Источник</th><th>Флаг</th><th>Текст</th><th>URL</th></tr></thead><tbody id="facts-tbody"></tbody></table>
  </div>
</main>
<footer>Последнее обновление: __GENERATED_AT__ · human_approval_required: true</footer>
<script>
const PAYLOAD = __PAYLOAD_JSON__;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const LAYER_NUM = (() => { const m = {}; Object.keys(PAYLOAD.story).forEach((n,i)=>m[n]=i+1); return m; })();
$$(".tab").forEach(t => t.addEventListener("click", () => {
  $$(".tab,.panel").forEach(x=>x.classList.remove("active"));
  t.classList.add("active"); $("#panel-"+t.dataset.panel).classList.add("active");
}));
function renderStory() {
  const cont = $("#story-container"); cont.innerHTML = "";
  const fls = {};
  PAYLOAD.facts.forEach(f => {
    const ln = Object.keys(PAYLOAD.story).find(n=>Object.keys(PAYLOAD.story[n]).includes(f.subcategory))||`Layer ${f.layer}`;
    (fls[ln]=fls[ln]||{});(fls[ln][f.subcategory]=fls[ln][f.subcategory]||[]).push(f);
  });
  Object.keys(PAYLOAD.story).forEach(ln => {
    let g=0,r=0,gr=0;
    Object.values(fls[ln]||{}).forEach(a=>a.forEach(f=>{if(f.flag==="green")g++;else if(f.flag==="red")r++;else gr++;}));
    const card=document.createElement("div"); card.className="layer-card"; card.dataset.layerName=ln;
    card.innerHTML=`<div class="layer-head"><div class="arrow"></div><div class="layer-num">${LAYER_NUM[ln]||"?"}</div><div class="layer-title">${ln}</div><div class="layer-stats"><span class="pill green">🟢 ${g}</span><span class="pill red">🔴 ${r}</span><span class="pill grey">⚪ ${gr}</span></div></div><div class="layer-body"></div>`;
    const body=card.querySelector(".layer-body");
    Object.keys(PAYLOAD.story[ln]).forEach(sub=>{
      const sd=document.createElement("div"); sd.className="subcat";
      sd.innerHTML=`<div class="subcat-name">${sub}</div>`;
      const arr=(fls[ln]||{})[sub]||[];
      if(!arr.length){sd.innerHTML+=`<div class="fact grey"><em>(нет фактов)</em></div>`;}
      else arr.forEach(f=>{
        const fe=document.createElement("div"); fe.className="fact "+f.flag;
        fe.dataset.flag=f.flag; fe.dataset.text=(f.text||"").toLowerCase();
        fe.innerHTML=`<div>${f.text}</div><div class="meta"><strong>${f.source_type}</strong> · conf ${(f.confidence||0).toFixed(2)}${f.red_flag_category?' · <span class="red-cat">'+f.red_flag_category+"</span>":""}</div><div class="src"><a href="${f.source_url}" target="_blank">${f.source_url}</a></div>`;
        sd.appendChild(fe);
      });
      body.appendChild(sd);
    });
    card.querySelector(".layer-head").addEventListener("click",()=>card.classList.toggle("open"));
    cont.appendChild(card);
  });
  cont.querySelector(".layer-card")?.classList.add("open");
}
function applyStory(){const q=$("#story-search").value.toLowerCase();const fl=$("#story-flag-filter").value;$$(".fact").forEach(el=>{el.style.display=((!q||(el.dataset.text||"").includes(q))&&(!fl||el.dataset.flag===fl))?"":"none";});}
$("#story-search").addEventListener("input",applyStory);$("#story-flag-filter").addEventListener("change",applyStory);
function renderTimeline(){
  const cont=$("#timeline-container"); cont.innerHTML="";
  let items=[...PAYLOAD.timeline];
  const ord=$("#tl-sort").value; items.sort((a,b)=>ord==="asc"?a.date.localeCompare(b.date):b.date.localeCompare(a.date));
  const q=$("#tl-search").value.toLowerCase();
  items.filter(e=>!q||e.text.toLowerCase().includes(q)).forEach(e=>{
    const d=document.createElement("div"); d.className="tl-item";
    d.innerHTML=`<div class="tl-date">${e.date}</div><div class="tl-text">${e.text}</div><div class="tl-meta">${e.layer} · ${e.entity} · <a href="${e.source}" target="_blank">источник</a></div>`;
    cont.appendChild(d);
  });
  if(!items.length) cont.innerHTML='<div style="color:var(--muted);padding:16px">Нет датируемых событий.</div>';
}
$("#tl-search").addEventListener("input",renderTimeline);$("#tl-sort").addEventListener("change",renderTimeline);
function renderFacts(){
  const tbody=$("#facts-tbody"); tbody.innerHTML="";
  const layers=Object.keys(PAYLOAD.story);
  PAYLOAD.facts.forEach(f=>{
    const tr=document.createElement("tr");
    const ln=layers.find(n=>Object.keys(PAYLOAD.story[n]).includes(f.subcategory))||`Layer ${f.layer}`;
    tr.dataset.flag=f.flag; tr.dataset.source=f.source_type; tr.dataset.text=(f.text||"").toLowerCase();
    tr.innerHTML=`<td>${LAYER_NUM[ln]||"?"}. ${ln}</td><td>${f.subcategory}</td><td><code style="font-size:11px">${f.source_type}</code></td><td><span class="pill ${f.flag}">${f.flag}</span>${f.red_flag_category?'<br><small class="red-cat">'+f.red_flag_category+"</small>":""}</td><td>${f.text}</td><td><a href="${f.source_url}" target="_blank">↗</a></td>`;
    tbody.appendChild(tr);
  });
}
function applyFacts(){
  const q=$("#facts-search").value.toLowerCase(),fl=$("#facts-flag-filter").value,src=$("#facts-source-filter").value;
  $$("#facts-tbody tr").forEach(tr=>{tr.classList.toggle("hidden",!(!q||tr.dataset.text.includes(q))||!(!fl||tr.dataset.flag===fl)||!(!src||tr.dataset.source===src));});
}
["#facts-search","#facts-flag-filter","#facts-source-filter"].forEach(s=>$(s).addEventListener("input",applyFacts));
renderStory(); renderTimeline(); renderFacts();
</script>
</body></html>"""


def render_html(payload: Dict[str, Any], entity_id: str) -> str:
    decision = payload["decision"].get("recommendation", "watch")
    rationale = payload["decision"].get("rationale", "").replace('"', "&quot;")
    m = payload["metrics"]
    return (
        _TEMPLATE
        .replace("__ENTITY__", entity_id)
        .replace("__ENTITY_TITLE__", entity_id.replace("-", " ").title())
        .replace("__GENERATED_AT__", payload["generated_at"][:19].replace("T", " "))
        .replace("__DECISION__", decision)
        .replace("__RATIONALE__", rationale)
        .replace("__COVERAGE__", str(m.get("coverage_pct", 0)))
        .replace("__FACT_COUNT__", str(m.get("fact_count", 0)))
        .replace("__GREEN_COUNT__", str(m.get("green_count", 0)))
        .replace("__RED_COUNT__", str(m.get("red_count", 0)))
        .replace("__GREY_COUNT__", str(m.get("grey_count", 0)))
        .replace("__FRESHNESS__", str(m.get("freshness_days_p50", "—")))
        .replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=False))
    )


def export_html(payload: Dict[str, Any], entity_id: str, out_path: str) -> None:
    import logging
    html = render_html(payload, entity_id)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    logging.getLogger(__name__).info("Dashboard saved → %s", out_path)
