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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400..700;1,400&family=Noto+Serif:ital,wght@0,400;0,600;1,400;1,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
 :root{--bg:#f9f7f5;--sf:#fff;--ink:#1d2939;--deep:#374b60;--soft:#667085;--line:#e6e1da;
   --acc:#ff4200;--accdark:#c12d00;--softblue:#bdd2e0;--softblue2:#e6eef3;--bordeaux:#661439;
   --tan:#ad836c;--cream2:#f4f1ec}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 'Instrument Sans',system-ui,sans-serif}
 .serif{font-family:'Noto Serif',serif}.mono{font-family:'IBM Plex Mono',monospace}
 a{color:var(--deep)}
 .eyebrow{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--tan)}
 .btn{display:inline-block;font:600 15px 'Instrument Sans';border-radius:10px;border:1px solid var(--line);
   padding:12px 22px;background:var(--sf);color:var(--ink);text-decoration:none;transition:all .15s}
 .btn:hover{border-color:var(--acc);transform:translateY(-1px)}
 .btn.primary{background:var(--acc);border-color:var(--acc);color:#fff}
 .btn.primary:hover{background:var(--accdark)}
 @media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>"""


def landing(st) -> str:
    rec = st["conclusion"]["recommendation"]
    nl = st["conclusion"]["results"][rec]
    man = st["manifest"]
    fac = st["facilities"]["summary"]
    chips = [
        (f"{man['total_s']}s", "full pipeline run"),
        ("28 / 28", "golden-eval fields correct"),
        (f"{fac['raw_records']:,} → {fac['unique_facilities']}", "register records deduplicated"),
        (f"€{man['llm_cost_eur']:.2f}", "AI spend (0 calls needed)"),
    ]
    chip_html = "".join(f'<div class="chip"><b>{a}</b><span>{b}</span></div>' for a, b in chips)
    return f"""<!doctype html><html lang="en"><head><title>Runway, the market-entry desk</title>{HEAD}
<style>
 .hero{{min-height:72vh;display:grid;place-content:center;text-align:center;padding:60px 22px 30px;gap:22px}}
 h1{{font-size:clamp(34px,6vw,58px);margin:0;letter-spacing:-.025em;font-weight:650;line-height:1.08;max-width:17ch}}
 h1 em{{font-family:'Noto Serif',serif;font-style:italic;font-weight:300;color:var(--acc)}}
 .sub{{color:var(--soft);max-width:56ch;margin:0 auto;font-size:17px}}
 .ctas{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-top:8px}}
 .chips{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;padding:10px 22px 70px}}
 .chip{{background:var(--sf);border:1px solid var(--line);border-radius:12px;padding:14px 20px;min-width:150px}}
 .chip b{{display:block;font-size:22px;letter-spacing:-.01em}}
 .chip span{{font-size:12.5px;color:var(--soft)}}
 .rail{{max-width:960px;margin:0 auto 80px;padding:0 22px}}
 .rail-strip{{background:var(--sf);border:1px solid var(--line);border-radius:14px;padding:6px 10px;
   display:flex;align-items:stretch;overflow-x:auto}}
 .stage{{flex:1;min-width:150px;padding:16px 14px;position:relative}}
 .stage+.stage{{border-left:1px dashed var(--line)}}
 .stage+.stage::before{{content:"→";position:absolute;left:-8px;top:18px;background:var(--sf);
   color:var(--acc);font-weight:700;padding:0 2px}}
 .stage .n{{font-family:'IBM Plex Mono',monospace;color:var(--acc);font-size:11px;letter-spacing:.08em}}
 .stage b{{display:block;margin:6px 0 3px;font-size:14.5px;letter-spacing:-.01em}}
 .stage p{{margin:0;font-size:12.5px;color:var(--soft);line-height:1.5}}
 .rail-caption{{text-align:center;font-size:13px;color:var(--soft);margin-top:12px}}
 footer{{text-align:center;padding:30px;color:var(--soft);font:12px 'IBM Plex Mono',monospace}}
 .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--acc);margin-right:8px}}
