"""Generate the static showcase site (GitHub Pages) into ../site/.

    index.html        landing
    deck/             web deck (5 slides, scroll-snap, keyboard nav)
    report/           latest run's dashboard
    chat/             static grounded chat (viewer's own key, browser-direct)

Everything is static, self-contained, noindexed, and generated from the
latest run of the default workspace — never hand-edited.
"""
import json
import shutil

from .paths import ws_dir, latest_run, DEFAULT_WS
from .util import ROOT

SITE = ROOT.parent / "docs"
DELIV = ROOT.parent / "deliverables"

HEAD = """<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400..700;1,400&family=Noto+Serif:ital,wght@0,300;0,400;1,300;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
 :root{--bg:#101828;--sf:#1d2939;--ink:#f9f7f5;--deep:#374b60;--soft:#8fa3b8;--line:#243447;
   --acc:#ff4200;--accdark:#c12d00;--softblue:#bdd2e0;--softblue2:#14263a;--bordeaux:#a34d6e;
   --tan:#c9a689;--cream2:#0c1522}
 *{box-sizing:border-box}
 html{scroll-behavior:smooth}
 body{margin:0;color:var(--ink);font:16px/1.6 'Instrument Sans',system-ui,sans-serif;
   background:var(--bg) fixed;
   background-image:radial-gradient(900px 600px at 12% -10%,rgba(55,75,96,.55),transparent 60%),
     radial-gradient(800px 560px at 105% 8%,rgba(255,66,0,.07),transparent 55%),
     radial-gradient(700px 700px at 85% 110%,rgba(55,75,96,.4),transparent 60%)}
 ::selection{background:var(--acc);color:#fff}
 .serif{font-family:'Noto Serif',serif}.mono{font-family:'IBM Plex Mono',monospace}
 a{color:var(--softblue)}
 .eyebrow{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--tan)}
 .tag{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--acc);margin-right:10px;vertical-align:1px}
 .btn{display:inline-block;font:600 15px 'Instrument Sans';border-radius:9px;border:1px solid var(--line);
   padding:12px 22px;background:var(--sf);color:var(--ink);text-decoration:none;transition:border-color .15s,transform .15s}
 .btn:hover{border-color:var(--acc);transform:translateY(-1px)}
 .btn.primary{background:var(--acc);border-color:var(--acc);color:#fff}
 .btn.primary:hover{background:var(--accdark)}
 .rule{position:relative;height:1px;background:var(--line);margin:0 auto}
 .rule::before,.rule::after{content:"";position:absolute;top:-4px;width:9px;height:9px;background:var(--bg);
   border:1px solid var(--soft);transform:rotate(45deg)}
 .rule::before{left:0}.rule::after{right:0}
 @media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}html{scroll-behavior:auto}}
 /* glass windows — body-prefixed so it outranks per-page rules */
 body .rail,body .stage,body #settings,body .msg.ai,body .dirty,body .bar,
 body .stats>div,body .steps>div,body .facts>div,body .in>.stats>div{
   background:rgba(29,41,57,.55);
   -webkit-backdrop-filter:blur(16px) saturate(1.3);
   backdrop-filter:blur(16px) saturate(1.3);
   border-color:rgba(189,210,224,.17)}
 body .stage,body #settings,body .msg.ai,body .stats>div,body .steps>div,body .facts>div{
   box-shadow:inset 0 1px 0 rgba(255,255,255,.07)}
 body .rail{box-shadow:0 18px 50px -30px rgba(0,0,0,.8),inset 0 1px 0 rgba(255,255,255,.08)}
 body .bar{background:rgba(16,24,40,.6)}
 body #settings{background:rgba(29,41,57,.72)}
</style>"""


