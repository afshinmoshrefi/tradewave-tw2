#!/usr/bin/env python3
"""Generate the interactive "Try it" API playground (a single static page).

A logged-in developer pastes their tw_live_ key, picks an endpoint, fills params, and runs a
LIVE call against the public API (api.tradewave.ai/v1) straight from the browser. The page
renders the PatternCard response and shows the exact curl / Python / JavaScript for the request.
BYOK: the key stays in the browser (optional localStorage), sent only as Authorization: Bearer.

Output: site/api_playground/out/index.html  (deployed at developers.tradewave.ai/playground/).
Run:  ./venv/bin/python site/api_playground/generate_playground.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT_DIR = HERE / "out"
sys.path.insert(0, str(REPO / "site" / "lib"))
sys.path.insert(0, str(REPO / "site" / "api_docs"))
import portal_urls          # noqa: E402
import portal_seo          # noqa: E402
import generate_api_docs as gad  # noqa: E402

API_BASE = portal_urls.API_BASE
CONSOLE_URL = portal_urls.CONSOLE_URL
DOCS_URL = portal_urls.DOCS_URL

PLAYGROUND_CSS = """
.pg-wrap{max-width:1100px;margin:0 auto;padding:0 24px 60px;}
.pg-grid{display:grid;grid-template-columns:380px 1fr;gap:24px;align-items:start;}
@media(max-width:880px){.pg-grid{grid-template-columns:1fr;}}
.pg-panel{border:1px solid var(--border);border-radius:12px;background:var(--bg-alt);padding:20px 22px;}
.pg-panel h3{margin:0 0 14px;font-size:15px;color:#fff;}
.pg-field{margin-bottom:14px;}
.pg-field label{display:block;font-size:12px;color:var(--text-muted);margin-bottom:5px;font-weight:600;letter-spacing:.02em;}
.pg-field input,.pg-field select,.pg-field textarea{
  width:100%;box-sizing:border-box;background:var(--bg);border:1px solid var(--border);
  border-radius:8px;color:#fff;padding:9px 11px;font-size:13px;font-family:inherit;}
.pg-field input:focus,.pg-field select:focus{outline:none;border-color:var(--accent);}
.pg-field .hint{font-size:11px;color:var(--text-muted);margin-top:4px;}
.pg-row{display:flex;gap:8px;align-items:center;}
.pg-btn{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:11px 18px;
  font-size:14px;font-weight:700;cursor:pointer;width:100%;transition:opacity .15s;}
.pg-btn:hover{opacity:.9;} .pg-btn:disabled{opacity:.5;cursor:not-allowed;}
.pg-key-warn{font-size:11px;color:var(--text-muted);margin-top:6px;line-height:1.5;}
.pg-method{display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:5px;margin-right:8px;}
.pg-method.get{background:#0e3b2e;color:#34d399;} .pg-method.post{background:#3b2e0e;color:#fbbf24;}
.pg-url{font-family:ui-monospace,monospace;font-size:12px;color:var(--text-dim);word-break:break-all;margin:6px 0 0;}
.pg-status{font-size:13px;font-weight:700;margin-bottom:10px;}
.pg-status.ok{color:#34d399;} .pg-status.err{color:#f87171;} .pg-status.warn{color:#fbbf24;}
.pg-empty{color:var(--text-muted);font-size:14px;padding:30px 0;text-align:center;}
.sc{border:1px solid var(--border);border-radius:10px;padding:16px 18px;margin-bottom:14px;background:var(--bg);}
.sc-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;}
.sc-sym{font-size:18px;font-weight:800;color:#fff;}
.sc-badge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:6px;}
.sc-badge.bullish{background:#0e3b2e;color:#34d399;} .sc-badge.bearish{background:#3b1414;color:#f87171;}
.sc-badge.neutral{background:#2a2a33;color:#9ca3af;}
.sc-headline{margin:8px 0 4px;color:#e5e7eb;font-size:14px;font-weight:600;}
.sc-verdict{color:var(--text-dim);font-size:13px;margin:0 0 12px;}
.sc-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:10px;margin:10px 0;}
.sc-stat{background:var(--bg-alt);border-radius:8px;padding:8px 10px;}
.sc-stat .k{font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;}
.sc-stat .v{font-size:15px;font-weight:700;color:#fff;margin-top:2px;}
.sc-edge{font-size:11px;color:var(--text-muted);margin-top:2px;}
.sc-years{display:flex;flex-wrap:wrap;gap:4px;margin:10px 0;}
.sc-yr{font-size:10px;padding:2px 6px;border-radius:4px;font-weight:600;}
.sc-yr.win{background:#0e3b2e;color:#34d399;} .sc-yr.loss{background:#3b1414;color:#f87171;}
.sc-ticket{background:var(--bg-alt);border-radius:8px;padding:10px 12px;margin-top:10px;font-size:12px;color:var(--text-dim);}
.sc-ticket code{color:#fff;}
.sc-disc{font-size:10px;color:var(--text-muted);margin-top:10px;line-height:1.5;}
.pg-raw{margin-top:16px;} .pg-raw summary{cursor:pointer;color:var(--text-dim);font-size:13px;}
.pg-raw pre{max-height:340px;overflow:auto;margin-top:8px;}
.pg-snippet{margin-top:24px;}
"""

# ---- endpoint registry (the playground's menu). Mirrors api/openapi.yaml. ----
# Each: method, path (with {param}), params [{name,in,placeholder,default,hint}], returns_cards
ENDPOINTS_JS = """
const ENDPOINTS = {
  "daily-pick": { method:"GET", path:"/daily-pick", label:"Daily pick (a PatternCard + track record)", cards:true, params:[] },
  "scan": { method:"GET", path:"/scan", label:"Scan - find best opportunities (flagship)", cards:true, params:[
    {name:"markets", in:"query", ph:"2,11 or gold,etfs", hint:"csv of ids or names; blank = liquid-equities core in scope"},
    {name:"window", in:"query", ph:"now", def:"now", hint:"now | next_2_weeks | next_month | YYYY-MM-DD..YYYY-MM-DD"},
    {name:"direction", in:"query", ph:"long | short", hint:"optional"},
    {name:"min_win_rate", in:"query", ph:"0.6", hint:"0..1, optional"},
    {name:"min_years", in:"query", ph:"5", hint:"optional"},
    {name:"rank_by", in:"query", ph:"sharpe", def:"sharpe", hint:"edge|win_rate|sharpe|ml|avg_return"},
    {name:"limit", in:"query", ph:"10", def:"10", hint:"tier-capped"} ]},
  "analyze": { method:"GET", path:"/analyze/{symbol}", label:"Analyze a symbol (flagship deep-dive)", cards:true, params:[
    {name:"symbol", in:"path", ph:"DOV", def:"DOV", hint:"ticker"},
    {name:"market", in:"query", ph:"2", hint:"optional id; resolved if unique"},
    {name:"direction", in:"query", ph:"long | short", hint:"optional"},
    {name:"days_out", in:"query", ph:"30", hint:"optional hold length"} ]},
  "markets": { method:"GET", path:"/markets", label:"List markets in your scope", cards:false, params:[] },
  "opportunities": { method:"GET", path:"/opportunities", label:"Opportunities (single-date primitive)", cards:false, params:[
    {name:"market", in:"query", ph:"2", def:"2", hint:"market id (required)"},
    {name:"direction", in:"query", ph:"long | short", hint:"optional"},
    {name:"min_win_rate", in:"query", ph:"0.6", hint:"optional"},
    {name:"limit", in:"query", ph:"10", hint:"optional"} ]},
  "patterns": { method:"GET", path:"/patterns/{market}/{symbol}", label:"Seasonal pattern stats", cards:false, params:[
    {name:"market", in:"path", ph:"2", def:"2"}, {name:"symbol", in:"path", ph:"DOV", def:"DOV"} ]},
  "track-record": { method:"GET", path:"/daily-pick/track-record", label:"Daily-pick realized track record", cards:false, params:[] },
  "score": { method:"POST", path:"/score", label:"ML score setups (POST)", cards:false, body:true, params:[] }
};
const DEFAULT_BODY = JSON.stringify({market:"2",opportunities:[{symbol:"DOV",date:"",days_out:30,direction:"long"}]}, null, 2);
"""

RUNNER_JS = r"""
const API_BASE = "__API_BASE__";
const CONSOLE_URL = "__CONSOLE_URL__";
const $ = (id) => document.getElementById(id);
const KEY_LS = "tw_pg_key";

function curEndpoint(){ return ENDPOINTS[$("ep").value]; }

function renderParams(){
  const ep = curEndpoint();
  const box = $("params"); box.innerHTML = "";
  (ep.params||[]).forEach(p => {
    const wrap = document.createElement("div"); wrap.className = "pg-field";
    wrap.innerHTML = `<label>${p.name}${p.in==="path"?' <span style="color:#f87171">*</span>':''}</label>
      <input data-pname="${p.name}" data-pin="${p.in}" placeholder="${p.ph||''}" value="${p.def||''}">
      ${p.hint?`<div class="hint">${p.hint}</div>`:''}`;
    box.appendChild(wrap);
  });
  if(ep.body){
    const wrap = document.createElement("div"); wrap.className="pg-field";
    wrap.innerHTML = `<label>request body (JSON)</label><textarea id="pgbody" rows="7" spellcheck="false">${DEFAULT_BODY}</textarea>`;
    box.appendChild(wrap);
  }
  updatePreview();
}

function buildRequest(){
  const ep = curEndpoint();
  let path = ep.path;
  const qs = [];
  document.querySelectorAll('[data-pname]').forEach(inp => {
    const v = inp.value.trim(); if(!v) return;
    if(inp.dataset.pin === "path") path = path.replace('{'+inp.dataset.pname+'}', encodeURIComponent(v));
    else qs.push(encodeURIComponent(inp.dataset.pname)+"="+encodeURIComponent(v));
  });
  // leftover unfilled path params -> placeholder so the URL still reads sensibly
  path = path.replace(/\{(\w+)\}/g, (_,n)=>':'+n);
  const url = API_BASE + path + (qs.length?("?"+qs.join("&")):"");
  let body = null;
  if(ep.body){ const t = $("pgbody"); body = t ? t.value : null; }
  return { method: ep.method, url, body };
}

function snippet(kind, req, key){
  const k = key || "tw_live_YOUR_KEY";
  if(kind==="curl"){
    let s = `curl ${req.method==="POST"?"-X POST ":""}"${req.url}" \\\n  -H "Authorization: Bearer ${k}"`;
    if(req.body) s += ` \\\n  -H "Content-Type: application/json" \\\n  -d '${req.body.replace(/\n\s*/g,' ')}'`;
    return s;
  }
  if(kind==="python"){
    let s = `import requests\n\nr = requests.${req.method.toLowerCase()}(\n    "${req.url}",\n    headers={"Authorization": "Bearer ${k}"}`;
    if(req.body) s += `,\n    json=${req.body.replace(/\n/g,'\n    ')}`;
    s += `,\n)\nprint(r.status_code)\nprint(r.json())`;
    return s;
  }
  // javascript
  let opts = `{\n    method: "${req.method}",\n    headers: { "Authorization": "Bearer ${k}"`;
  if(req.body) opts += `, "Content-Type": "application/json"`;
  opts += ` }`;
  if(req.body) opts += `,\n    body: JSON.stringify(${req.body})`;
  opts += `\n  }`;
  return `const r = await fetch("${req.url}", ${opts});\nconst data = await r.json();\nconsole.log(data);`;
}

function updatePreview(){
  const req = buildRequest();
  const ep = curEndpoint();
  $("reqline").innerHTML = `<span class="pg-method ${ep.method.toLowerCase()}">${ep.method}</span><span class="pg-url">${req.url}</span>`;
  const key = ($("key").value||"").trim();
  ["curl","python","javascript"].forEach(kind => { $("snip-"+kind).textContent = snippet(kind, req, key); });
}

function fmtPct(x){ return (x==null)?"-":(x*1).toFixed(2).replace(/\.00$/,'')+"%"; }
function fmtProb(x){ return (x==null)?"-":Math.round(x*100)+"%"; }

// Escape EVERY value that comes from the API response before inserting it as HTML. The
// gateway is first-party but its card fields (symbol, names, notes) are treated as untrusted
// in the browser - this page is where users paste a live API key, so no reflected/stored XSS.
function esc(v){
  return String(v==null?"":v).replace(/[&<>"']/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c];
  });
}

function renderCard(c){
  if(!c || typeof c!=="object") return "";
  const sig = esc((c.bias||"").toLowerCase());
  const s = c.stats||{}, r = c.receipts||{}, ml = c.ml;
  let years = "";
  (r.per_year||[]).slice(0,15).forEach(y => { years += `<span class="sc-yr ${esc(y.result)}">${esc(y.year)} ${fmtPct(y.return_pct)}</span>`; });
  let mlrow = "";
  if(ml){ mlrow = `<div class="sc-stat"><div class="k">ML win prob</div><div class="v">${fmtProb(ml.ml_win_prob)}</div></div>`; }
  let ticket = "";
  const t = (c.next_step||{}).order_ticket;
  if(t){ ticket = `<div class="sc-ticket"><strong>Order ticket:</strong> <code>${esc(t.side)} ${esc(t.symbol)} ${esc(t.type)} ${esc(t.time_in_force)}</code>, enter ~${esc(t.suggested_entry_date||'-')}, exit ~${esc(t.suggested_exit_date||'-')}. ${esc(t.note||'')}</div>`; }
  return `<div class="sc">
    <div class="sc-head"><div><span class="sc-sym">${esc(c.symbol||'?')}</span> <span style="color:var(--text-muted);font-size:12px">${esc((c.market||{}).name||'')} &middot; ${esc(c.direction||'')}</span></div>
      <span class="sc-badge ${sig}">${esc(c.bias||'')}</span></div>
    <div class="sc-headline">${esc(c.headline||'')}</div>
    <div class="sc-verdict">${esc(c.verdict||'')}</div>
    <div class="sc-stats">
      <div class="sc-stat"><div class="k">Edge</div><div class="v">${c.edge_score!=null?esc(c.edge_score):'-'}</div></div>
      <div class="sc-stat"><div class="k">Hist win rate</div><div class="v">${fmtProb(s.historical_win_rate)}</div></div>
      <div class="sc-stat"><div class="k">Sharpe</div><div class="v">${s.sharpe_ratio!=null?esc(s.sharpe_ratio):'-'}</div></div>
      <div class="sc-stat"><div class="k">Avg return</div><div class="v">${fmtPct(s.avg_return_pct)}</div></div>
      ${mlrow}
    </div>
    ${years?`<div class="sc-years">${years}</div>`:''}
    ${ticket}
    ${c.disclaimer?`<div class="sc-disc">${esc(c.disclaimer)}</div>`:''}
  </div>`;
}

function renderResult(ep, data){
  // pull cards out of the various envelopes
  let cards = [];
  if(ep.cards){
    if(Array.isArray(data.opportunities)) cards = data.opportunities;
    else if(data.card) cards = [data.card];
    else if(data.symbol && data.headline) cards = [data];
  }
  let html = "";
  if(cards.length){ html += cards.map(renderCard).join(""); }
  else if(ep.cards){ html += `<div class="pg-empty">No cards returned (the API may have responded with a neutral bias or an empty scan). See the raw response below.</div>`; }
  html += `<details class="pg-raw" ${cards.length?'':'open'}><summary>Raw JSON response</summary><pre><code>${JSON.stringify(data,null,2).replace(/</g,'&lt;')}</code></pre></details>`;
  return html;
}

async function run(){
  const key = ($("key").value||"").trim();
  const out = $("output");
  if(!key){ out.innerHTML = `<div class="pg-status err">Enter your API key first.</div><div class="pg-empty">No key? <a href="${CONSOLE_URL}">Create one in the dashboard</a> - free, instant.</div>`; return; }
  if($("remember").checked) localStorage.setItem(KEY_LS, key); else localStorage.removeItem(KEY_LS);
  const ep = curEndpoint();
  const req = buildRequest();
  $("run").disabled = true; out.innerHTML = `<div class="pg-status">Calling ${ep.method} ${ep.path} ...</div>`;
  try{
    const opts = { method: req.method, headers: { "Authorization": "Bearer "+key } };
    if(req.body){ opts.headers["Content-Type"]="application/json"; opts.body = req.body; }
    const resp = await fetch(req.url, opts);
    let data; try{ data = await resp.json(); }catch(e){ data = {error:"non-JSON response"}; }
    let cls = "ok", msg = `HTTP ${resp.status}`;
    if(resp.status===401||resp.status===403){ cls="err"; msg += " - check your key / tier"; }
    else if(resp.status===429){ cls="warn"; msg += " - rate limited, slow down"; }
    else if(resp.status>=500){ cls="err"; msg += " - server error"; }
    const rl = resp.headers.get("X-RateLimit-Remaining");
    if(rl!=null) msg += `  &middot;  ${rl} req remaining this window`;
    out.innerHTML = `<div class="pg-status ${cls}">${msg}</div>` + renderResult(ep, data);
  }catch(err){
    out.innerHTML = `<div class="pg-status err">Request failed: ${err}</div><div class="pg-empty">If this is a CORS error, make sure you are on the official developer portal. The API allows browser calls only from TradeWave portal origins.</div>`;
  }finally{ $("run").disabled = false; }
}

document.addEventListener("DOMContentLoaded", function(){
  const saved = localStorage.getItem(KEY_LS);
  if(saved){ $("key").value = saved; $("remember").checked = true; }
  $("ep").addEventListener("change", renderParams);
  $("key").addEventListener("input", updatePreview);
  $("params").addEventListener("input", updatePreview);
  $("run").addEventListener("click", run);
  document.querySelectorAll(".code-tab-btn").forEach((b,i)=>b.addEventListener("click",()=>{
    document.querySelectorAll(".code-tab-btn").forEach(x=>x.classList.remove("active"));
    document.querySelectorAll(".code-tab-pane").forEach(x=>x.classList.remove("active"));
    b.classList.add("active"); document.querySelectorAll(".code-tab-pane")[i].classList.add("active");
  }));
  renderParams();
});
"""

BODY_HTML = """
<div class="pg-wrap">
  <div class="callout green" style="margin:0 0 22px">
    <p><strong>BYOK - your key never leaves your browser.</strong> It is sent only as an
    <code class="inline-code">Authorization: Bearer</code> header straight to the API. No key?
    <a href="__CONSOLE_URL__">Create a free one</a> - instant, no card.</p>
  </div>
  <div class="pg-grid">
    <div class="pg-panel">
      <h3>Request</h3>
      <div class="pg-field">
        <label>API key</label>
        <input id="key" type="password" placeholder="tw_live_...">
        <div class="pg-row" style="margin-top:7px"><input type="checkbox" id="remember" style="width:auto"> <label for="remember" style="margin:0;cursor:pointer">remember in this browser</label></div>
        <div class="pg-key-warn">Stored only in this browser's localStorage if checked. Clear it any time by unchecking and re-running.</div>
      </div>
      <div class="pg-field">
        <label>Endpoint</label>
        <select id="ep">
          <option value="daily-pick">Daily pick</option>
          <option value="scan">Scan - find best opportunities</option>
          <option value="analyze">Analyze a symbol</option>
          <option value="markets">List markets</option>
          <option value="opportunities">Opportunities (primitive)</option>
          <option value="patterns">Seasonal pattern stats</option>
          <option value="track-record">Daily-pick track record</option>
          <option value="score">ML score (POST)</option>
        </select>
      </div>
      <div id="params"></div>
      <button class="pg-btn" id="run">Send request</button>
    </div>
    <div class="pg-panel">
      <h3>Response</h3>
      <div id="reqline" style="margin-bottom:14px"></div>
      <div id="output"><div class="pg-empty">Pick an endpoint and hit <strong>Send request</strong> to see a live PatternCard.</div></div>
    </div>
  </div>

  <div class="pg-snippet">
    <h2>The same call in your code</h2>
    <p>This updates as you edit the request above. Copy it straight into your app.</p>
    <div class="code-tabs">
      <div class="code-tab-bar">
        <button class="code-tab-btn active">curl</button>
        <button class="code-tab-btn">Python</button>
        <button class="code-tab-btn">JavaScript</button>
      </div>
      <div class="code-tab-pane active"><pre><code id="snip-curl"></code></pre></div>
      <div class="code-tab-pane"><pre><code id="snip-python"></code></pre></div>
      <div class="code-tab-pane"><pre><code id="snip-javascript"></code></pre></div>
    </div>
    <p style="margin-top:18px"><a href="__DOCS_URL__/api-reference.html">Full API reference</a> &middot;
       <a href="__DOCS_URL__/tradewave.postman_collection.json">Download Postman collection</a> &middot;
       <a href="__DOCS_URL__/openapi.yaml">OpenAPI spec</a></p>
  </div>
</div>
"""


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    head = "<style>" + gad.PAGE_CSS + PLAYGROUND_CSS + "</style>"
    header = gad.load_header()
    footer = gad.footer_html()
    body = BODY_HTML.replace("__CONSOLE_URL__", CONSOLE_URL).replace("__DOCS_URL__", DOCS_URL)
    js = ("<script>" + ENDPOINTS_JS +
          RUNNER_JS.replace("__API_BASE__", API_BASE).replace("__CONSOLE_URL__", CONSOLE_URL) +
          "</script>")
    page = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>API Playground - TradeWave Developers</title>\n"
        "<meta name=\"description\" content=\"Run live TradeWave API calls in your browser and copy the code.\">\n"
        "<meta name=\"robots\" content=\"index, follow\">\n"
        + portal_seo.head_tags(portal_urls.PORTAL_URL + "/playground/", "API Playground",
            "Run live TradeWave API calls in your browser and copy the curl, Python, or JavaScript.")
        + "\n<link rel=\"icon\" type=\"image/png\" href=\"/favicon.png\">\n"
        "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">\n"
        "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap\">\n"
        + head + "\n</head>\n<body>\n" + header +
        "\n<div class=\"docs-hero\"><h1>API Playground</h1><p>Run real calls against the live API and copy the exact code.</p></div>\n"
        + body + "\n" + footer + "\n" + js + "\n</body>\n</html>"
    )
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")
    print(f"  {len(page):,} bytes -> {OUT_DIR / 'index.html'}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