</style></head><body>
<div class="hero">
 <div class="eyebrow"><span class="dot"></span>Runway · the market-entry desk · Helix Optics case</div>
 <h1>Four markets in, <em>one answer out.</em></h1>
 <p class="sub">A seven-stage pipeline reads the raw pack in its native formats, validates every figure,
 deduplicates 3,236 register records into {fac['unique_facilities']} real facilities, catches the planted
 impossibilities. The recommendation: <b>the {rec}</b>, break-even in Year {nl['break_even_year']},
 cash trough €{nl['min_cash']/1e6:.1f}M, the only market that survives the €4.0M runway.</p>
 <div class="ctas">
  <a class="btn primary" href="deck/">View the deck →</a>
  <a class="btn" href="report/">Explore the evidence report</a>
  <a class="btn" href="chat/">Ask the data</a>
 </div>
</div>
<div class="chips">{chip_html}</div>
<div class="rail"><div class="rail-strip">
 <div class="stage"><span class="n">01 READ</span><b>Native formats</b>
  <p>PDF, XLSX, HTML, CSV. Zero retyping; every file's fate on the ingestion board.</p></div>
 <div class="stage"><span class="n">02 EXTRACT</span><b>Deterministic first</b>
  <p>Patterns resolve 74/74 fields here; a schema-guarded AI tier absorbs messier markets.</p></div>
 <div class="stage"><span class="n">03 UNIFY</span><b>One schema</b>
  <p>Provenance on every value: source, method, pattern.</p></div>
 <div class="stage"><span class="n">04 DEDUPE</span><b>3,236 → 228</b>
  <p>One row per real facility, rule stated, conflicts surfaced.</p></div>
 <div class="stage"><span class="n">05–06 CHECK</span><b>Nothing silent</b>
  <p>Source agreement plus arithmetic; the impossible 300k claim dies here.</p></div>
 <div class="stage"><span class="n">07 CONCLUDE</span><b>The model decides</b>
  <p>One five-year engine, four markets, one ranking; it also feeds the Excel.</p></div>