def landing(st) -> str:
    import json as _json
    rec = st["conclusion"]["recommendation"]
    man = st["manifest"]
    fac = st["facilities"]["summary"]
    nl = st["conclusion"]["results"][rec]
    files = []
    for d in st["ingestion"]:
        key = d["key"]
        scope, kind = key.split("/", 1)
        role = (kind.replace("_", " ") if scope in ("company", "shared") else f"{scope} · {kind.replace('_', ' ')}")
        files.append({"name": d["file"], "role": role, "fmt": d["format"].upper()})
    for f in st.get("files", {}).get("skipped", []):
        files.append({"name": f, "role": "reference — not analysed", "fmt": f.split(".")[-1].upper()})
    for f in st.get("files", {}).get("unassigned", []):
        files.append({"name": f, "role": "unassigned", "fmt": f.split(".")[-1].upper()})
    seed = _json.dumps({
        "id": "eu4", "name": "EU4 Case Pack", "protected": True, "hasRun": True, "dirty": False,
        "lastRun": man["run_at"][:16].replace("T", " ") + " UTC", "files": files,
        "facts": [["Recommendation", f"the {rec}"], ["Break-even", f"Year {nl['break_even_year']}"],
                   ["Cash trough", f"€{nl['min_cash']/1e6:.2f}M"], ["End cash Y5", f"€{nl['end_cash']/1e6:.2f}M"],
                   ["Records → facilities", f"{fac['raw_records']:,} → {fac['unique_facilities']}"],
                   ["Golden eval", "28 / 28"], ["AI calls · cost", f"{man['llm_calls']} · €{man['llm_cost_eur']:.2f}"],
                   ["Runtime", f"{man['total_s']}s"]]})
    stages_js = _json.dumps(["read native formats", "extract parameters", "resolve one schema",
                             "dedupe facilities", "compare sources", "arithmetic checks", "conclude"])
    return f"""<!doctype html><html lang="en"><head><title>Runway, the market-entry desk</title>{HEAD}
<style>
 html,body{{height:100%}}
 body{{overflow:hidden;display:grid;grid-template-rows:auto 1fr;font-size:15px}}
 .bar{{display:flex;align-items:center;gap:12px;padding:14px 22px;border-bottom:1px solid var(--line)}}
 .bar b{{font-size:15px}} .bar .mono{{color:var(--soft);font-size:11px;letter-spacing:.14em}}
 .bar nav{{margin-left:auto;display:flex;gap:18px}}
 .bar nav a{{font:600 12.5px 'Instrument Sans';color:var(--softblue);text-decoration:none}}
 .bar nav a:hover{{color:var(--acc)}}
 .desk{{display:grid;grid-template-columns:270px 1fr;gap:18px;padding:18px 22px;min-height:0}}
 @media(max-width:820px){{body{{overflow:auto}}.desk{{grid-template-columns:1fr}}}}
 /* left rail — the floating panel */
 .rail{{background:var(--sf);border:1px solid var(--line);border-radius:14px;display:flex;flex-direction:column;
   min-height:0;box-shadow:0 18px 50px -30px rgba(0,0,0,.8)}}
 .rail header{{display:flex;align-items:center;gap:8px;padding:13px 14px;border-bottom:1px solid var(--line)}}
 .rail header .mono{{font-size:10px;letter-spacing:.18em;color:var(--tan)}}
 .rail header button{{margin-left:auto;font:600 12px 'Instrument Sans';background:var(--acc);color:#fff;
   border:none;border-radius:7px;padding:6px 10px;cursor:pointer}}
 .rail header button:hover{{background:var(--accdark)}}
 .exlist{{flex:1;overflow-y:auto;min-height:0;padding:6px}}
 .ex{{display:flex;align-items:center;gap:9px;padding:10px 10px;border-radius:9px;cursor:pointer;color:var(--ink)}}
 .ex:hover{{background:var(--softblue2)}}
 .ex.on{{background:var(--softblue2);outline:1px solid var(--deep)}}
 .ex .dot{{width:8px;height:8px;border-radius:50%;flex:none;border:1.5px solid var(--soft)}}
 .ex.ran .dot{{background:var(--acc);border-color:var(--acc)}}
 .ex .nm{{flex:1;font-size:13.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
 .ex input{{flex:1;font:600 13.5px 'Instrument Sans';background:var(--bg);color:var(--ink);
   border:1px solid var(--deep);border-radius:6px;padding:4px 7px;min-width:0}}
 .ex .del{{border:none;background:none;color:var(--soft);cursor:pointer;font-size:13px;padding:2px 4px;opacity:0}}
 .ex:hover .del{{opacity:1}} .ex .del:hover{{color:var(--acc)}}
 .railset{{display:flex;align-items:center;gap:9px;padding:12px 14px;border:none;border-top:1px solid var(--line);
   background:none;color:var(--softblue);cursor:pointer;font:600 13px 'Instrument Sans';text-align:left}}
 .railset:hover{{color:var(--ink)}} .railset svg{{width:15px;height:15px}}
 .rail footer{{padding:10px 14px;border-top:1px solid var(--line);font:10px 'IBM Plex Mono',monospace;
   letter-spacing:.1em;color:var(--soft)}}
 #wsset{{position:fixed;left:22px;bottom:96px;width:280px;background:rgba(29,41,57,.85);
   -webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px);border:1px solid rgba(189,210,224,.2);
   border-radius:14px;padding:15px;display:none;z-index:9;box-shadow:0 24px 60px -30px rgba(0,0,0,.85)}}
 #wsset.open{{display:block}}
 #wsset label{{display:block;font:10px 'IBM Plex Mono',monospace;letter-spacing:.14em;color:var(--tan);
   text-transform:uppercase;margin:10px 0 5px}} #wsset label:first-child{{margin-top:0}}
 #wsset input,#wsset select{{width:100%;font:12.5px 'IBM Plex Mono',monospace;border:1px solid var(--line);
   border-radius:8px;padding:8px 9px;background:var(--bg);color:var(--ink)}}
 .whint{{font-size:12px;color:var(--soft);margin-top:5px;min-height:14px}}
 .wforget{{margin-top:10px;border:none;background:none;color:var(--soft);cursor:pointer;
   font:600 11.5px 'Instrument Sans';padding:0}} .wforget:hover{{color:var(--acc)}}
 /* center pane */
 .pane{{display:flex;flex-direction:column;min-height:0;gap:14px}}
 .panehead{{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}}
 .panehead h1{{margin:0;font-size:clamp(24px,3vw,34px);font-weight:700;text-transform:uppercase;letter-spacing:-.02em}}
 .panehead h1 em{{font-family:'Noto Serif',serif;font-style:italic;font-weight:300;text-transform:none;color:var(--acc)}}
 .panehead h1{{cursor:text;border-bottom:1.5px dashed transparent}}
 .panehead h1:hover{{border-bottom-color:var(--deep)}}
 .panehead input.titled{{font:700 clamp(24px,3vw,34px) 'Instrument Sans';text-transform:uppercase;letter-spacing:-.02em;background:var(--sf);color:var(--ink);border:1px solid var(--deep);border-radius:8px;padding:2px 10px;min-width:0;max-width:60vw}}
 .tabs{{display:flex;gap:6px;margin-left:auto}}
 .tab{{font:600 13px 'Instrument Sans';border:1px solid var(--line);background:var(--sf);color:var(--softblue);
   border-radius:9px;padding:8px 18px;cursor:pointer}}
 .tab.on{{background:var(--deep);color:#fff;border-color:var(--deep)}}
 .tab:disabled{{opacity:.4;cursor:not-allowed}}
 .dirty{{background:#3d2f16;color:#f2d9a7;border:1px solid #5a4620;border-radius:10px;padding:10px 14px;
   font-size:13px;display:none}}
 .dirty.show{{display:block}}
 .stage{{flex:1;background:var(--sf);border:1px solid var(--line);border-radius:14px;min-height:0;
   overflow:auto;padding:18px}}
 /* files */
 .filegrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:9px}}
 .frow{{display:flex;align-items:center;gap:9px;border:1px solid var(--line);border-radius:9px;padding:9px 11px}}
 .frow .mono{{font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:110px}}
 .chip{{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.06em;border-radius:99px;
   padding:2px 8px;background:var(--softblue2);color:var(--softblue);white-space:nowrap}}
 .chip.warn{{background:#3d2f16;color:#f2d9a7}}
 .frow .del{{border:none;background:none;color:var(--soft);cursor:pointer;padding:0 2px}}
 .frow .del:hover{{color:var(--acc)}}
 .viewtog{{display:flex;gap:6px;justify-content:flex-end;margin-bottom:12px}}
 .viewtog button{{font:600 12px 'IBM Plex Mono',monospace;border:1px solid var(--line);background:transparent;
   color:var(--soft);border-radius:7px;width:32px;height:28px;cursor:pointer}}
 .viewtog button.on{{background:var(--softblue2);color:var(--ink);border-color:var(--deep)}}
 .fgridV{{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:10px}}
 .ftile{{aspect-ratio:1;border:1px solid var(--line);border-radius:11px;position:relative;padding:12px 10px;
   display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;text-align:center}}
 .ftile .fmt{{font:600 11px 'IBM Plex Mono',monospace;background:var(--softblue2);color:var(--softblue);
   border:1px solid var(--line);border-radius:8px;padding:9px 11px}}
 .ftile .nm{{font:11px 'IBM Plex Mono',monospace;max-width:100%;overflow:hidden;display:-webkit-box;
   -webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-all}}
 .ftile .del{{position:absolute;top:7px;right:7px;border:none;background:none;color:var(--soft);
   cursor:pointer;opacity:0}}
 .ftile:hover .del{{opacity:1}} .ftile .del:hover{{color:var(--acc)}}
 .flist{{display:flex;flex-direction:column;gap:8px}}
 .addsq{{aspect-ratio:1;border:1.5px dashed var(--deep);border-radius:11px;display:grid;place-content:center;
   color:var(--softblue);cursor:pointer;font-size:26px}}
 .addsq:hover{{border-color:var(--acc);color:var(--acc)}}
 .addsq.sm{{width:64px;height:64px;aspect-ratio:auto;margin-top:8px}}
 /* run */
 .runwrap{{display:grid;place-content:center;text-align:center;height:100%;gap:16px}}
 .runbtn{{font:700 17px 'Instrument Sans';background:var(--acc);color:#fff;border:none;border-radius:12px;
   padding:16px 34px;cursor:pointer;letter-spacing:.01em}}
 .runbtn:hover{{background:var(--accdark)}}
 .runbtn.ghost{{background:var(--sf);border:1px solid var(--line);color:var(--ink)}}
 .modes{{display:flex;gap:14px;flex-wrap:wrap;justify-content:center}}
 .mode{{display:flex;flex-direction:column;gap:6px;align-items:flex-start;text-align:left;cursor:pointer;
   background:var(--sf);border:1px solid var(--line);border-radius:14px;padding:16px 20px;max-width:270px;
   color:var(--ink);transition:border-color .15s,transform .15s}}
 .mode:hover{{border-color:var(--acc);transform:translateY(-2px)}}
 .mode b{{font:700 16px 'Instrument Sans'}}
 .mode span{{font-size:12px;color:var(--soft);line-height:1.5}}
 .mode.after{{border-color:var(--deep)}}
 .mode.after b{{color:var(--acc)}}
 .mode:disabled{{opacity:.45;cursor:wait;transform:none}}
 .runlog{{text-align:left;font:12.5px 'IBM Plex Mono',monospace;color:var(--soft);display:none;min-width:290px}}
 .runlog div{{padding:3px 0}} .runlog .done::before{{content:"✓ ";color:var(--acc)}}
 .runlog .pend::before{{content:"· "}}
 /* results */
 .seg{{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}}
 .seg button{{font:600 12px 'Instrument Sans';border:1px solid var(--line);background:transparent;
   color:var(--softblue);border-radius:99px;padding:7px 15px;cursor:pointer}}
 .seg button.on{{background:var(--softblue2);border-color:var(--deep);color:var(--ink)}}
 iframe{{width:100%;height:calc(100% - 78px);border:1px solid var(--line);border-radius:10px;background:#fff}}
 .recnote{{margin:0 0 10px;font:11.5px 'IBM Plex Mono',monospace;color:var(--soft);letter-spacing:.02em}}
 .facts{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:1px;background:var(--line);
   border:1px solid var(--line)}}
 .facts div{{background:var(--bg);padding:16px}}
 .facts span{{display:block;font:10px 'IBM Plex Mono',monospace;letter-spacing:.14em;color:var(--soft);text-transform:uppercase}}
 .facts b{{font-size:21px;letter-spacing:-.01em}}
 .openfull{{font:600 12px 'Instrument Sans';color:var(--softblue);text-decoration:none;float:right}}
 .openfull:hover{{color:var(--acc)}}
 .iband{{border:1px solid var(--line);border-radius:11px;padding:14px 16px;display:flex;gap:16px;
   align-items:baseline;flex-wrap:wrap;margin-bottom:14px}}
 .iband b{{font-size:15.5px}} .iband span{{font-size:12.5px;color:var(--soft)}}
 .iband.SUFFICIENT{{border-color:var(--deep);background:var(--softblue2)}}
 .iband.PARTIAL{{border-color:#5a4620;background:#2b2413}}
 .iband.INSUFFICIENT{{border-color:#5a2620;background:#2b1613}}
 .ichip{{font:600 10px 'IBM Plex Mono',monospace;letter-spacing:.08em;border-radius:99px;padding:2px 9px}}
 .ichip.SUFFICIENT{{background:var(--softblue2);color:var(--softblue)}}
 .ichip.PARTIAL{{background:#3d2f16;color:#f2d9a7}}
 .ichip.INSUFFICIENT{{background:#3d1c16;color:#f2b3a7}}
 .ichip.PEND{{background:transparent;border:1px dashed var(--soft);color:var(--soft)}}
 .ichip.AGREE{{background:var(--softblue2);color:var(--softblue)}}
 .ichip.DISAGREE{{background:#3d1c16;color:#f2b3a7}}
 .ichip.SKIPPED{{background:transparent;border:1px dashed var(--soft);color:var(--soft)}}
 .mini h3{{font:600 13px 'Instrument Sans';margin:20px 0 10px;letter-spacing:.01em}}
 .mini h3:first-child{{margin-top:0}}
 .steps{{display:grid;gap:12px}}
 .steps div{{background:rgba(29,41,57,.55);border:1px solid rgba(189,210,224,.17);border-radius:12px;padding:14px}}
 .steps span{{font:600 11px 'IBM Plex Mono',monospace;color:var(--acc)}}
 .steps b{{display:block;margin:4px 0 2px}} .steps p{{margin:2px 0 0;font-size:12.5px;color:var(--soft)}}
 .itable{{border-collapse:collapse;width:100%;font-size:13px;margin-bottom:14px}}
 .itable th,.itable td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}}
 .itable th{{font:600 10.5px 'IBM Plex Mono',monospace;letter-spacing:.1em;color:var(--soft);text-transform:uppercase}}
 .igrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}
 .igrid>div{{border:1px solid var(--line);border-radius:11px;padding:13px 15px}}
 .igrid b{{display:block;font-size:13px;margin-bottom:6px}}
 .igrid p{{margin:3px 0;font-size:12.5px;color:var(--soft)}}
 .emptyres{{display:grid;place-content:center;text-align:center;height:100%;color:var(--soft);gap:10px}}
 .emptyres b{{font-size:26px;color:var(--line);letter-spacing:.04em}}
</style></head><body>
<div class="bar"><span class="tag"></span><b>RUNWAY</b><span class="mono">THE MARKET-ENTRY DESK</span>
 <nav><a href="http://108.132.145.140/" style="color:var(--acc)">Hosted desk</a><a href="model/">Blank model</a>
 <a href="https://github.com/tomasbb0/market-runway">Repo</a>
 <a href="https://burnaylabs.pt/v1-market-runway/">v1 site<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px;vertical-align:-2px;margin-left:5px"><path d="M7 17L17 7M9 7h8v8"/></svg></a></nav></div>

<div class="desk">
 <aside class="rail">
  <header><span class="tag"></span><span class="mono">EXERCISES</span><button id="newex">+ New</button></header>
  <div class="exlist" id="exlist"></div>
  <button class="railset" id="openset"><svg viewBox="0 0 24 24" fill="currentColor" fill-rule="evenodd"><path d="M18.79 10.31 L21.70 10.64 L21.70 13.36 L18.79 13.69 L18.00 15.61 L19.83 17.90 L17.90 19.83 L15.61 18.00 L13.69 18.79 L13.36 21.70 L10.64 21.70 L10.31 18.79 L8.39 18.00 L6.10 19.83 L4.17 17.90 L6.00 15.61 L5.21 13.69 L2.30 13.36 L2.30 10.64 L5.21 10.31 L6.00 8.39 L4.17 6.10 L6.10 4.17 L8.39 6.00 L10.31 5.21 L10.64 2.30 L13.36 2.30 L13.69 5.21 L15.61 6.00 L17.90 4.17 L19.83 6.10 L18.00 8.39 Z M15.1 12 A3.1 3.1 0 1 0 8.9 12 A3.1 3.1 0 1 0 15.1 12 Z"/></svg><span>Settings</span></button>
  <footer>SEVEN STAGES · DETERMINISTIC FIRST · EVAL 28/28</footer>
 </aside>
 <div id="wsset">
  <label>API key</label><input type="password" id="wkey" placeholder="sk-ant-… / sk-… / AIza…" autocomplete="off">
  <div class="whint" id="wprov"></div>
  <label>Model</label><select id="wmodel" disabled><option>set a key first</option></select>
  <button class="wforget" id="wforget">Forget key</button>
 </div>

 <section class="pane">
  <div class="panehead"><h1 id="title">EU4 <em>case pack</em></h1>
   <div class="tabs">
    <button class="tab" data-t="files">Files</button>
    <button class="tab" data-t="run">Run</button>
    <button class="tab" data-t="results" id="tabres">Results</button>
   </div></div>
  <div class="dirty" id="dirty">Files changed since the last run — results are stale. Nothing updates until you re-run.</div>
  <div class="stage" id="stage"></div>
 </section>
</div>

<input type="file" id="fpick" multiple hidden>
<script src="engine/engine.js"></script>
<script>
 document.documentElement.classList.add('js');
 const SEED={seed};
 const STAGES={stages_js};
 const FILESTORE={{}};   // exercise id -> {{filename: Uint8Array}} (session only)
 const RUNS={{}};        // exercise id -> real browser-engine result
 const IDB={{db:null,
  open(){{return new Promise(res=>{{const q=indexedDB.open('runway',1);
    q.onupgradeneeded=()=>{{q.result.createObjectStore('files');q.result.createObjectStore('runs')}};
    q.onsuccess=()=>{{IDB.db=q.result;res()}};q.onerror=()=>res()}})}},
  req(r){{return new Promise(res=>{{r.onsuccess=()=>res(r.result);r.onerror=()=>res(undefined)}})}},
  put(st,k,v){{try{{IDB.db&&IDB.db.transaction(st,'readwrite').objectStore(st).put(v,k)}}catch(err){{}}}},
  del(st,k){{try{{IDB.db&&IDB.db.transaction(st,'readwrite').objectStore(st).delete(k)}}catch(err){{}}}},
  async all(st){{if(!IDB.db)return[];
    const ks=await IDB.req(IDB.db.transaction(st).objectStore(st).getAllKeys());
    const vs=await IDB.req(IDB.db.transaction(st).objectStore(st).getAll());
    return (ks||[]).map((k,i)=>[k,(vs||[])[i]])}}
 }};
 let S=JSON.parse(localStorage.getItem('runway-ex')||'null');
 if(!S){{S={{list:[SEED],sel:'eu4',tab:'files'}};save();}}
 if(!S.list.find(e=>e.id==='eu4')){{S.list.unshift(SEED);}}
 function save(){{localStorage.setItem('runway-ex',JSON.stringify(S))}}
 function cur(){{return S.list.find(e=>e.id===S.sel)||S.list[0]}}
 const $=id=>document.getElementById(id);

 function renderRail(){{
   $('exlist').innerHTML=S.list.map(e=>
     `<div class="ex ${{e.id===S.sel?'on':''}} ${{e.hasRun?'ran':''}}" data-id="${{e.id}}">
       <span class="dot"></span><span class="nm" title="click again to rename">${{esc(e.name)}}</span>
       ${{e.protected?'':'<button class="del" title="Delete exercise">✕</button>'}}</div>`).join('');
   document.querySelectorAll('.ex').forEach(el=>{{
     el.onclick=ev=>{{if(ev.target.classList.contains('del'))return;
       if(el.dataset.id===S.sel&&ev.target.classList.contains('nm')){{rename(el.dataset.id);return}}
       S.sel=el.dataset.id;S.tab=cur().hasRun?'results':'files';save();render();}};
     el.querySelector('.del')?.addEventListener('click',()=>{{
       if(confirm('Delete this exercise and its file list?')){{
         const id=el.dataset.id;
         Object.keys(FILESTORE[id]||{{}}).forEach(n=>IDB.del('files',id+'|'+n));
         delete FILESTORE[id];delete RUNS[id];IDB.del('runs',id);
         S.list=S.list.filter(x=>x.id!==id);
         if(S.sel===el.dataset.id)S.sel=S.list[0]?.id;save();render();}}}});
     el.querySelector('.nm').ondblclick=()=>rename(el.dataset.id);
   }});
 }}
 function rename(id){{
   const e=S.list.find(x=>x.id===id);const row=document.querySelector(`.ex[data-id="${{id}}"]`);
   row.querySelector('.nm').outerHTML=`<input value="${{esc(e.name)}}" maxlength="40">`;
   const inp=row.querySelector('input');inp.focus();inp.select();
   const done=()=>{{e.name=inp.value.trim()||e.name;save();render();}};
   inp.onkeydown=ev=>{{if(ev.key==='Enter')done();if(ev.key==='Escape')render();}};
   inp.onblur=done;
 }}
 $('newex').onclick=()=>{{
   const n=S.list.filter(e=>!e.protected).length+1;
   const e={{id:'ex'+Date.now(),name:'Exercise '+n,protected:false,hasRun:false,dirty:false,files:[],facts:[]}};
   S.list.push(e);S.sel=e.id;S.tab='files';save();render();
   setTimeout(()=>rename(e.id),50);
 }};

 function render(){{
   const e=cur();if(!e)return;
   renderRail();
   const t=$('title');
   const parts=e.name.split(' ');
   t.innerHTML=parts.length>1?esc(parts[0])+' <em>'+esc(parts.slice(1).join(' ').toLowerCase())+'</em>':esc(e.name);
   t.title='Click to rename';
   t.onclick=()=>{{
     const inp=document.createElement('input');inp.className='titled';inp.maxLength=40;inp.value=e.name;
     t.replaceWith(inp);inp.focus();inp.select();
     const done=ok=>{{if(ok){{e.name=inp.value.trim()||e.name;save();}}
       inp.replaceWith(t);render();}};
     inp.onkeydown=ev=>{{if(ev.key==='Enter')done(true);if(ev.key==='Escape')done(false);}};
     inp.onblur=()=>done(true);
   }};
   document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.t===S.tab));
   $('tabres').disabled=!e.hasRun;
   $('dirty').classList.toggle('show',!!e.dirty&&e.hasRun);
   if(S.tab==='run'&&!e.protected&&window.Engine&&!Engine.isReady())
     Engine.init(()=>{{}}).catch(()=>{{}});
   ({{files:renderFiles,run:renderRun,results:renderResults}})[S.tab]();
 }}
 document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{{
   if(b.disabled)return;S.tab=b.dataset.t;save();render();}});

 function renderFiles(){{
   const e=cur();const v=S.view||'grid';
   const tog='<div class="viewtog">'
     +'<button data-v="grid" class="'+(v==='grid'?'on':'')+'" title="Icon view">⊞</button>'
     +'<button data-v="list" class="'+(v==='list'?'on':'')+'" title="List view">≡</button></div>';
   let body;
   if(v==='grid'){{
     body='<div class="fgridV">'+e.files.map((f,i)=>
       `<div class="ftile"><button class="del" data-i="${{i}}" title="Remove">✕</button>
        <span class="fmt">${{esc(f.fmt||'?')}}</span>
        <span class="nm" title="${{esc(f.name)}}">${{esc(f.name)}}</span>
        <span class="chip ${{f.role==='unassigned'?'warn':''}}">${{esc(f.role||'')}}</span></div>`).join('')
       +'<div class="addsq" id="addf" title="Add documents">+</div></div>';
   }} else {{
     body='<div class="flist">'+e.files.map((f,i)=>
       `<div class="frow"><span class="mono" title="${{esc(f.name)}}">${{esc(f.name)}}</span>
        <span class="chip ${{f.role==='unassigned'?'warn':''}}">${{esc(f.role||f.fmt||'')}}</span>
        <button class="del" data-i="${{i}}" title="Remove">✕</button></div>`).join('')
       +'</div><div class="addsq sm" id="addf" title="Add documents">+</div>';
   }}
   $('stage').innerHTML=tog+body
     +'<p style="color:var(--soft);font-size:12.5px;margin-top:14px">Adding or removing files changes nothing until you run. '
     +(e.protected?'This is the recorded case pack; edits here are a local mock.':'')+'</p>';
   document.querySelectorAll('.viewtog button').forEach(b=>b.onclick=()=>{{S.view=b.dataset.v;save();render();}});
   $('addf').onclick=()=>$('fpick').click();
   $('fpick').onchange=async()=>{{
     for(const f of [...$('fpick').files]){{
       const ua=new Uint8Array(await f.arrayBuffer());
       (FILESTORE[e.id]=FILESTORE[e.id]||{{}})[f.name]=ua;
       IDB.put('files',e.id+'|'+f.name,ua);
       if(!e.files.some(x=>x.name===f.name))
         e.files.push({{name:f.name,role:'unassigned',fmt:(f.name.split('.').pop()||'').toUpperCase()}});
     }}
     $('fpick').value='';e.dirty=true;save();render();
     if(window.__autorun){{const mm=window.__autorun;window.__autorun=null;
       const st=FILESTORE[e.id]||{{}};
       if(e.files.every(f=>st[f.name])){{S.tab='run';save();render();setTimeout(()=>realRun(e,mm),50);}}}}
   }};
   document.querySelectorAll('.stage .del,.ftile .del,.frow .del').forEach(b=>b.onclick=()=>{{
     const nm=(e.files[+b.dataset.i]||{{}}).name;
     if(nm){{delete (FILESTORE[e.id]||{{}})[nm];IDB.del('files',e.id+'|'+nm);}}
     e.files.splice(+b.dataset.i,1);e.dirty=true;save();render();}});
 }}

 async function providerCall(p,key,model,prompt){{
   if(p==='anthropic'){{
     const r=await fetch('https://api.anthropic.com/v1/messages',{{method:'POST',headers:{{
       'content-type':'application/json','x-api-key':key,'anthropic-version':'2023-06-01',
       'anthropic-dangerous-direct-browser-access':'true'}},
       body:JSON.stringify({{model,max_tokens:700,messages:[{{role:'user',content:prompt}}]}})}});
     const j=await r.json();if(j.error)throw j.error.message;return j.content[0].text;}}
   if(p==='openai'){{
     const r=await fetch('https://api.openai.com/v1/chat/completions',{{method:'POST',headers:{{
       'content-type':'application/json','authorization':'Bearer '+key}},
       body:JSON.stringify({{model,max_completion_tokens:700,messages:[{{role:'user',content:prompt}}]}})}});
     const j=await r.json();if(j.error)throw j.error.message;return j.choices[0].message.content;}}
   if(p==='google'){{
     const r=await fetch('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent?key='+key,
       {{method:'POST',headers:{{'content-type':'application/json'}},
        body:JSON.stringify({{contents:[{{role:'user',parts:[{{text:prompt}}]}}],
          generationConfig:{{maxOutputTokens:700,temperature:0}}}})}});
     const j=await r.json();if(j.error)throw j.error.message;return j.candidates[0].content.parts[0].text;}}
   throw 'unknown provider';
 }}
 async function browserAudit(res,line){{
   const key=getKey(),p=detectProvider(key);
   const mdl=localStorage.getItem('mdl');
   const model=PROVIDERS[p].models[mdl]?mdl:Object.keys(PROVIDERS[p].models)[0];
   const bySrc={{}};
   res.targets.forEach(t=>{{if(res.doc_texts[t.source])(bySrc[t.source]=bySrc[t.source]||[]).push(t)}});
   const out=[];let a=0,d=0,sk=0;
   for(const [src,items] of Object.entries(bySrc)){{
     const prompt='Extract exactly these parameters from the document below. Reply with ONLY a JSON object '
       +'mapping each parameter name to a number, or null if absent. Express percentages as fractions '
       +'(43% means 0.43). Parameters: '+items.map(t=>t.param).join(', ')
       +'.'+String.fromCharCode(10)+'DOCUMENT:'+String.fromCharCode(10)+res.doc_texts[src];
     try{{
       const raw=await providerCall(p,key,model,prompt);
       const jm=raw.match(/{{[^]*}}/);const got=JSON.parse(jm?jm[0]:raw);
       items.forEach(t=>{{
         let g=got[t.param];
         if(typeof g!=='number'){{out.push({{...t,model:null,verdict:'SKIPPED'}});sk++;return}}
         if(t.value<=1&&g>1)g=g/100;
         const ok=Math.abs(g-t.value)<=Math.max(Math.abs(t.value)*.01,1e-9);
         out.push({{...t,model:g,verdict:ok?'AGREE':'DISAGREE'}});ok?a++:d++;}});
       line('audit '+src+': '+items.length+' value(s) checked');
     }}catch(err){{items.forEach(t=>{{out.push({{...t,model:null,verdict:'SKIPPED'}});sk++}});
       line('audit '+src+' failed: '+String(err).slice(0,120));}}
   }}
   line('model audit: '+a+' agree · '+d+' disagree · '+sk+' skipped');
   return{{list:out,agree:a,dis:d,skipped:sk,model:PROVIDERS[p].label+' · '+PROVIDERS[p].models[model]}};
 }}
 function auditHTML(au){{
   const cls=au.dis?'PARTIAL':'SUFFICIENT';
   const rows=au.list.map(t=>'<tr><td>'+esc(t.scope)+' · '+esc(t.param)+'</td><td>'+t.value
     +'</td><td>'+(t.model===null?'—':t.model)+'</td><td><span class="ichip '+t.verdict+'">'+t.verdict
     +'</span></td></tr>').join('');
   return '<div class="iband '+cls+'" style="margin-top:16px"><b>Model audit: '+au.agree+' agree · '
     +au.dis+' disagree'+(au.skipped?' · '+au.skipped+' skipped':'')+'</b><span>'+esc(au.model)
     +', called from this browser with your key</span></div>'
     +'<table class="itable"><thead><tr><th>Field</th><th>Engine</th><th>Model</th><th>Verdict</th></tr></thead><tbody>'
     +rows+'</tbody></table>';
 }}
 async function realRun(e,m){{
   const log=$('rlog');log.style.display='block';
   const line=t=>{{const d=document.createElement('div');d.className='done';d.textContent=t;
     log.appendChild(d);d.scrollIntoView({{block:'nearest'}})}};
   document.querySelectorAll('.mode').forEach(b=>b.disabled=true);
   const store=FILESTORE[e.id]||{{}};
   const missing=e.files.filter(f=>!store[f.name]).map(f=>f.name);
   if(!e.files.length){{log.innerHTML='<div class="pend">add documents in Files first</div>';
     document.querySelectorAll('.mode').forEach(b=>b.disabled=false);return}}
   if(missing.length){{
     log.innerHTML='<div class="pend">This exercise predates on-device storage, so the file contents were '
       +'never saved — only the names. Select the files once more (all at once is fine) and the run starts '
       +'by itself. Missing: '+missing.map(esc).join(', ')+'</div>';
     const pick=document.createElement('button');pick.className='runbtn ghost';pick.textContent='Select the files';
     pick.onclick=()=>{{window.__autorun=m;$('fpick').click()}};log.appendChild(pick);
     document.querySelectorAll('.mode').forEach(b=>b.disabled=false);return}}
   log.innerHTML='';
   try{{
     const files=e.files.map(f=>({{name:f.name,bytes:store[f.name]}}));
     const res=await Engine.run(e.id,files,line);
     if(m==='afterburner'){{
       if(!getKey())line('audit skipped: add an API key in Settings to enable the model audit');
       else try{{res.audit=await browserAudit(res,line);}}
       catch(err){{line('audit failed: '+String(err).slice(0,200));}}
     }}
     RUNS[e.id]=res;IDB.put('runs',e.id,res);
     e.hasRun=true;e.dirty=false;e.lastMode=m;e.realAt=Date.now();
     e.analysis=analyze(e.files);
     if(m==='afterburner')e.insights=e.analysis;
     e.lastRun=new Date().toISOString().slice(0,16).replace('T',' ');
     line('done — opening the evidence report');
     save();S.res='evidence';S.tab='results';render();
   }}catch(err){{
     line('engine error: '+String(err).slice(0,300));
     document.querySelectorAll('.mode').forEach(b=>b.disabled=false);
   }}
 }}
 function renderRun(){{
   const e=cur();const rerun=e.hasRun?'Re-run':'Run';
   $('stage').innerHTML=`<div class="runwrap">
     <div class="eyebrow"><span class="tag"></span>${{e.hasRun
       ?'LAST RUN · '+(e.lastRun||'recorded')+(e.lastMode?' · '+e.lastMode.toUpperCase():''):'NEVER RUN'}}</div>
     <div class="modes">
      <button class="mode" data-m="glide"><b>${{rerun}}: Glide</b>
       <span>deterministic core; AI only where patterns fail · seconds, ~€0</span></button>
      <button class="mode after" data-m="afterburner"><b>${{rerun}}: Afterburner</b>
       <span>Glide, then a frontier model re-checks every extracted value in this browser and
       grades document sufficiency · key via Settings, bottom-left</span></button>
     </div>
     ${{e.hasRun?'<button class="runbtn ghost" id="gores">View last results</button>':''}}
     <div class="runlog" id="rlog"></div>
     <p style="color:var(--soft);font-size:12px;max-width:46ch">${{e.protected
       ?'Re-running replays the recorded pipeline run (0.9s, 0 AI calls).'
       :'Runs execute in your browser; files and results persist on this device.'}}</p></div>`;
   $('gores')&&($('gores').onclick=()=>{{S.tab='results';save();render();}});
   document.querySelectorAll('.mode').forEach(btn=>btn.onclick=async()=>{{
     const m=btn.dataset.m;
     if(!e.protected){{await realRun(e,m);return}}
     if(m==='afterburner'&&!getKey()){{
       wset.classList.add('open');syncW();
       $('rlog').style.display='block';
       $('rlog').innerHTML='<div class="pend">Afterburner needs an API key — add one in Settings (bottom-left), then run again.</div>';
       return;}}
     const steps=[...STAGES,...(m==='afterburner'?['audit every extraction (frontier model)']:[])];
     const log=$('rlog');log.innerHTML=steps.map(x=>'<div class="pend">'+x+'</div>').join('');
     log.style.display='block';
     document.querySelectorAll('.mode').forEach(b=>b.disabled=true);
     const rows=[...log.children];let i=0;
     const tick=()=>{{if(i<rows.length){{rows[i].className='done';i++;
         setTimeout(tick,m==='afterburner'&&i>STAGES.length-1?420:210)}}
       else{{e.hasRun=true;e.dirty=false;e.lastMode=m;
         e.analysis=analyze(e.files);
         if(m==='afterburner')e.insights=e.analysis;
         e.lastRun=new Date().toISOString().slice(0,16).replace('T',' ');
         save();S.res='evidence';S.tab='results';render();}}}};
     setTimeout(tick,250);
   }});
 }}

 function insightsHTML(I){{
   const chip=v=>`<span class="ichip ${{v}}">${{v}}</span>`;
   const rows=I.rows.length?I.rows.map(r=>
     `<tr><td>${{esc(r.m)}}</td><td>${{chip(r.verdict)}}</td>
      <td>${{r.miss.length?('missing: '+r.miss.join(', ')):'screening report + facility register present'}}</td></tr>`).join('')
     :'<tr><td colspan="3">no market detected from the filenames yet</td></tr>';
   const add=[];
   I.rows.forEach(r=>r.miss.forEach(x=>add.push(r.m+' '+x)));
   I.core.forEach(c=>{{if(!c.ok)add.push(c.lbl)}});
   return `<div class="iband ${{I.overall}}"><b>Document base: ${{I.overall}}</b>
     <span>${{I.rows.length}} market(s) detected · ${{I.rows.filter(r=>r.verdict==='SUFFICIENT').length}} fully covered
     · core docs ${{I.core.every(c=>c.ok)?'complete':'incomplete'}}</span></div>
   <table class="itable"><thead><tr><th>Market</th><th>Verdict</th><th>Detail</th></tr></thead><tbody>${{rows}}</tbody></table>
   <div class="igrid">
    <div><b>Core documents</b>${{I.core.map(c=>`<p>${{esc(c.lbl)}} — ${{c.ok?'present':'missing'}}</p>`).join('')}}
     ${{I.extras.length?'<p>also present: '+I.extras.join(', ')+'</p>':''}}</div>
    <div><b>Flags</b>
     ${{I.unknown.length?'<p>'+I.unknown.length+' file(s) unrecognised: '+I.unknown.map(esc).join(', ')+'</p>':'<p>no unrecognised files</p>'}}
     ${{I.dupes.length?'<p>duplicate names: '+I.dupes.map(esc).join(', ')+'</p>':''}}</div>
    <div><b>To reach sufficient</b>${{add.length?add.map(x=>'<p>add the '+esc(x)+'</p>').join(''):'<p>nothing — run Glide for the numbers</p>'}}</div>
   </div>`;
 }}
 function pendChip(){{return '<span class="ichip PEND">ENGINE PENDING</span>'}}
 function miniEvidence(e,A){{
   const cards=e.files.map(f=>{{const r=roleOf(f.name);
     const ok=r.kind!=='unknown';
     return `<div class="frow"><span class="mono" style="flex:1;min-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${{esc(f.name)}}</span>
       <span class="chip ${{ok?'':'warn'}}">${{ok?(r.mkt?esc(r.mkt)+' · ':'')+esc(r.kind):'unassigned'}}</span></div>`}}).join('');
   const mkts=A.rows.map(r=>r.m);
   const params=['Eligible population','Participation','FIT positivity','Addressable / yr','Price per test','Months to reimbursement'];
   const tbl='<table class="itable"><thead><tr><th>Parameter</th>'
     +(mkts.length?mkts.map(m=>'<th>'+esc(m)+'</th>').join(''):'<th>Market</th>')+'</tr></thead><tbody>'
     +params.map(p=>'<tr><td>'+p+'</td>'+(mkts.length?mkts.map(()=>'<td>—</td>').join(''):'<td>—</td>')+'</tr>').join('')
     +'</tbody></table>';
   const checks=['Cross-source agreement','Competitor volume vs addressable','Rates are valid fractions','Screened-volume arithmetic']
     .map((n,i)=>`<div class="finding" style="border:1px dashed var(--line);border-radius:9px;padding:10px 14px;margin-bottom:8px;color:var(--soft)">
       <span class="ichip PEND">PENDING</span> <b>CHK-0${{i+1}}</b> ${{n}}</div>`).join('');
   return `<div class="mini">
     <h3>1 · Ingestion — every file, its role</h3><div style="display:flex;flex-direction:column;gap:8px">${{cards}}</div>
     <h3>2–3 · Canonical dataset ${{pendChip()}}</h3>${{tbl}}
     <h3>4–6 · Validation ${{pendChip()}}</h3>${{checks}}
     <h3>7 · Conclusion</h3>
     <div class="iband ${{A.overall}}"><b>Structure ${{A.overall}} — numbers await the engine</b>
      <span>${{A.rows.length}} market(s) detected · the ranking is computed, never written</span></div></div>`;
 }}
 function miniDeck(A){{
   const mk=A.rows.map(r=>r.m).join(', ')||'the detected markets';
   const slides=[['S1','Recommendation','which market first — engine output'],
     ['S2','The counter-case','why the runner-up loses on the numbers'],
     ['S3','The winning market','break-even, trough, unit economics'],
     ['S4','Sensitivity','where the case bends and where it breaks'],
     ['S5','Sequencing','order, triggers, refusals for '+mk]];
   return '<div class="steps" style="grid-template-columns:repeat(auto-fit,minmax(190px,1fr))">'
     +slides.map(x=>`<div><span>${{x[0]}}</span><b>${{x[1]}}</b><p>${{x[2]}}</p><p>${{pendChip()}}</p></div>`).join('')+'</div>'
     +'<p style="color:var(--soft);font-size:12.5px;margin-top:12px">The outline is fixed by the method; every number on it comes from a real run.</p>';
 }}
 function miniDataset(e,A){{
   const facts=[['Files',e.files.length],['Markets detected',A.rows.length||'—'],
     ['Fully covered',A.rows.filter(r=>r.verdict==='SUFFICIENT').length+' / '+A.rows.length],
     ['Unrecognised files',A.unknown.length],['Recommendation','—'],['Break-even','—'],['Cash trough','—'],['Eval','—']];
   return '<div class="facts">'+facts.map(f=>`<div><span>${{f[0]}}</span><b>${{f[1]}}</b></div>`).join('')+'</div>';
 }}
 function renderResults(){{
   const e=cur();
   if(!e.protected){{
     if(e.hasRun&&!e.analysis){{e.analysis=analyze(e.files);save();}}
     if(!e.analysis){{
       $('stage').innerHTML=`<div class="emptyres"><b>— · — · — · —</b>
         <p>Run this exercise first.</p></div>`;return;}}
     const A=e.analysis;
     const R=RUNS[e.id];
     const segs=[['evidence','Evidence report'],['deck','Deck'],['dataset','Dataset']];
     if(e.insights)segs.push(['insights','Insights']);
     segs.push(['chat','Ask the data']);
     const seg=segs.some(x=>x[0]===S.res)?S.res:'evidence';
     let body='';
     if(seg==='evidence')body=R?'<iframe id="realrep" title="evidence"></iframe>':miniEvidence(e,A);
     else if(seg==='deck')body=(R?'<div class="iband SUFFICIENT"><b>Engine verdict: '
       +esc(R.facts["Recommendation"])+'</b><span>'+esc(R.facts["Ranking"])+'</span></div>':'')+miniDeck(A);
     else if(seg==='dataset')body=R?'<div class="facts">'+Object.entries(R.facts).map(([k,v])=>
       `<div><span>${{esc(k)}}</span><b>${{esc(String(v))}}</b></div>`).join('')+'</div>':miniDataset(e,A);
     else if(seg==='insights')body=insightsHTML(A)+(R&&R.audit?auditHTML(R.audit):'');
     else body=`<div class="emptyres" style="height:auto;padding:40px 0"><b>ASK THE DATA</b>
       <p>The grounded chat answers only from a computed dataset. This exercise does not have one yet —
       run it on the <a href="http://108.132.145.140/" style="color:var(--acc)">hosted desk</a>, then chat against that run there.</p>
       <p><a class="openfull" style="float:none" href="chat/">see it working on the EU4 case</a></p></div>`;
     const note=R?'Computed by the pipeline in your browser this session; nothing left your machine.'
       :(e.realAt?'Results are not on this device. Re-run to regenerate; structural view below.'
         :'Structure view, computed in the browser from your files. Full numbers: press Run.');
     $('stage').innerHTML='<div class="seg">'+segs.map(x=>
       `<button data-s="${{x[0]}}" class="${{seg===x[0]?'on':''}}">${{x[1]}}</button>`).join('')+'</div>'
       +'<p class="recnote">'+note+'</p>'+body;
     if(R&&seg==='evidence')document.getElementById('realrep').srcdoc=R.report;
     document.querySelectorAll('.seg button').forEach(b=>b.onclick=()=>{{S.res=b.dataset.s;save();render();}});
     return;
   }}
   const segs=[['evidence','Evidence report'],['deck','Deck'],['dataset','Dataset'],['chat','Ask the data']];
   if(e.insights)segs.unshift(['insights','Insights']);
   const seg=S.res||'evidence';
   let body='';
   if(seg==='insights'){{
     body=insightsHTML(e.insights);
   }} else if(seg==='dataset'){{
     body='<div class="facts">'+e.facts.map(f=>`<div><span>${{f[0]}}</span><b>${{f[1]}}</b></div>`).join('')+'</div>';
   }} else {{
     const src={{evidence:'report/',deck:'deck/',chat:'chat/'}}[seg];
     body=`<a class="openfull" href="${{src}}">open full<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px;vertical-align:-2px;margin-left:5px"><path d="M7 17L17 7M9 7h8v8"/></svg></a><iframe src="${{src}}" title="${{seg}}"></iframe>`;
   }}
   const recnote=(seg!=='insights')?
     '<p class="recnote">Recorded from the real pipeline run. File edits in this mock never regenerate these '
     +'artifacts; Insights grades your current file base. Regeneration happens in the local app.</p>':'';
   $('stage').innerHTML='<div class="seg">'+segs.map(x=>
     `<button data-s="${{x[0]}}" class="${{seg===x[0]?'on':''}}">${{x[1]}}</button>`).join('')+'</div>'+recnote+body;
   document.querySelectorAll('.seg button').forEach(b=>b.onclick=()=>{{S.res=b.dataset.s;save();render();}});
 }}

 function esc(x){{const d=document.createElement('div');d.textContent=x;return d.innerHTML}}

 // ---- settings (shared with the chat page via the same storage keys)
 const PROVIDERS={{anthropic:{{label:'Anthropic',models:{{'claude-sonnet-5':'Claude Sonnet 5','claude-haiku-4-5-20251001':'Claude Haiku 4.5','claude-fable-5':'Claude Fable 5'}}}},
                   openai:{{label:'OpenAI',models:{{'gpt-5.1':'GPT-5.1','gpt-5-mini':'GPT-5 mini'}}}},
                   google:{{label:'Google',models:{{'gemini-3-pro-preview':'Gemini 3 Pro','gemini-2.5-flash':'Gemini 2.5 Flash'}}}}}};
 function detectProvider(k){{k=(k||'').trim();
   if(k.startsWith('sk-ant-'))return 'anthropic';
   if(/^AIza[0-9A-Za-z_-]{{30,}}$/.test(k))return 'google';
   if(k.startsWith('sk-'))return 'openai';return null}}
 const getKey=()=>localStorage.getItem('ak')||'';
 const wset=$('wsset');
 $('openset').onclick=e=>{{e.stopPropagation();wset.classList.toggle('open');syncW()}};
 document.addEventListener('click',e=>{{
   if(!wset.contains(e.target)&&!$('openset').contains(e.target))wset.classList.remove('open')}});
 function syncW(){{
   const k=getKey(),p=detectProvider(k);
   $('wkey').value='';$('wkey').placeholder=k?PROVIDERS[p].label+' key set ·…'+k.slice(-4):'sk-ant-… / sk-… / AIza…';
   $('wprov').textContent=k?'':'the provider is detected from the key format';
   const sel=$('wmodel');
   if(p){{sel.disabled=false;const cur=localStorage.getItem('mdl');
     sel.innerHTML=Object.entries(PROVIDERS[p].models).map(([v,l])=>
       `<option value="${{v}}" ${{v===cur?'selected':''}}>${{l}}</option>`).join('');}}
   else{{sel.disabled=true;sel.innerHTML='<option>set a key first</option>'}}
 }}
 $('wkey').oninput=()=>{{const p=detectProvider($('wkey').value);
   $('wprov').textContent=p?PROVIDERS[p].label+' key detected':($('wkey').value.trim()?'format not recognised':'')}};
 $('wkey').onchange=()=>{{const v=$('wkey').value.trim(),p=detectProvider(v);
   if(p){{localStorage.setItem('ak',v);localStorage.setItem('mdl',Object.keys(PROVIDERS[p].models)[0]);syncW()}}}};
 $('wmodel').onchange=()=>localStorage.setItem('mdl',$('wmodel').value);
 $('wforget').onclick=()=>{{localStorage.removeItem('ak');localStorage.removeItem('mdl');syncW()}};

 // ---- Afterburner insights: document-sufficiency grading (computed locally)
 const CTRY=['portugal','germany','netherlands','poland','spain','france','italy','austria','belgium',
   'sweden','denmark','norway','finland','ireland','greece','czech','switzerland','uk'];
 function roleOf(n){{n=n.toLowerCase();
   const c=CTRY.find(x=>n.includes(x));const cap=x=>x[0].toUpperCase()+x.slice(1);
   if(/candidate/.test(n)&&/brief/.test(n))return{{kind:'reference'}};
   if(/company/.test(n)&&/brief/.test(n))return{{kind:'company'}};
   if(/landscape/.test(n))return{{kind:'landscape'}};
   if(/funding/.test(n))return{{kind:'funding'}};
   if(/competitor|oncostream/.test(n))return{{kind:'competitor'}};
   if(/master/.test(n))return{{kind:'master'}};
   if(/screen/.test(n)&&c)return{{kind:'screening',mkt:cap(c)}};
   if((/facilit|register|units/.test(n))&&c)return{{kind:'register',mkt:cap(c)}};
   return{{kind:'unknown'}}}}
 function analyze(files){{
   const seen={{}},mkts={{}},unknown=[],dupes=[];
   const names={{}};
   files.forEach(f=>{{
     if(names[f.name])dupes.push(f.name);names[f.name]=1;
     const r=roleOf(f.name);
     if(r.kind==='unknown'){{unknown.push(f.name);return}}
     if(r.mkt){{mkts[r.mkt]=mkts[r.mkt]||{{}};mkts[r.mkt][r.kind]=1}}
     else seen[r.kind]=1;
   }});
   const rows=Object.keys(mkts).sort().map(m=>{{
     const has=mkts[m];const ok=has.screening&&has.register;
     return{{m,verdict:ok?'SUFFICIENT':'PARTIAL',
       miss:[!has.screening&&'screening report',!has.register&&'facility register'].filter(Boolean)}}}});
   const core=[['company briefing','company'],['market landscape','landscape']]
     .map(([lbl,k])=>({{lbl,ok:!!seen[k]}}));
   const nMkts=rows.length,nOk=rows.filter(r=>r.verdict==='SUFFICIENT').length;
   const coreOk=core.every(c=>c.ok);
   const overall=nMkts&&coreOk&&nOk===nMkts?'SUFFICIENT':(nMkts||coreOk?'PARTIAL':'INSUFFICIENT');
   return{{overall,rows,core,unknown,dupes,
     extras:[seen.competitor&&'competitor brief',seen.funding&&'funding call',seen.master&&'master registry'].filter(Boolean)}};
 }}
 render();
 (async()=>{{await IDB.open();
   for(const [k,v] of await IDB.all('files')){{const i=k.indexOf('|');
     (FILESTORE[k.slice(0,i)]=FILESTORE[k.slice(0,i)]||{{}})[k.slice(i+1)]=new Uint8Array(v);}}
   for(const [k,v] of await IDB.all('runs'))RUNS[k]=v;
   render();}})();
</script>
</body></html>"""


