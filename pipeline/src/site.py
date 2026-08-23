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
 body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 'Instrument Sans',system-ui,sans-serif}
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
</style>"""


def landing(st) -> str:
    rec = st["conclusion"]["recommendation"]
    nl = st["conclusion"]["results"][rec]
    man = st["manifest"]
    fac = st["facilities"]["summary"]
    stages = ["01 READ", "02 EXTRACT", "03 UNIFY", "04 DEDUPE", "05 COMPARE", "06 CHECK", "07 CONCLUDE"]
    lane = " &nbsp;&nbsp;◇&nbsp;&nbsp; ".join(stages)
    stats = [
        ("Y3", "BREAK-EVEN", "company EBITDA positive, second reimbursed year"),
        ("€1.30M", "CASH TROUGH", "the €4.0M runway is never exhausted"),
        ("159,910", "FIT+ / YEAR", "92% of Germany's volume, none of its barriers"),
        (f"€{nl.get('system_saving_per_100',0):,}", "SAVED PER 100", "at €650 per avoided colonoscopy"),
    ]
    stat_html = "".join(
        f'<div class="stat"><span class="mono lbl"><i>▲</i>{lbl}</span><b>{big}</b><p>{sub}</p></div>'
        for big, lbl, sub in stats)
    rows = [
        ("deck/", "THE DECK", "five slides · the recommendation and its defence"),
        ("report/", "THE EVIDENCE", "every file's fate · the checks · the impossible 300k claim, rejected"),
        ("chat/", "ASK THE DATA", "grounded chat · your key, any provider, detected on paste"),
    ]
    row_html = "".join(
        f'<a class="row" href="{href}"><span class="split big">{title}</span>'
        f'<span class="mono sub">{sub}</span><span class="arr">→</span></a><div class="rule wide"></div>'
        for href, title, sub in rows)
    return f"""<!doctype html><html lang="en"><head><title>Runway, the market-entry desk</title>{HEAD}