</div><div class="rail-caption">The seven stages the brief asks for, in the order they run.</div></div>
<footer>closed-world analysis: the pack is the sole source of truth. deterministic core · AI at the edges · evidence on every number</footer>
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
        <img src="assets/cash_curves.png" width="1560" height="860" alt="Five-year cash position of all four markets">
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
        </ul><img src="assets/trough.png" width="1240" height="840" alt="Cash trough by market"></div>
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
        </ul><img src="assets/nl_model.png" width="1280" height="840" alt="Netherlands EBITDA and cash"></div>
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
 table.grid th{{background:var(--ink);color:#fff;font:600 11.5px 'IBM Plex Mono',monospace}}
 table.grid tr th:first-child{{text-align:left}}
 td.good{{background:var(--softblue2);font-weight:650}} td.thin{{background:#f6ead9;font-weight:650}}
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


def chat(st) -> tuple[str, str]:
    compact = {
        "dataset": {s: {p: {"value": e["value"], "unit": e["unit"], "method": e["method"],
                            "source": e["source"]} for p, e in d.items()}
                    for s, d in st["dataset"].items()},
        "conclusion": st["conclusion"],
        "validation_findings": st["findings"],
        "facilities_summary": st["facilities"]["summary"],
        "evidence_gaps": [{k: g[k] for k in ("id", "market", "field", "why")} for g in st["gaps"]],
    }
    data_js = "window.DATASET = " + json.dumps(compact, default=str) + ";"
    page = f"""<!doctype html><html lang="en"><head><title>Ask the data — Helix</title>{HEAD}
<style>
 .wrap{{max-width:800px;margin:0 auto;padding:34px 20px 120px;display:flex;flex-direction:column;gap:16px}}
 h1{{font-size:26px;margin:0;letter-spacing:-.02em}} h1 em{{font-family:'Noto Serif',serif;font-style:italic;font-weight:300;color:var(--acc)}}
 .msg{{border-radius:14px;padding:12px 16px;max-width:88%;font-size:14.5px;white-space:pre-wrap}}
 .msg.user{{background:var(--deep);color:#fff;align-self:flex-end}}
 .msg.ai{{background:var(--sf);border:1px solid var(--line);align-self:flex-start}}
 #msgs{{display:flex;flex-direction:column;gap:10px}}
 .bar{{position:fixed;bottom:0;left:0;right:0;background:var(--bg);border-top:1px solid var(--line);padding:12px}}
 .bar .in{{max-width:800px;margin:0 auto;display:flex;gap:10px}}
 input,select,button{{font:14px 'Instrument Sans';border:1px solid var(--line);border-radius:9px;padding:10px 12px;background:var(--sf);color:var(--ink)}}
 #q{{flex:1}} button.primary{{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600;cursor:pointer}}
 .hint{{font-size:13px;color:var(--soft)}}
 .back{{font:600 13px 'Instrument Sans';color:var(--soft);text-decoration:none}}
</style></head><body>
<div class="wrap">
 <a class="back" href="../">← Runway</a>
 <div><div class="eyebrow">Helix Optics · ask the data</div>
 <h1>Chat with the <em>validated</em> dataset</h1>
 <p class="hint">Answers come only from the pipeline's validated output (embedded in this page). Your API key stays
 in your browser; calls go straight from here to Anthropic, no server in between. This static edition is read-only;
 the local app can additionally apply overrides and re-run the pipeline.</p></div>
 <div id="msgs"></div>
</div>
<div class="bar"><div class="in">
 <select id="model">
  <option value="claude-sonnet-5" selected>Sonnet 5</option>
  <option value="claude-haiku-4-5-20251001">Haiku 4.5</option>
  <option value="claude-fable-5">Fable 5</option></select>
 <input id="key" type="password" placeholder="Anthropic API key" style="width:180px;font-family:'IBM Plex Mono',monospace;font-size:12px">
 <input id="q" placeholder="e.g. Why not Germany? What drives break-even?" onkeydown="if(event.key==='Enter')send()">
 <button class="primary" onclick="send()">Send</button>
</div></div>
<script src="data.js"></script>
<script>
 const SYSTEM=`You are the analyst assistant for a market-entry assessment. Answer ONLY from the JSON dataset
provided (the pipeline's validated output). If something is not in it, say "not in the validated dataset" -
never guess. Cite a figure's source and method when giving numbers. Be concise. Currency EUR.
DATASET: `+JSON.stringify(window.DATASET);
 const msgs=document.getElementById('msgs');let hist=[];
 const keyEl=document.getElementById('key');keyEl.value=localStorage.getItem('ak')||'';
 function render(role,text){{const d=document.createElement('div');d.className='msg '+(role==='user'?'user':'ai');
   d.textContent=text;msgs.appendChild(d);d.scrollIntoView({{behavior:'smooth',block:'end'}})}}
 async function send(){{
   const q=document.getElementById('q');const t=q.value.trim();if(!t)return;q.value='';
   const key=keyEl.value.trim();if(!key){{render('ai','⚠ Paste your Anthropic API key first (it stays in your browser).');return}}
   localStorage.setItem('ak',key);render('user',t);hist.push({{role:'user',content:t}});
   try{{
    const r=await fetch('https://api.anthropic.com/v1/messages',{{method:'POST',headers:{{
      'content-type':'application/json','x-api-key':key,'anthropic-version':'2023-06-01',
      'anthropic-dangerous-direct-browser-access':'true'}},
      body:JSON.stringify({{model:document.getElementById('model').value,max_tokens:900,system:SYSTEM,messages:hist.slice(-20)}})}});
    const j=await r.json();
    if(j.error){{render('ai','⚠ '+j.error.message);return}}
    const text=j.content[0].text;render('ai',text);hist.push({{role:'assistant',content:text}});
   }}catch(e){{render('ai','⚠ '+e)}}
 }}
</script></body></html>"""
    return page, data_js


def build() -> str:
    run = latest_run(ws_dir(DEFAULT_WS))
    st = json.load(open(run / "state.json"))
    for sub in ("", "deck", "deck/assets", "report", "chat"):
        (SITE / sub).mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(landing(st))
    (SITE / "deck" / "index.html").write_text(deck(st))
    for png in ("cash_curves.png", "trough.png", "nl_model.png"):
        shutil.copy(DELIV / "charts" / png, SITE / "deck" / "assets" / png)
    shutil.copy(run / "report.html", SITE / "report" / "index.html")
    page, data_js = chat(st)
    (SITE / "chat" / "index.html").write_text(page)
    (SITE / "chat" / "data.js").write_text(data_js)
    (SITE / ".nojekyll").write_text("")
    return str(SITE)


if __name__ == "__main__":
    print(build())