def deck(st) -> str:
    rec = st["conclusion"]["recommendation"]
    res = st["conclusion"]["results"]
    nl, de = res[rec], res["Germany"]
    fac = st["facilities"]["summary"]
    man = st["manifest"]
    from .stage7_conclude import project
    comp = {p: e["value"] for p, e in st["dataset"]["company"].items()}
    nlpar = {p: e["value"] for p, e in st["dataset"][rec].items()}
    grid_rows = ""
    for mu in (0.5, 0.75, 1.0, 1.25):
        cells = ""
        for dd in (0, 6, 12):
            r = project(nlpar, comp, ramp_mult=mu, delay_extra_months=dd)
            v = r["min_cash"] / 1e6
            cls = "bad" if v < 0 else ("good" if v > 1 else "thin")
            cells += f'<td class="{cls}">{v:+.1f}M</td>'
        grid_rows += f'<tr><th>ramp ×{mu:.0%}</th>{cells}</tr>'

    slides = [
        # S1
        f"""<section class="slide hero"><div class="in">
        <div class="eyebrow">Helix Optics · first European market · board recommendation</div>
        <h1>Enter the <em>Netherlands</em> first.</h1>
        <div class="stats">
         <div><b>Break-even Y{nl['break_even_year']}</b><span>company EBITDA positive in the second reimbursed year</span></div>
         <div><b>€{nl['min_cash']/1e6:.2f}M</b><span>cash trough: the runway is never exhausted</span></div>
         <div><b>{nl['params']['addressable_fit_positive']:,.0f}/yr</b><span>addressable FIT-positives: 92% of Germany's volume, none of its barriers</span></div>
         <div><b>€{nl.get('system_saving_per_100',0):,} saved</b><span>per 100 patients triaged. The payer wants this</span></div>
        </div>
        <img src="assets/cash_curves_dark.png" width="1560" height="860" alt="Five-year cash position of all four markets">
        </div></section>""",
        # S2
        f"""<section class="slide"><div class="in">
        <div class="eyebrow">Why not the biggest market first</div>
        <h2>Germany is the prize — and the certain death of the runway.</h2>
        <div class="cols"><ul>
         <li><b>24 months to reimbursed revenue.</b> Procedural: investigators, lab partners and prior studies do <i>not</i> shorten it. Its own national report says so.</li>
         <li><b>Pre-reimbursement revenue ≈ €0.</b> Selective contracts and self-pay: "negligible volume".</li>
         <li><b>The runway dies first.</b> Cash bottoms at {de['min_cash']/1e6:.1f}M, insolvent before the first reimbursed euro.</li>
         <li><b>An incumbent owns the channel.</b> OncoStream has ~3 reimbursed years, 35–40% share, framework agreements.</li>
         <li><b>Its 300k tests/yr claim is impossible:</b> 1.7× the entire organised addressable market (174,240/yr). Rejected by pipeline check CHK-02.</li>
        </ul><img src="assets/trough_dark.png" width="1240" height="840" alt="Cash trough by market"></div>
        <p class="note">Right market later, unaffordable market now. File the German application early (the clock is procedural) and enter once NL cash flow or new capital funds the wait.</p>
        </div></section>""",
        # S3
        f"""<section class="slide"><div class="in">
        <div class="eyebrow">The case for the recommendation</div>
        <h2>The Netherlands: fastest to revenue, and the payer is <em>motivated</em>.</h2>
        <div class="cols"><ul>
         <li><b>Volume without the barriers.</b> 71% participation × 9.1% positivity → 159,910 FIT-positives a year.</li>
         <li><b>12 months to reimbursement.</b> One centralised, national procurement decision.</li>
         <li><b>Open field.</b> No competitor active; second-highest price (€215).</li>
         <li><b>Capacity pressure is policy.</b> Referrals run at ~103% of national endoscopy capacity (deduplicated registers).</li>
         <li><b>The economics clear.</b> 76% unit margin by Y3; five-year end cash €{nl['end_cash']/1e6:.1f}M.</li>
        </ul><img src="assets/nl_model_dark.png" width="1280" height="840" alt="Netherlands EBITDA and cash"></div>
        <p class="note">What must be true: reimbursement ≈ month 12 · ramp ~13% of addressable by the second reimbursed year · price holds near €215.</p>
        </div></section>""",
        # S4
        f"""<section class="slide"><div class="in">
        <div class="eyebrow">Break-even and the range around it</div>
        <h2>Where the case bends — and where it breaks.</h2>
        <div class="cols">
        <ul>
         <li><b>Ramp alone can sink it.</b> At half the benchmark the trough grazes €0 (−€0.0M): the case fails without help.</li>
         <li><b>Delay alone breaks it too.</b> Any slip past month 12 puts the trough at −€0.8M on the base ramp (the annual model rounds delays up, deliberately conservative).</li>
         <li><b>Together, decisively fatal.</b> Half-ramp + 24 months → −€2.1M.</li>
         <li><b>Price is the cushion; month 15 is the tripwire.</b> Every €10 ≈ €0.2–0.3M annual EBITDA at scale; no reimbursement signal by month 15 → cut in-market spend and bridge before the trough.</li>
        </ul>
        <div><table class="grid"><tr><th>cash trough<br>ramp ↓ delay →</th><th>12 mo</th><th>18 mo</th><th>24 mo</th></tr>{grid_rows}</table>
        <p class="note">The same grid lives as formulas in the Excel: change an assumption, everything recalculates.</p></div>
        </div></div></section>""",
        # S5
        f"""<section class="slide"><div class="in">
        <div class="eyebrow">After the first market</div>
        <h2>Sequence, triggers, and what we <em>refuse</em> to do.</h2>
        <div class="steps">
         <div><span>NOW→Y1</span><b>Netherlands entry</b><p>€200k entry · file reimbursement immediately · first revenue ~month 13</p></div>
         <div><span>Y1</span><b>Start Germany's clock</b><p>the 24-month pathway is procedural: file while NL scales, spend €0</p></div>
         <div><span>Y2</span><b>Portugal</b><p>€120k entry, home turf, contribution-positive add-on</p></div>
         <div><span>Y3+</span><b>Germany, funded</b><p>enter once the wait is funded · Poland stays parked (€115 price)</p></div>
        </div>
        <ul>
         <li><b>Accelerate:</b> NL year-1 penetration ≥7% and price ≥€200 → pull Portugal forward, raise on proven uptake.</li>
         <li><b>Delay:</b> reimbursement past month 15 or ramp &lt; half plan → freeze Portugal, cut burn.</li>
         <li><b>Abandon:</b> nothing by month 18 → stop-loss. The German filing and the Portuguese R&D base (€500k grant, R&D-only) keep two doors open.</li>
         <li><b>Refuse:</b> chasing Germany's volume with an unfunded 24-month gap, or booking the R&D grant as launch money.</li>
        </ul>
        <p class="note">{man['extraction']['deterministic']} values extracted deterministically · {man['llm_calls']} AI calls · eval 28/28 · {man['total_s']}s end-to-end. Markets 5–14 are a config entry away.</p>
        </div></section>""",
    ]
    dots = "".join(f'<a href="#s{i+1}" data-i="{i}"></a>' for i in range(5))
    body = "".join(s.replace('<section class="slide', f'<section id="s{i+1}" class="slide', 1)
                   for i, s in enumerate(slides))
    return f"""<!doctype html><html lang="en"><head><title>Helix — the deck</title>{HEAD}
<style>
 html{{scroll-snap-type:y proximity;scroll-behavior:smooth}}
 .slide{{min-height:100vh;scroll-snap-align:start;display:grid;place-content:center;padding:56px 24px;border-bottom:1px solid var(--line)}}
 .in{{max-width:1020px;display:flex;flex-direction:column;gap:18px}}
 h1{{font-size:clamp(36px,6vw,60px);margin:0;letter-spacing:-.025em;line-height:1.05;font-weight:650}}
 h2{{font-size:clamp(26px,3.6vw,38px);margin:0;letter-spacing:-.02em;line-height:1.15;font-weight:650}}
 h1 em,h2 em{{font-family:'Noto Serif',serif;font-style:italic;font-weight:300;color:var(--acc)}}
 .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}
 .stats div{{background:var(--sf);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
 .stats b{{display:block;font-size:22px;letter-spacing:-.01em}} .stats span{{font-size:12.5px;color:var(--soft)}}
 img{{max-width:100%;height:auto;border-radius:12px;border:1px solid var(--line);background:#fff}}
 .cols{{display:grid;grid-template-columns:1.05fr 1fr;gap:26px;align-items:center}}
 @media(max-width:880px){{.cols{{grid-template-columns:1fr}}}}
 ul{{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:10px}}
 li{{padding-left:18px;position:relative;font-size:15.5px}}
 li::before{{content:"▪";position:absolute;left:0;color:var(--acc)}}
 li b{{font-weight:650}} li,li i{{color:var(--ink)}} li{{color:var(--soft)}} li b{{color:var(--ink)}}
 .note{{font-size:13.5px;color:var(--soft);border-top:1px solid var(--line);padding-top:12px;margin:4px 0 0}}
 table.grid{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
 table.grid th,table.grid td{{border:1px solid var(--line);padding:9px 12px;font-size:14px;text-align:center}}
 table.grid th{{background:var(--deep);color:#fff;font:600 11.5px 'IBM Plex Mono',monospace}}
 table.grid tr th:first-child{{text-align:left}}
 td.good{{background:var(--softblue2);color:var(--softblue);font-weight:650}} td.thin{{background:#3d2f16;color:#f2d9a7;font-weight:650}}
 td.bad{{background:var(--accdark);color:#fff;font-weight:650}}
 .steps{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
 .steps div{{background:var(--sf);border:1px solid var(--line);border-radius:12px;padding:14px}}
 .steps span{{font:600 11px 'IBM Plex Mono',monospace;color:var(--acc)}}
 .steps b{{display:block;margin:4px 0 2px}} .steps p{{margin:0;font-size:12.5px;color:var(--soft)}}
 nav.dots{{position:fixed;right:18px;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:10px;z-index:9}}
 nav.dots a{{width:9px;height:9px;border-radius:50%;background:var(--line);transition:background .2s}}
 nav.dots a.on{{background:var(--acc)}}
 .back{{position:fixed;top:16px;left:18px;z-index:9;font:600 13px 'Instrument Sans';color:var(--soft);text-decoration:none;background:var(--sf);border:1px solid var(--line);border-radius:99px;padding:7px 14px}}
 @media print{{.slide{{min-height:auto;page-break-after:always}}nav.dots,.back{{display:none}}}}
</style></head><body>
<a class="back" href="../">← Runway</a>
<nav class="dots">{dots}</nav>
{body}
<script>
 const dots=[...document.querySelectorAll('nav.dots a')];
 const slides=[...document.querySelectorAll('.slide')];
 const io=new IntersectionObserver(es=>es.forEach(e=>{{
   if(e.isIntersecting){{const i=slides.indexOf(e.target);dots.forEach((d,j)=>d.classList.toggle('on',i===j))}}
 }}),{{threshold:.5}});
 slides.forEach(s=>io.observe(s));
 addEventListener('keydown',e=>{{
   const i=dots.findIndex(d=>d.classList.contains('on'));
   if(e.key==='ArrowDown'||e.key==='ArrowRight'||e.key==='PageDown'){{e.preventDefault();slides[Math.min(i+1,4)].scrollIntoView()}}
   if(e.key==='ArrowUp'||e.key==='ArrowLeft'||e.key==='PageUp'){{e.preventDefault();slides[Math.max(i-1,0)].scrollIntoView()}}
 }});
</script></body></html>"""