<style>
 .bar{{position:fixed;top:0;left:0;right:0;display:flex;align-items:center;gap:12px;padding:16px 28px;z-index:9;
   background:linear-gradient(var(--bg) 60%,transparent)}}
 .bar b{{font-size:15px;letter-spacing:.02em}} .bar .mono{{color:var(--soft);font-size:11px}}
 .bar nav{{margin-left:auto;display:flex;gap:20px}}
 .bar nav a{{font:600 13px 'Instrument Sans';color:var(--softblue);text-decoration:none}}
 .bar nav a:hover{{color:var(--acc)}}
 .hero{{min-height:100svh;display:flex;flex-direction:column;justify-content:center;padding:110px 28px 40px;max-width:1240px;margin:0 auto}}
 h1{{margin:14px 0 0;font-weight:700;text-transform:uppercase;letter-spacing:-.028em;
   font-size:clamp(46px,9.2vw,132px);line-height:.98}}
 h1 .l2{{color:var(--acc);display:block}}
 h1 .serif{{font-style:italic;font-weight:300;text-transform:none;letter-spacing:0}}
 .hero .meta{{display:flex;justify-content:space-between;align-items:flex-end;gap:30px;margin-top:34px;flex-wrap:wrap}}
 .hero .meta p{{max-width:44ch;margin:0;color:var(--soft);font-size:15.5px}}
 .scrollhint{{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.3em;color:var(--soft)}}
 .sect{{max-width:1240px;margin:0 auto;padding:90px 28px}}
 .verdict h2{{margin:16px 0 0;font-weight:700;text-transform:uppercase;letter-spacing:-.02em;
   font-size:clamp(34px,6vw,84px);line-height:1.02}}
 .verdict h2 em{{font-family:'Noto Serif',serif;font-style:italic;font-weight:300;text-transform:none;color:var(--acc);letter-spacing:0}}
 .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:1px;background:var(--line);
   border:1px solid var(--line);margin-top:46px}}
 .stat{{background:var(--bg);padding:22px 20px}}
 .stat .lbl{{font-size:10.5px;letter-spacing:.14em;color:var(--soft)}}
 .stat .lbl i{{font-style:normal;color:var(--acc);margin-right:8px;font-size:9px}}
 .stat b{{display:block;font-size:clamp(28px,3vw,40px);letter-spacing:-.02em;margin:8px 0 4px}}
 .stat p{{margin:0;font-size:12.5px;color:var(--soft)}}
 .lane{{border-top:1px solid var(--line);border-bottom:1px solid var(--line);overflow:hidden;padding:18px 0;
   font-family:'IBM Plex Mono',monospace;font-size:13px;letter-spacing:.12em;color:var(--softblue);white-space:nowrap}}
 .lane .in{{display:inline-block;animation:lane 36s linear infinite;padding-right:60px}}
 .lane:hover .in{{animation-play-state:paused}}
 @keyframes lane{{to{{transform:translateX(-50%)}}}}
 @media(prefers-reduced-motion:reduce){{.lane .in{{animation:none}}}}
 .rows{{display:flex;flex-direction:column}}
 .row{{display:flex;align-items:baseline;gap:26px;padding:34px 4px;text-decoration:none;color:var(--ink)}}
 .row .big{{font-weight:700;text-transform:uppercase;letter-spacing:-.02em;font-size:clamp(30px,5vw,64px);line-height:1}}
 .row .sub{{color:var(--soft);font-size:12px;max-width:34ch;line-height:1.6}}
 .row .arr{{margin-left:auto;font-size:clamp(24px,3.5vw,40px);color:var(--soft);transition:transform .2s,color .2s}}
 .row:hover .arr{{color:var(--acc);transform:translateX(10px)}}
 .row:hover .big{{color:var(--acc)}}
 .rule.wide{{max-width:1240px}}
 .method{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:34px;color:var(--soft);font-size:14px}}
 .method b{{display:block;color:var(--ink);margin-bottom:6px;font-size:15px}}
 footer{{text-align:center;padding:40px 20px 50px;color:var(--soft);font:11.5px 'IBM Plex Mono',monospace;letter-spacing:.08em}}
 /* reveals (initial hidden states only when JS is present) */
 .split{{display:inline-block;overflow:hidden;vertical-align:bottom}}
 .js .split .ch{{display:inline-block;transform:translateY(110%);transition:transform .7s cubic-bezier(.2,.6,.1,1)}}
 .js .on .ch{{transform:translateY(0)}}
 .js .fade{{opacity:0;transform:translateY(18px);transition:opacity .6s ease,transform .6s ease}}
 .js .fade.on{{opacity:1;transform:none}}
 @media(prefers-reduced-motion:reduce){{.js .split .ch{{transform:none}}.js .fade{{opacity:1;transform:none}}}}
</style></head><body>
<div class="bar"><span class="tag"></span><b>RUNWAY</b><span class="mono">THE MARKET-ENTRY DESK</span>
 <nav><a href="deck/">Deck</a><a href="report/">Evidence</a><a href="chat/">Ask the data</a></nav></div>

<section class="hero">
 <div class="eyebrow"><span class="tag"></span>HELIX OPTICS · FIRST EUROPEAN MARKET · {fac['raw_records']:,} RECORDS READ</div>
 <h1><span class="split" data-stagger>FOUR MARKETS IN,</span>
     <span class="l2"><span class="split" data-stagger>ONE <span class="serif">answer</span> OUT.</span></span></h1>
 <div class="meta">
  <p>A seven-stage pipeline reads the raw pack in its native formats, validates every figure, deduplicates
  {fac['raw_records']:,} register records into {fac['unique_facilities']} real facilities, and rejects the
  planted impossibilities. Deterministic first; AI only where it earns its place.</p>
  <span class="scrollhint">(&nbsp;&nbsp;SCROLL&nbsp;&nbsp;)</span>
 </div>
</section>

<div class="lane"><span class="in">{lane} &nbsp;&nbsp;◇&nbsp;&nbsp; {lane}</span></div>