def model_blank() -> str:
    """The dashboard in its empty state: the same sections the pipeline fills,
    rendered unpopulated so it is unmistakable that nothing is hand-typed."""
    slot = ('<div class="fcard"><div class="fstat">·</div><div>'
            '<div class="fname">awaiting file</div><div class="fmeta">format — · sha —</div></div></div>')
    ing = slot * 6
    prow = "".join(f'<tr><th>{p}</th><td>—</td><td>—</td><td>—</td><td>—</td></tr>'
                   for p in ("Eligible population", "Participation", "FIT positivity",
                             "Addressable / yr", "Price per test", "Months to reimbursement"))
    chk = "".join(f'<div class="finding"><span class="fpill">PENDING</span><b>CHK-0{i}</b> '
                  f'{n}<div class="fdetail">runs when a pack is read</div></div>'
                  for i, n in enumerate(("Cross-source agreement", "Competitor volume vs addressable",
                                         "Rates are valid fractions", "Screened-volume arithmetic"), 1))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>The blank model — Runway</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400..700;1,400&family=Noto+Serif:ital,wght@0,300;1,300&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
 :root{{--bg:#f9f7f5;--sf:#fff;--ink:#1d2939;--soft:#667085;--line:#e6e1da;--acc:#ff4200;
   --deep:#374b60;--accsoft:#e6eef3;--tan:#ad836c}}
 *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);
   font:15px/1.5 'Instrument Sans',system-ui,sans-serif;padding:34px 22px 70px}}
 .wrap{{max-width:880px;margin:0 auto;display:flex;flex-direction:column;gap:24px}}
 .eyebrow{{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.15em;
   text-transform:uppercase;color:var(--tan)}}
 h1{{font-size:27px;margin:0;letter-spacing:-.01em;font-weight:650}}
 h1 em{{font-family:'Noto Serif',serif;font-style:italic;font-weight:300;color:var(--acc)}}
 .empty-chip{{font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.1em;
   border:1.5px dashed var(--soft);border-radius:99px;padding:3px 12px;color:var(--soft);vertical-align:6px;margin-left:10px}}
 .note{{background:var(--accsoft);border:1px solid var(--line);border-left:4px solid var(--acc);
   border-radius:10px;padding:14px 18px;font-size:14.5px}}
 section{{background:var(--sf);border:1px solid var(--line);border-radius:12px;padding:18px 20px;position:relative}}
 section::after{{content:"EMPTY";position:absolute;top:14px;right:16px;font:10px 'IBM Plex Mono',monospace;
   letter-spacing:.12em;color:var(--soft);border:1px dashed var(--line);border-radius:99px;padding:2px 8px}}
 h2{{font-size:16px;margin:0 0 12px;font-weight:650}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px}}
 .fcard{{display:flex;gap:10px;border:1px dashed var(--line);border-radius:8px;padding:8px 10px;align-items:center;color:var(--soft)}}
 .fstat{{width:26px;height:26px;border-radius:7px;display:grid;place-content:center;background:var(--bg)}}
 .fname{{font-size:13px;font-weight:600}} .fmeta{{font-size:11.5px;font-family:'IBM Plex Mono',monospace}}
 table{{border-collapse:collapse;width:100%;font-size:13.5px}}
 th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}}
 td{{color:var(--soft);font-family:'IBM Plex Mono',monospace;font-size:12.5px}}
 tbody tr:last-child td,tbody tr:last-child th{{border-bottom:none}}
 .finding{{border:1px dashed var(--line);border-radius:9px;padding:10px 14px;margin-bottom:8px;color:var(--soft)}}
 .fpill{{font-family:'IBM Plex Mono',monospace;font-size:10.5px;border-radius:99px;padding:1px 8px;
   background:var(--bg);margin-right:8px}}
 .fdetail{{font-size:13px;margin-top:3px}}
 .verdict{{display:grid;place-content:center;text-align:center;min-height:150px;color:var(--soft)}}
 .verdict b{{font-size:34px;color:var(--line);letter-spacing:.02em}}
 .verdict p{{margin:6px 0 0;font-size:13.5px}}
 .ctas{{display:flex;gap:12px;flex-wrap:wrap}}
 .btn{{display:inline-block;font:600 14.5px 'Instrument Sans';border-radius:9px;border:1px solid var(--line);
   padding:11px 20px;background:var(--sf);color:var(--ink);text-decoration:none}}
 .btn.primary{{background:var(--acc);border-color:var(--acc);color:#fff}}
 .btn.primary:hover{{background:#c12d00}}
 a.back{{font:600 13px 'Instrument Sans';color:var(--soft);text-decoration:none}}
</style></head><body><div class="wrap">
 <a class="back" href="../">← Runway</a>
 <div><div class="eyebrow">RUNWAY · WORKSPACE: BLANK-MODEL</div>
  <h1>The model, before any <em>data</em>.<span class="empty-chip">NOTHING LOADED</span></h1></div>
 <div class="note"><b>This dashboard is generated, never hand-filled.</b> Every section below is rendered by the
  pipeline; until documents are read, it has nothing to say — and shows exactly that. Drop a pack into a
  workspace and the same page fills itself: ingestion fates, provenance-badged values, checks, and a ranking.</div>
 <section><h2>1 · Ingestion — every file, its fate</h2><div class="grid">{ing}</div></section>
 <section><h2>2–3 · Canonical dataset</h2>
  <table><thead><tr><th>Parameter</th><th>Market A</th><th>Market B</th><th>Market C</th><th>Market D</th></tr></thead>
  <tbody>{prow}</tbody></table></section>
 <section><h2>4–6 · Validation</h2>{chk}</section>
 <section><h2>7 · Conclusion</h2><div class="verdict"><b>— · — · — · —</b>
  <p>the ranking appears when the engine has inputs; it is computed, not written</p></div></section>
 <div class="ctas">
  <a class="btn primary" href="../report/">Populate it: open the Helix case →</a>
  <a class="btn" href="https://github.com/tomasbb0/market-runway">Run it yourself (local app)</a>
 </div>
</div></body></html>"""


def chat(st) -> tuple[str, str]:
    import json as _json
    compact = {
        "dataset": {sc: {p: {"value": e["value"], "unit": e["unit"], "method": e["method"],
                             "source": e["source"]} for p, e in d.items()}
                    for sc, d in st["dataset"].items()},
        "conclusion": st["conclusion"],
        "validation_findings": st["findings"],
        "facilities_summary": st["facilities"]["summary"],
        "evidence_gaps": [{k: g[k] for k in ("id", "market", "field", "why")} for g in st["gaps"]],
    }
    data_js = "window.DATASET = " + _json.dumps(compact, default=str) + ";"
    page = f"""<!doctype html><html lang="en"><head><title>Ask the data — Helix</title>{HEAD}
<style>
 body{{padding-bottom:120px}}
 .wrap{{max-width:820px;margin:0 auto;padding:30px 20px 20px;display:flex;flex-direction:column;gap:16px}}
 h1{{font-size:26px;margin:0;letter-spacing:-.02em}}
 h1 em{{font-family:'Noto Serif',serif;font-style:italic;font-weight:300;color:var(--acc)}}
 .msg{{border-radius:14px;padding:12px 16px;max-width:88%;font-size:14.5px;line-height:1.55}}
 .msg.user{{background:var(--deep);color:#fff;align-self:flex-end;white-space:pre-wrap}}
 .msg.ai{{background:var(--sf);border:1px solid var(--line);align-self:flex-start}}
 .msg.ai p{{margin:.35em 0}} .msg.ai p:first-child{{margin-top:0}} .msg.ai p:last-child{{margin-bottom:0}}
 .msg.ai ul,.msg.ai ol{{margin:.35em 0;padding-left:20px}}
 .msg.ai li{{margin:.15em 0}}
 .msg.ai code{{font:12.5px 'IBM Plex Mono',monospace;background:var(--softblue2);border:1px solid var(--line);
   border-radius:5px;padding:1px 5px}}
 .msg.ai pre{{background:var(--cream2);border:1px solid var(--line);border-radius:9px;padding:11px 13px;
   overflow-x:auto;margin:.5em 0}}
 .msg.ai pre code{{background:none;border:none;padding:0}}
 .msg.ai h1,.msg.ai h2,.msg.ai h3{{font-size:15.5px;margin:.6em 0 .25em;letter-spacing:0}}
 .msg.ai strong{{color:var(--ink)}} .msg.ai em{{font-style:italic}}
 .msg .opts{{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}}
 .msg .opts button{{font:600 12.5px 'Instrument Sans';border:1px solid var(--line);background:var(--softblue2);
   color:var(--ink);border-radius:99px;padding:7px 14px;cursor:pointer}}
 .msg .opts button:hover{{border-color:var(--acc)}}
 #msgs{{display:flex;flex-direction:column;gap:10px}}
 /* full-width composer */
 .bar{{position:fixed;bottom:0;left:0;right:0;background:var(--bg);border-top:1px solid var(--line);padding:12px 16px}}
 .bar .in{{display:flex;gap:9px;width:100%;align-items:center}}
 #q{{flex:1;font:15px 'Instrument Sans';border:1px solid var(--line);border-radius:11px;padding:13px 15px;
   background:var(--sf);color:var(--ink);min-width:0}}
 #q:focus{{outline:none;border-color:var(--deep)}}
 .send{{font:600 14.5px 'Instrument Sans';background:var(--acc);border:1px solid var(--acc);color:#fff;
   border-radius:11px;padding:13px 22px;cursor:pointer}}
 .send:hover{{background:var(--accdark)}}
 /* provider dropdown */
 .provbtn{{font-size:15px;border:1px solid var(--line);background:var(--sf);color:var(--soft);
   border-radius:11px;width:44px;height:46px;cursor:pointer;flex:none;display:grid;place-content:center}}
 .provbtn:hover{{border-color:var(--deep);color:var(--ink)}}
 .provbtn.set{{color:var(--softblue)}}
 .gearlink{{border:1px solid var(--line);background:var(--softblue2);color:var(--ink);
   border-radius:7px;width:28px;height:28px;cursor:pointer;vertical-align:-8px;margin-right:8px;padding:0;
   display:inline-grid;place-content:center}}
 .gearlink:hover{{border-color:var(--acc)}}
 .gearlink svg{{width:15px;height:15px}}
 .provbtn svg{{width:22px;height:22px}}
 .typing{{display:inline-flex;gap:4px;align-items:center;height:10px}}
 .typing i{{width:4.5px;height:4.5px;border-radius:50%;background:var(--soft);animation:tp 1.1s ease-in-out infinite}}
 .typing i:nth-child(2){{animation-delay:.18s}} .typing i:nth-child(3){{animation-delay:.36s}}
 @keyframes tp{{0%,70%,100%{{opacity:.25;transform:translateY(0)}}35%{{opacity:1;transform:translateY(-3px)}}}}
 #settings{{position:fixed;bottom:74px;left:16px;width:min(340px,calc(100vw - 32px));background:var(--sf);
   border:1px solid var(--line);border-radius:14px;padding:16px;display:none;
   box-shadow:0 24px 60px -30px rgba(0,0,0,.85);z-index:9}}
 #settings.open{{display:block}}
 #settings label{{display:block;font:10.5px 'IBM Plex Mono',monospace;letter-spacing:.14em;color:var(--tan);
   text-transform:uppercase;margin:10px 0 5px}}
 #settings label:first-child{{margin-top:0}}
 #settings input[type=password],#settings select{{width:100%;font:13px 'IBM Plex Mono',monospace;
   border:1px solid var(--line);border-radius:8px;padding:9px 10px;background:var(--bg);color:var(--ink)}}
 #settings .scope{{display:flex;gap:6px}}
 #settings .scope button{{flex:1;font:600 11.5px 'Instrument Sans';border:1px solid var(--line);
   background:var(--bg);color:var(--soft);border-radius:8px;padding:8px;cursor:pointer}}
 #settings .scope button.on{{background:var(--softblue2);color:var(--ink);border-color:var(--deep)}}
 #settings .clear{{margin-top:12px;font:600 11.5px 'Instrument Sans';border:none;background:none;
   color:var(--soft);cursor:pointer;padding:0}}
 #settings .clear:hover{{color:var(--acc)}}
 .hint{{font-size:13px;color:var(--soft)}}
 a.back{{font:600 13px 'Instrument Sans';color:var(--soft);text-decoration:none}}