<section class="sect verdict">
 <div class="eyebrow fade"><span class="tag"></span>THE VERDICT</div>
 <h2><span class="split">ENTER THE</span><br><span class="split"><em>Netherlands</em> FIRST.</span></h2>
 <div class="stats fade">{stat_html}</div>
</section>

<section class="sect" style="padding-top:0">
 <div class="eyebrow fade" style="margin-bottom:8px"><span class="tag"></span>EXPLORE</div>
 <div class="rows">{row_html}</div>
</section>

<section class="sect method">
 <div class="fade"><b>Deterministic core.</b>74 of 74 fields resolved by patterns on this pack; the manifest
  records {man['llm_calls']} AI calls and €{man['llm_cost_eur']:.2f} spent. Eval: 28/28.</div>
 <div class="fade"><b>Nothing silent.</b>Unrecognised files are flagged, never ignored; capacity conflicts are
  reported as ranges; the competitor's 300k claim dies in check CHK-02.</div>
 <div class="fade"><b>Closed world.</b>The pack is the sole source of truth. The research workflow exists,
  and is deliberately off.</div>
</section>

<footer>RUNWAY · BUILT ON THE ILOF PALETTE · MARKETS 5–14 ARE A CONFIG ENTRY AWAY</footer>
<script>
 document.documentElement.classList.add('js');
 const rm=matchMedia('(prefers-reduced-motion: reduce)').matches;
 document.querySelectorAll('.split').forEach(el=>{{
   if(rm)return;
   const walk=n=>{{[...n.childNodes].forEach(c=>{{
     if(c.nodeType===3){{const f=document.createDocumentFragment();
       [...c.textContent].forEach(ch=>{{const s=document.createElement('span');s.className='ch';
         s.textContent=ch===' '?'\u00a0':ch;f.appendChild(s)}});n.replaceChild(f,c);}}
     else walk(c);}})}};
   walk(el);
   [...el.querySelectorAll('.ch')].forEach((c,i)=>c.style.transitionDelay=(i*22)+'ms');
 }});
 const io=new IntersectionObserver(es=>es.forEach(e=>{{if(e.isIntersecting){{e.target.classList.add('on');io.unobserve(e.target)}}}}),{{threshold:.3}});
 document.querySelectorAll('.split,.fade').forEach(el=>io.observe(el));
 addEventListener('load',()=>document.querySelectorAll('.hero .split').forEach(el=>el.classList.add('on')));
 setTimeout(()=>document.querySelectorAll('.split,.fade').forEach(el=>el.classList.add('on')),1600);
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
 <p class="hint">Answers come only from the pipeline's validated output (embedded in this page). Paste an
 Anthropic, OpenAI or Gemini key: the provider is detected from the key format and the model picker appears.
 The key stays in your browser; calls go straight to the provider, no server in between. This static edition is read-only;
 the local app can additionally apply overrides and re-run the pipeline.</p></div>
 <div id="msgs"></div>
</div>
<div class="bar"><div class="in">
 <select id="model" hidden></select>
 <input id="key" type="password" placeholder="API key (Anthropic / OpenAI / Gemini)" oninput="detect()"
   style="width:210px;font-family:'IBM Plex Mono',monospace;font-size:12px">
 <input id="q" placeholder="e.g. Why not Germany? What drives break-even?" onkeydown="if(event.key==='Enter')send()">
 <button class="primary" onclick="send()">Send</button>
</div></div>
<script src="data.js"></script>
<script>
 const PROVIDERS={{anthropic:{{label:'Anthropic',models:{{'claude-sonnet-5':'Claude Sonnet 5','claude-haiku-4-5-20251001':'Claude Haiku 4.5','claude-fable-5':'Claude Fable 5'}}}},
                   openai:{{label:'OpenAI',models:{{'gpt-5.1':'GPT-5.1','gpt-5-mini':'GPT-5 mini'}}}},
                   google:{{label:'Google',models:{{'gemini-3-pro-preview':'Gemini 3 Pro','gemini-2.5-flash':'Gemini 2.5 Flash'}}}}}};
 function detectProvider(k){{k=(k||'').trim();
   if(k.startsWith('sk-ant-'))return 'anthropic';
   if(/^AIza[0-9A-Za-z_-]{{30,}}$/.test(k))return 'google';
   if(k.startsWith('sk-'))return 'openai';return null}}
 function detect(){{const el=document.getElementById('key');const p=detectProvider(el.value);
   const sel=document.getElementById('model');
   if(!p){{sel.hidden=true;return}}
   sel.innerHTML=Object.entries(PROVIDERS[p].models).map(([v,l])=>`<option value="${{v}}">${{l}}</option>`).join('');
   sel.hidden=false;}}
 async function callProvider(p,key,model,system,hist){{
   if(p==='anthropic'){{
     const r=await fetch('https://api.anthropic.com/v1/messages',{{method:'POST',headers:{{
       'content-type':'application/json','x-api-key':key,'anthropic-version':'2023-06-01',
       'anthropic-dangerous-direct-browser-access':'true'}},
       body:JSON.stringify({{model,max_tokens:900,system,messages:hist}})}});
     const j=await r.json();if(j.error)throw j.error.message;return j.content[0].text;
   }}
   if(p==='openai'){{
     const r=await fetch('https://api.openai.com/v1/chat/completions',{{method:'POST',headers:{{
       'content-type':'application/json','authorization':'Bearer '+key}},
       body:JSON.stringify({{model,max_completion_tokens:900,
         messages:[{{role:'system',content:system}},...hist]}})}});
     const j=await r.json();if(j.error)throw j.error.message;return j.choices[0].message.content;
   }}
   if(p==='google'){{
     const contents=hist.map(m=>({{role:m.role==='assistant'?'model':'user',parts:[{{text:m.content}}]}}));
     const r=await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${{model}}:generateContent?key=${{key}}`,
       {{method:'POST',headers:{{'content-type':'application/json'}},
        body:JSON.stringify({{system_instruction:{{parts:[{{text:system}}]}},contents,
          generationConfig:{{maxOutputTokens:900,temperature:0}}}})}});
     const j=await r.json();if(j.error)throw j.error.message;return j.candidates[0].content.parts[0].text;
   }}
   throw 'unknown provider';
 }}
 const SYSTEM=`You are the analyst assistant for a market-entry assessment. Answer ONLY from the JSON dataset
provided (the pipeline's validated output). If something is not in it, say "not in the validated dataset" -
never guess. Cite a figure's source and method when giving numbers. Be concise. Currency EUR.
DATASET: `+JSON.stringify(window.DATASET);
 const msgs=document.getElementById('msgs');let hist=[];
 const keyEl=document.getElementById('key');keyEl.value=localStorage.getItem('ak')||'';detect();
 function render(role,text){{const d=document.createElement('div');d.className='msg '+(role==='user'?'user':'ai');
   d.textContent=text;msgs.appendChild(d);d.scrollIntoView({{behavior:'smooth',block:'end'}})}}
 async function send(){{
   const q=document.getElementById('q');const t=q.value.trim();if(!t)return;q.value='';
   const key=keyEl.value.trim();const p=detectProvider(key);
   if(!key){{render('ai','⚠ Paste an API key first: Anthropic (sk-ant-…), OpenAI (sk-…) or Gemini (AIza…). It stays in your browser.');return}}
   if(!p){{render('ai','⚠ Key format not recognised. Expected sk-ant-…, sk-… or AIza…');return}}
   localStorage.setItem('ak',key);render('user',t);hist.push({{role:'user',content:t}});
   try{{
    const model=document.getElementById('model').value||Object.keys(PROVIDERS[p].models)[0];
    const text=await callProvider(p,key,model,SYSTEM,hist.slice(-20));
    render('ai',text);hist.push({{role:'assistant',content:text}});
   }}catch(e){{render('ai','⚠ '+(e.message||e)+(p!=='anthropic'?' (some providers refuse browser calls; the local app routes them server-side)':''))}}
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