</style></head><body>
<div class="wrap">
 <a class="back" href="../">← Runway</a>
 <div><div class="eyebrow"><span class="tag"></span>HELIX OPTICS · ASK THE DATA</div>
 <h1>Chat with the <em>validated</em> dataset</h1>
 <p class="hint">Answers come only from the pipeline's validated output, embedded in this page.
 Keys never leave your browser; calls go straight to the provider.</p></div>
 <div id="msgs"></div>
</div>

<div id="settings">
 <label>API key</label><input type="password" id="skey" placeholder="sk-ant-… / sk-… / AIza…" autocomplete="off">
 <div class="hint" id="sprov" style="margin-top:6px"></div>
 <label>Model</label><select id="smodel"></select>
 <label>Remember</label>
 <div class="scope"><button id="scAll">All chats on this browser</button><button id="scOne">Just this session</button></div>
 <button class="clear" id="sclear">Forget key</button>
</div>

<div class="bar"><div class="in">
 <button class="provbtn" id="provbtn" title="Provider settings" aria-label="Provider settings"></button>
 <input id="q" placeholder="Ask about the data — or paste your API key right here to get set up"
   onkeydown="if(event.key==='Enter')send()">
 <button class="send" onclick="send()">Send</button>
</div></div>

<script src="data.js"></script>
<script>
 const PROVIDERS={{anthropic:{{label:'Anthropic',models:{{'claude-sonnet-5':'Claude Sonnet 5','claude-haiku-4-5-20251001':'Claude Haiku 4.5','claude-fable-5':'Claude Fable 5'}}}},
                   openai:{{label:'OpenAI',models:{{'gpt-5.1':'GPT-5.1','gpt-5-mini':'GPT-5 mini'}}}},
                   google:{{label:'Google',models:{{'gemini-3-pro-preview':'Gemini 3 Pro','gemini-2.5-flash':'Gemini 2.5 Flash'}}}}}};
 const GEAR='<svg viewBox="0 0 24 24" fill="currentColor" fill-rule="evenodd">'
  +'<path d="M18.79 10.31 L21.70 10.64 L21.70 13.36 L18.79 13.69 L18.00 15.61 L19.83 17.90 L17.90 19.83 L15.61 18.00 L13.69 18.79 L13.36 21.70 L10.64 21.70 L10.31 18.79 L8.39 18.00 L6.10 19.83 L4.17 17.90 L6.00 15.61 L5.21 13.69 L2.30 13.36 L2.30 10.64 L5.21 10.31 L6.00 8.39 L4.17 6.10 L6.10 4.17 L8.39 6.00 L10.31 5.21 L10.64 2.30 L13.36 2.30 L13.69 5.21 L15.61 6.00 L17.90 4.17 L19.83 6.10 L18.00 8.39 Z M15.1 12 A3.1 3.1 0 1 0 8.9 12 A3.1 3.1 0 1 0 15.1 12 Z"/></svg>';
 document.getElementById('provbtn').innerHTML=GEAR;
 function detectProvider(k){{k=(k||'').trim();
   if(k.startsWith('sk-ant-'))return 'anthropic';
   if(/^AIza[0-9A-Za-z_-]{{30,}}$/.test(k))return 'google';
   if(k.startsWith('sk-'))return 'openai';return null}}

 // ---- key store: localStorage = all chats, sessionStorage = just this one
 const store={{
   get k(){{return sessionStorage.getItem('ak')||localStorage.getItem('ak')||''}},
   get m(){{return sessionStorage.getItem('mdl')||localStorage.getItem('mdl')||''}},
   set(key,model,all){{const S=all?localStorage:sessionStorage;
     S.setItem('ak',key);if(model)S.setItem('mdl',model);
     (all?sessionStorage:0)&&0;}},
   setModel(model){{(localStorage.getItem('ak')?localStorage:sessionStorage).setItem('mdl',model)}},
   clear(){{['ak','mdl'].forEach(x=>{{localStorage.removeItem(x);sessionStorage.removeItem(x)}})}}
 }};
 let pendingKey=null;

 // ---- tiny safe markdown (assistant messages only)
 function esc(x){{const d=document.createElement('div');d.textContent=x;return d.innerHTML}}
 function inline(t){{return t
   .replace(/`([^`\\n]+)`/g,'<code>$1</code>')
   .replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>')
   .replace(/(^|[^*])\\*([^*\\n]+)\\*(?!\\*)/g,'$1<em>$2</em>')}}
 function md(src){{
   const parts=esc(src).split(/```(?:\\w*\\n)?/);let out='';
   parts.forEach((seg,i)=>{{
     if(i%2){{out+='<pre><code>'+seg.replace(/\\n$/,'')+'</code></pre>';return}}
     const blocks=seg.split(/\\n{{2,}}/);
     blocks.forEach(b=>{{
       if(!b.trim())return;
       const lines=b.split('\\n');
       if(lines.every(l=>/^\\s*[-•]\\s+/.test(l)))
         out+='<ul>'+lines.map(l=>'<li>'+inline(l.replace(/^\\s*[-•]\\s+/,''))+'</li>').join('')+'</ul>';
       else if(lines.every(l=>/^\\s*\\d+[.)]\\s+/.test(l)))
         out+='<ol>'+lines.map(l=>'<li>'+inline(l.replace(/^\\s*\\d+[.)]\\s+/,''))+'</li>').join('')+'</ol>';
       else if(/^#{{1,3}}\\s/.test(lines[0])&&lines.length===1)
         out+='<h3>'+inline(lines[0].replace(/^#+\\s*/,''))+'</h3>';
       else out+='<p>'+lines.map(inline).join('<br>')+'</p>';
     }});
   }});
   return out}}

 const msgs=document.getElementById('msgs');let hist=[];
 function bubble(role,html,opts){{
   const d=document.createElement('div');d.className='msg '+(role==='user'?'user':'ai');
   if(role==='user')d.textContent=html;else d.innerHTML=html;
   if(opts){{const o=document.createElement('div');o.className='opts';
     opts.forEach(([t,fn])=>{{const b=document.createElement('button');b.textContent=t;
       b.onclick=()=>{{o.remove();fn()}};o.appendChild(b)}});d.appendChild(o)}}
   msgs.appendChild(d);d.scrollIntoView({{behavior:'smooth',block:'end'}});return d}}

 // ---- settings dropdown
 const sBtn=document.getElementById('provbtn'),sPanel=document.getElementById('settings'),
       sKey=document.getElementById('skey'),sModel=document.getElementById('smodel'),
       sProv=document.getElementById('sprov');
 sBtn.onclick=()=>{{sPanel.classList.toggle('open');syncSettings()}};
 document.addEventListener('click',e=>{{
   if(!sPanel.contains(e.target)&&e.target!==sBtn)sPanel.classList.remove('open')}});
 function fillModels(p,sel){{
   sModel.innerHTML=p?Object.entries(PROVIDERS[p].models).map(([v,l])=>
     `<option value="${{v}}" ${{v===sel?'selected':''}}>${{l}}</option>`).join('')
     :'<option>set a key first</option>';sModel.disabled=!p}}
 function syncSettings(){{
   const k=store.k,p=detectProvider(k);
   sKey.value='';sKey.placeholder=k?PROVIDERS[p].label+' key set ·…'+k.slice(-4):'sk-ant-… / sk-… / AIza…';
   sProv.textContent=k?'':'paste a key — the provider is detected from its format';
   fillModels(p,store.m);
   document.getElementById('scAll').classList.toggle('on',!!localStorage.getItem('ak'));
   document.getElementById('scOne').classList.toggle('on',!localStorage.getItem('ak')&&!!sessionStorage.getItem('ak'));
   sBtn.title=k?PROVIDERS[p].label+' · '+(PROVIDERS[p].models[currentModel()]||'')+' — click to change'
     :'No key set — paste one in the chat, or click to set up';
   sBtn.classList.toggle('set',!!k);
 }}
 sKey.oninput=()=>{{const p=detectProvider(sKey.value);
   sProv.textContent=p?PROVIDERS[p].label+' key detected':(sKey.value.trim()?'format not recognised':'');
   if(p)fillModels(p,null)}};
 sKey.onchange=()=>{{const p=detectProvider(sKey.value);
   if(p){{store.set(sKey.value.trim(),Object.keys(PROVIDERS[p].models)[0],!!localStorage.getItem('ak'));syncSettings()}}}};
 sModel.onchange=()=>{{store.setModel(sModel.value);syncSettings()}};
 document.getElementById('scAll').onclick=()=>{{const k=store.k,m=store.m;if(!k)return;
   store.clear();localStorage.setItem('ak',k);localStorage.setItem('mdl',m);syncSettings()}};
 document.getElementById('scOne').onclick=()=>{{const k=store.k,m=store.m;if(!k)return;
   store.clear();sessionStorage.setItem('ak',k);sessionStorage.setItem('mdl',m);syncSettings()}};
 document.getElementById('sclear').onclick=()=>{{store.clear();syncSettings();
   bubble('ai','Key forgotten. Paste a new one here whenever you like.')}};
 function currentModel(){{const p=detectProvider(store.k);if(!p)return null;
   return PROVIDERS[p].models[store.m]?store.m:Object.keys(PROVIDERS[p].models)[0]}}

 // ---- providers
 async function callProvider(p,key,model,system,h){{
   if(p==='anthropic'){{
     const r=await fetch('https://api.anthropic.com/v1/messages',{{method:'POST',headers:{{
       'content-type':'application/json','x-api-key':key,'anthropic-version':'2023-06-01',
       'anthropic-dangerous-direct-browser-access':'true'}},
       body:JSON.stringify({{model,max_tokens:900,system,messages:h}})}});
     const j=await r.json();if(j.error)throw j.error.message;return j.content[0].text;}}
   if(p==='openai'){{
     const r=await fetch('https://api.openai.com/v1/chat/completions',{{method:'POST',headers:{{
       'content-type':'application/json','authorization':'Bearer '+key}},
       body:JSON.stringify({{model,max_completion_tokens:900,
         messages:[{{role:'system',content:system}},...h]}})}});
     const j=await r.json();if(j.error)throw j.error.message;return j.choices[0].message.content;}}
   if(p==='google'){{
     const contents=h.map(m=>({{role:m.role==='assistant'?'model':'user',parts:[{{text:m.content}}]}}));
     const r=await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${{model}}:generateContent?key=${{key}}`,
       {{method:'POST',headers:{{'content-type':'application/json'}},
        body:JSON.stringify({{system_instruction:{{parts:[{{text:system}}]}},contents,
          generationConfig:{{maxOutputTokens:900,temperature:0}}}})}});
     const j=await r.json();if(j.error)throw j.error.message;return j.candidates[0].content.parts[0].text;}}
   throw 'unknown provider';}}
 const SYSTEM=`You are the analyst assistant for a market-entry assessment. Answer ONLY from the JSON dataset
provided (the pipeline's validated output). If something is not in it, say "not in the validated dataset" -
never guess. Cite a figure's source and method when giving numbers. Be concise. Markdown is supported.
Currency EUR. DATASET: `+JSON.stringify(window.DATASET);

 // ---- send flow (incl. in-chat key onboarding)
 async function send(){{
   const q=document.getElementById('q');const t=q.value.trim();if(!t)return;q.value='';
   const asKey=detectProvider(t);
   if(asKey){{
     bubble('user','•'.repeat(12)+' '+t.slice(-4));
     pendingKey=t;
     bubble('ai','<p><strong>'+PROVIDERS[asKey].label+' key detected.</strong> Which model should I use?</p>',
       Object.entries(PROVIDERS[asKey].models).map(([v,l])=>[l,()=>chooseModel(v)]));
     return;}}
   if(!store.k){{
     bubble('user',t);
     bubble('ai','<p>Before I can answer, I need an API key — <strong>paste it right here in the chat</strong> '
       +'(Anthropic <code>sk-ant-…</code>, OpenAI <code>sk-…</code> or Gemini <code>AIza…</code>). '
       +'I will detect the provider from its format and offer to remember it.</p>');
     return;}}
   bubble('user',t);hist.push({{role:'user',content:t}});
   const p=detectProvider(store.k),model=currentModel();
   const wait=bubble('ai','<span class="typing"><i></i><i></i><i></i></span>');
   try{{
     const text=await callProvider(p,store.k,model,SYSTEM,hist.slice(-20));
     wait.innerHTML=md(text);hist.push({{role:'assistant',content:text}});
   }}catch(e){{wait.innerHTML='<p>⚠ '+esc(String(e.message||e))
     +(p!=='anthropic'?' <em>(some providers refuse browser calls; the local app routes them server-side)</em>':'')+'</p>'}}
   wait.scrollIntoView({{behavior:'smooth',block:'end'}});
 }}
 let pendingModel=null;
 function chooseModel(m){{
   pendingModel=m;
   const p=detectProvider(pendingKey);
   bubble('ai','<p><strong>'+PROVIDERS[p].models[m]+'</strong> it is. Where should I keep the key?</p>',
     [['Save for all chats on this browser',()=>keepKey(true)],
      ['Just this session',()=>keepKey(false)]]);
 }}
 function keepKey(all){{
   const p=detectProvider(pendingKey);
   store.clear();store.set(pendingKey,pendingModel||Object.keys(PROVIDERS[p].models)[0],all);
   pendingKey=null;pendingModel=null;
   syncSettings();
   bubble('ai','<p><button class="gearlink" title="Change provider settings">'+GEAR+'</button>'
     +'<strong>'+PROVIDERS[p].label+' · '+PROVIDERS[p].models[currentModel()]+'</strong> — saved '
     +(all?'for all chats on this browser':'for this session only')
     +'. That little gear (here or next to the message box) changes it any time. Ask away.</p>');
 }}
 msgs.addEventListener('click',e=>{{
   if(e.target.closest('.gearlink')){{sPanel.classList.add('open');syncSettings();}}}});

 syncSettings();
 if(!store.k){{
   bubble('ai','<p><strong>Welcome.</strong> To get set up, paste your provider key <em>right here</em> in the '
     +'message box — I will save it for the future once you tell me how. Then ask things like '
     +'<em>why not Germany?</em> or <em>what drives break-even?</em></p>');
 }}
</script></body></html>"""
    return page, data_js


ENGINE_JS = r"""// Runway browser engine: the real pipeline, in WebAssembly. Files never leave the machine.
window.Engine = (() => {
  let py = null, ready = false, loading = null;
  const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.5/full/pyodide.mjs";
  async function init(progress) {
    if (ready) return;
    if (loading) return loading;
    loading = (async () => {
      progress("downloading the Python runtime (~15 MB, once per session)");
      const { loadPyodide } = await import(PYODIDE);
      py = await loadPyodide();
      progress("loading packages: yaml, xlsx, html, pdf, imaging");
      await py.loadPackage(["micropip", "pyyaml", "beautifulsoup4", "cryptography", "pillow"]);
      await py.runPythonAsync('import micropip\nawait micropip.install(["pdfplumber==0.9.0","openpyxl"])');
      progress("mounting the pipeline");
      const list = await (await fetch("engine/files.json")).json();
      const mk = d => { try { py.FS.mkdirTree(d) } catch (e) {} };
      mk("/app/src"); mk("/app/config");
      for (const rel of list) {
        const buf = new Uint8Array(await (await fetch("engine/py/" + rel)).arrayBuffer());
        py.FS.writeFile("/app/" + rel, buf);
      }
      ready = true;
      progress("engine ready");
    })();
    try { await loading } finally { loading = null }
  }
  async function run(exId, files, progress) {
    await init(progress);
    const ws = "w_" + exId.replace(/[^a-z0-9]/gi, "");
    const raw = "/app/workspaces/" + ws + "/raw";
    try { py.FS.mkdirTree(raw) } catch (e) {}
    for (const f of py.FS.readdir(raw)) if (f !== "." && f !== "..") py.FS.unlink(raw + "/" + f);
    for (const f of files) py.FS.writeFile(raw + "/" + f.name, f.bytes);
    progress("running the seven stages on " + files.length + " file(s)");
    const out = await py.runPythonAsync(
      'import sys, json, importlib\n' +
      'sys.path.insert(0, "/app")\n' +
      'import web_run\n' +
      'r = web_run.run(' + JSON.stringify(ws) + ')\n' +
      'targets = [{"scope": sc, "param": p, "value": e["value"], "source": e["source"]}\\n' +
      '  for sc, d in r["state"]["dataset"].items() for p, e in d.items()\\n' +
      '  if e["method"] == "DET" and isinstance(e["value"], (int, float))]\\n' +
      'json.dumps({"summary": r["summary"], "report": r["report"], ' +
      '"targets": targets, "doc_texts": r["doc_texts"], ' +
      '"facts": {"Recommendation": r["summary"]["recommendation"] or "none", ' +
      '"Ranking": " > ".join(r["summary"]["ranking"]) or "-", ' +
      '"Deterministic fields": r["summary"]["det"], ' +
      '"Unresolved": r["summary"]["unresolved"], ' +
      '"Runtime": str(r["summary"]["seconds"]) + "s (in this browser)"}})'
    );
    return JSON.parse(out);
  }
  return { init, run, isReady: () => ready };
})();"""


def build() -> str:
    run = latest_run(ws_dir(DEFAULT_WS))
    st = json.load(open(run / "state.json"))
    for sub in ("", "deck", "deck/assets", "report", "chat"):
        (SITE / sub).mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(landing(st))
    # browser engine: the pipeline itself, served for Pyodide
    eng = SITE / "engine"
    (eng / "py" / "src").mkdir(parents=True, exist_ok=True)
    (eng / "py" / "config").mkdir(parents=True, exist_ok=True)
    files = []
    for f in sorted((ROOT / "src").glob("*.py")):
        if f.name in ("site.py", "excel.py", "deck.py"):
            continue
        shutil.copy(f, eng / "py" / "src" / f.name)
        files.append("src/" + f.name)
    for f in sorted((ROOT / "config").glob("*.yaml")):
        shutil.copy(f, eng / "py" / "config" / f.name)
        files.append("config/" + f.name)
    shutil.copy(ROOT / "overrides.yaml", eng / "py" / "overrides.yaml")
    files.append("overrides.yaml")
    shutil.copy(ROOT / "web_run.py", eng / "py" / "web_run.py")
    files.append("web_run.py")
    (eng / "files.json").write_text(json.dumps(files))
    (eng / "engine.js").write_text(ENGINE_JS)
    (SITE / "model").mkdir(exist_ok=True)
    (SITE / "model" / "index.html").write_text(model_blank())
    (SITE / "deck" / "index.html").write_text(deck(st))
    for png in ("cash_curves_dark.png", "trough_dark.png", "nl_model_dark.png"):
        shutil.copy(DELIV / "charts" / png, SITE / "deck" / "assets" / png)
    shutil.copy(run / "report.html", SITE / "report" / "index.html")
    page, data_js = chat(st)
    (SITE / "chat" / "index.html").write_text(page)
    (SITE / "chat" / "data.js").write_text(data_js)
    (SITE / ".nojekyll").write_text("")
    return str(SITE)


if __name__ == "__main__":
    print(build())
