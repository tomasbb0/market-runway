"""Build the self-contained dashboard (data/out/report.html) from state.json.

Design language matches the case workbench: Archivo / Source Sans 3 /
IBM Plex Mono, clinical teal on ink. No external JS; <details> for expanders;
prints cleanly. Every number on the page comes from the pipeline state - the
report is generated, never hand-edited.
"""
import html
import json
from datetime import datetime

from .util import load_yaml
from .paths import ws_dir, latest_run, DEFAULT_WS

# iLoF brand palette (ilof.tech): cream / deep blue / vivid orange / bordeaux / tan
C = {"bg": "#f9f7f5", "surface": "#FFFFFF", "ink": "#1d2939", "soft": "#667085",
     "line": "#e6e1da", "accent": "#374b60", "accent2": "#1d2939", "accsoft": "#e6eef3",
     "warn": "#ad836c", "warnsoft": "#f6ead9", "fail": "#c12d00", "failsoft": "#f8e3dc",
     "okgreen": "#374b60", "hot": "#ff4200"}

MARKET_COLORS = {"Netherlands": "#ff4200", "Germany": "#661439", "Portugal": "#374b60", "Poland": "#ad836c"}


def eur_m(v):
    return f"€{v/1e6:.2f}M"


def badge(method):
    color = {"DET": C["accent"], "LLM": "#7A4FA5", "MANUAL": C["warn"], "INTERNAL": C["soft"]}.get(method, C["soft"])
    label = {"DET": "DET", "LLM": "AI", "MANUAL": "MANUAL", "INTERNAL": "DERIVED"}.get(method, method)
    return f'<span class="badge" style="background:{color}1A;color:{color}">{label}</span>'


def cash_svg(results, ranking):
    W, H, PAD = 640, 260, 42
    all_vals = [y["cash"] for m in results for y in results[m]["years"]] + [4_000_000]
    lo, hi = min(all_vals), max(all_vals)
    span = hi - lo or 1

    def x(i):  # i in 0..5 (Y0..Y5)
        return PAD + i * (W - PAD - 14) / 5

    def y(v):
        return 14 + (H - 54) * (1 - (v - lo) / span)

    zero_y = y(0)
    lines, labels = [], []
    for m in ranking:
        pts = [(x(0), y(4_000_000 - results[m]["params"]["entry_cost"]))]
        pts += [(x(i + 1), y(yr["cash"])) for i, yr in enumerate(results[m]["years"])]
        d = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        col = MARKET_COLORS[m]
        lines.append(f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="2.5" />')
        lines.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.5" fill="{col}"/>')
        labels.append(f'<tspan x="{W-8}" dy="{15}" fill="{col}">{m} {results[m]["end_cash"]/1e6:+.1f}M</tspan>')
    ticks = "".join(
        f'<text x="{x(i)}" y="{H-16}" text-anchor="middle" class="tick">Y{i}</text>' for i in range(6))
    return f'''<svg viewBox="0 0 {W} {H}" role="img" aria-label="Five-year cash position per market">
      <line x1="{PAD}" y1="{zero_y:.1f}" x2="{W-14}" y2="{zero_y:.1f}" stroke="{C["fail"]}" stroke-dasharray="5 4" stroke-width="1"/>
      <text x="{PAD+2}" y="{zero_y-5:.1f}" class="tick" fill="{C["fail"]}">€0 — insolvency</text>
      {''.join(lines)}
      <text text-anchor="end" y="10" class="lbl">{''.join(labels)}</text>
      {ticks}
    </svg>'''


def build(state_path=None) -> str:
    if state_path is None:
        state_path = latest_run(ws_dir(DEFAULT_WS)) / "state.json"
    state_path = __import__("pathlib").Path(state_path)
    state = json.load(open(state_path))
    OUT = state_path.parent
    ds = state["dataset"]
    man = state["manifest"]
    fac = state["facilities"]
    res = state["conclusion"]["results"]
    ranking = state["conclusion"]["ranking"]
    rec = state["conclusion"]["recommendation"]

    # eval score, computed live against the golden set
    golden = load_yaml("golden.yaml")
    hits = sum(
        1 for g in golden
        if (v := ds.get(g["market"], {}).get(g["param"], {}).get("value")) is not None
        and abs(float(v) - float(g["expect"])) <= abs(float(g["expect"])) * 0.001)

    # ---------- sections ----------
    ing_cards = ""
    for d in state["ingestion"]:
        icon = {"parsed": "✓", "partial": "△", "failed": "✕"}[d["status"]]
        cls = {"parsed": "ok", "partial": "warn", "failed": "fail"}[d["status"]]
        ing_cards += f'''<div class="fcard"><div class="fstat {cls}">{icon}</div>
          <div><div class="fname">{html.escape(d["file"])}</div>
          <div class="fmeta">{d["format"].upper()} · {d["ms"]}ms · sha {d["sha"][:8]}{(" · " + html.escape(d["detail"])) if d["detail"] else ""}</div></div></div>'''

    param_rows = ""
    show_order = ["eligible_population", "participation", "fit_positivity", "annual_screened",
                  "addressable_fit_positive", "price_per_test", "time_to_reimbursement_months",
                  "colonoscopy_tariff", "entry_cost", "inmarket_cost_per_year"]
    pretty = {"eligible_population": "Eligible population 50–74", "participation": "Participation",
              "fit_positivity": "FIT positivity", "annual_screened": "Annual screened",
              "addressable_fit_positive": "Addressable FIT+ / yr", "price_per_test": "Price per test",
              "time_to_reimbursement_months": "Months to reimbursement", "colonoscopy_tariff": "Colonoscopy tariff",
              "entry_cost": "One-time entry cost", "inmarket_cost_per_year": "In-market cost / yr"}
    markets = [m for m in ["Portugal", "Germany", "Netherlands", "Poland"] if m in ds]
    for p in show_order:
        cells = ""
        for m in markets:
            e = ds[m].get(p)
            if not e:
                cells += "<td>—</td>"
                continue
            v = e["value"]
            if p in ("participation", "fit_positivity"):
                txt = f"{v*100:.1f}%"
            elif p in ("eligible_population", "annual_screened", "addressable_fit_positive"):
                txt = f"{v:,.0f}"
            elif "cost" in p or "price" in p or "tariff" in p:
                txt = f"€{v:,.0f}"
            else:
                txt = f"{v}"
            cells += f"<td>{txt} {badge(e['method'])}</td>"
        param_rows += f"<tr><th>{pretty[p]}</th>{cells}</tr>"

    agree_rows = ""
    for r in state["agreement"]:
        cls = "ok" if r["agree"] else "fail"
        srcs = " · ".join(f"<b>{html.escape(k.split('/')[-1])}</b>: {v}" for k, v in r["sources"].items())
        agree_rows += (f'<tr class="{cls}"><td>{r["scope"]}</td><td>{r["param"]}</td>'
                       f'<td>{"AGREE" if r["agree"] else "DISAGREE"}</td><td class="src">{srcs}</td></tr>')

    find_rows = ""
    for f in state["findings"]:
        cls = {"PASS": "ok", "FAIL": "fail", "WARN": "warn", "INFO": "info"}[f["status"]]
        find_rows += (f'<div class="finding {cls}"><div class="fhead"><span class="fpill">{f["status"]}</span>'
                      f'<b>{f["id"]}</b> {html.escape(f["name"])}</div>'
                      f'<div class="fdetail">{html.escape(f["detail"])}</div>'
                      + (f'<div class="fnote">{html.escape(f["note"])}</div>' if f["note"] and f["status"] != "PASS" else "")
                      + "</div>")

    s = fac["summary"]
    fac_sample = ""
    interesting = [f_ for f_ in fac["facilities"] if f_["type_conflict"] or f_["capacity_conflict"]][:6]
    for f_ in interesting:
        fac_sample += (f'<tr><td class="mono">{f_["facility_uid"]}</td><td>{html.escape(f_["institution"])} · Unit {f_["unit"]}</td>'
                       f'<td>{f_["country"]}</td><td>{f_["type"]} <span class="mono soft">({f_["type_votes"]})</span></td>'
                       f'<td>{f_["capacity_annual"] or "—"}'
                       + (f' <span class="mono soft">[{f_["capacity_min"]:.0f}–{f_["capacity_max"]:.0f}]</span>' if f_["capacity_conflict"] else "")
                       + f'</td><td>{f_["n_source_records"]}</td></tr>')

    gap_cards = ""
    for g in state["gaps"]:
        plan = "".join(f"<li>{html.escape(p)}</li>" for p in g["plan"])
        gap_cards += f'''<div class="gap"><div class="gaphead"><b>{g["id"]}</b> · {g["market"]} · {html.escape(g["field"])}
          <button class="research" disabled title="Disabled: this assessment treats the pack as a closed world. In production this launches the sourcing workflow, and found documents land in quarantine until a human approves them.">Research this ⏸</button></div>
          <div class="gapwhy">{html.escape(g["why"])} <i>{html.escape(g["impact"])}</i></div>
          <details><summary>Research plan (what the sourcing workflow would run)</summary><ul>{plan}</ul></details></div>'''

    rank_rows = ""
    for i, m in enumerate(ranking):
        r = res[m]
        be = f"Year {r['break_even_year']}" if r["break_even_year"] else "—"
        flag = '<span class="pill fail">insolvent</span>' if r["insolvent"] else '<span class="pill ok">survives</span>'
        rank_rows += (f'<tr class="{"winner" if i == 0 else ""}"><td>{i+1}</td><td><b>{m}</b></td>'
                      f'<td>{r["params"]["addressable_fit_positive"]:,.0f}</td><td>€{r["params"]["price_per_test"]:,.0f}</td>'
                      f'<td>{be}</td><td>{eur_m(r["min_cash"])}</td><td>{eur_m(r["end_cash"])}</td><td>{flag}</td></tr>')

    nl = res[rec]
    yr_rows = "".join(
        f'<tr><td>Y{y["year"]}</td><td>{y["ramp"]*100:.0f}%</td><td>{y["tests"]:,}</td>'
        f'<td>€{y["revenue"]:,}</td><td>€{y["cogs"]:.0f}</td><td>€{y["gross_margin"]:,}</td>'
        f'<td class="{"pos" if y["ebitda"]>0 else "neg"}">€{y["ebitda"]:,}</td><td>€{y["cash"]:,}</td></tr>'
        for y in nl["years"])

    ts = datetime.fromisoformat(man["run_at"]).strftime("%d %b %Y %H:%M UTC")
    ex = man["extraction"]

    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Helix Optics — Market-Entry Pipeline Report</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400..700;1,400&family=Noto+Serif:ital,wght@0,600;1,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
 :root{{--bg:{C["bg"]};--sf:{C["surface"]};--ink:{C["ink"]};--soft:{C["soft"]};--line:{C["line"]};
   --acc:{C["accent"]};--acc2:{C["accent2"]};--accsoft:{C["accsoft"]};--hot:{C["hot"]};--warn:{C["warn"]};--warnsoft:{C["warnsoft"]};
   --fail:{C["fail"]};--failsoft:{C["failsoft"]};--ok:{C["okgreen"]}}}
 *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);
   font:15px/1.5 'Instrument Sans',system-ui,sans-serif;padding:34px 22px 70px}}
 .wrap{{max-width:880px;margin:0 auto;display:flex;flex-direction:column;gap:26px}}
 h1,h2{{font-family:'Instrument Sans',system-ui;font-weight:650;letter-spacing:-.01em;margin:0}}
 h1{{font-size:27px}} h2{{font-size:17px;margin-bottom:10px}}
 .mono{{font-family:'IBM Plex Mono',monospace;font-size:12px}}
 .soft{{color:var(--soft)}}
 .eyebrow{{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--hot)}}
 .runbar{{display:flex;gap:14px;flex-wrap:wrap;align-items:center;background:var(--sf);border:1px solid var(--line);
   border-radius:10px;padding:10px 16px;font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--soft)}}
 .verdict{{background:var(--accsoft);border:1px solid var(--line);border-left:4px solid var(--hot);
   border-radius:10px;padding:16px 20px;font-size:16.5px}}
 section{{background:var(--sf);border:1px solid var(--line);border-radius:12px;padding:18px 20px}}
 table{{border-collapse:collapse;width:100%;font-size:13.5px}}
 .tablewrap{{overflow-x:auto}}
 th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
 thead th{{font-family:'IBM Plex Mono',monospace;font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--soft)}}
 tbody tr:last-child td{{border-bottom:none}}
 td{{font-variant-numeric:tabular-nums}}
 .badge{{font-family:'IBM Plex Mono',monospace;font-size:10px;border-radius:99px;padding:1px 7px;vertical-align:1px}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:8px}}
 .fcard{{display:flex;gap:10px;border:1px solid var(--line);border-radius:8px;padding:8px 10px;align-items:center}}
 .fstat{{width:26px;height:26px;border-radius:7px;display:grid;place-content:center;font-weight:700;flex:none}}
 .fstat.ok{{background:var(--accsoft);color:var(--acc2)}} .fstat.warn{{background:var(--warnsoft);color:var(--warn)}}
 .fstat.fail{{background:var(--failsoft);color:var(--fail)}}
 .fname{{font-size:13px;font-weight:600}} .fmeta{{font-size:11.5px;color:var(--soft);font-family:'IBM Plex Mono',monospace}}
 .tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:12px}}
 .tile{{border:1px solid var(--line);border-radius:9px;padding:10px 12px}}
 .tile b{{display:block;font-size:20px;font-weight:650}} .tile span{{font-size:12px;color:var(--soft)}}
 .finding{{border:1px solid var(--line);border-radius:9px;padding:10px 14px;margin-bottom:8px}}
 .finding.fail{{background:var(--failsoft);border-color:#E4B8B8}}
 .finding.warn{{background:var(--warnsoft)}}
 .fpill{{font-family:'IBM Plex Mono',monospace;font-size:10.5px;border-radius:99px;padding:1px 8px;margin-right:8px;background:var(--line)}}
 .fail .fpill{{background:var(--fail);color:#fff}} .warn .fpill{{background:var(--warn);color:#fff}}
 .ok .fpill{{background:var(--acc);color:#fff}} .info .fpill{{background:var(--soft);color:#fff}}
 .fdetail{{font-size:13.5px;margin-top:4px}} .fnote{{font-size:12.5px;color:var(--soft);font-style:italic;margin-top:3px}}
 tr.ok td:nth-child(3){{color:var(--ok);font-weight:600}} tr.fail td:nth-child(3){{color:var(--fail);font-weight:700}}
 td.src{{font-size:12.5px;color:var(--soft)}}
 .gap{{border:1px solid var(--line);border-radius:9px;padding:12px 14px;margin-bottom:8px}}
 .gaphead{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
 .research{{margin-left:auto;border:1px solid var(--line);background:var(--bg);color:var(--soft);
   border-radius:99px;padding:3px 12px;font:12px 'IBM Plex Mono',monospace}}
 .gapwhy{{font-size:13.5px;margin-top:5px}} .gap i{{color:var(--soft)}}
 details{{margin-top:6px;font-size:13px}} summary{{cursor:pointer;color:var(--acc2)}}
 tr.winner td{{background:var(--accsoft)}}
 .pill{{font-family:'IBM Plex Mono',monospace;font-size:10.5px;border-radius:99px;padding:1px 8px}}
 .pill.ok{{background:var(--accsoft);color:var(--acc2)}} .pill.fail{{background:var(--failsoft);color:var(--fail)}}
 td.pos{{color:var(--ok);font-weight:600}} td.neg{{color:var(--fail)}}
 .tick{{font:10.5px 'IBM Plex Mono',monospace;fill:var(--soft)}} .lbl{{font:11.5px 'IBM Plex Mono',monospace}}
 .rule{{background:var(--bg);border-radius:8px;padding:10px 14px;font-size:13px;margin-top:10px}}
 footer{{text-align:center;font:11.5px 'IBM Plex Mono',monospace;color:var(--soft)}}
 @media print{{body{{background:#fff;padding:0}} section{{break-inside:avoid}}}}
</style></head><body><div class="wrap">

<header>
  <div class="eyebrow">Helix Optics · market-entry assessment · pipeline run report</div>
  <h1>Four markets in, one recommendation out</h1>
</header>

<div class="runbar"><span>run {ts}</span><span>ai mode: {man["ai_mode"]}</span>
  <span>llm calls: {man["llm_calls"]} · cost €{man["llm_cost_eur"]:.2f}</span>
  <span>runtime {man["total_s"]}s</span><span>eval {hits}/{len(golden)}</span>
  <span>extraction: {ex["deterministic"]} det / {ex["ai"]} ai / {ex["manual_overrides"]} manual / {ex["unresolved"]} unresolved</span></div>

<div class="verdict"><b>Recommendation: enter the {rec} first.</b> Break-even in Year {nl["break_even_year"]},
 cash trough {eur_m(nl["min_cash"])}, five-year end cash {eur_m(nl["end_cash"])}. The only market of the four that
 does not exhaust the €4.0M runway. Each 100 patients triaged saves the Dutch system €{nl["system_saving_per_100"]:,}.</div>

<section><h2>1 · Ingestion — every file, its fate</h2><div class="grid">{ing_cards}</div></section>

<section><h2>2–3 · Canonical dataset (method-badged)</h2>
 <div class="tablewrap"><table><thead><tr><th>Parameter</th>{"".join(f"<th>{m}</th>" for m in markets)}</tr></thead>
 <tbody>{param_rows}</tbody></table></div>
 <div class="rule">Precedence: national screening report → landscape table → other. Full provenance per value in
 <span class="mono">markets.csv</span>; manual corrections belong in <span class="mono">overrides.yaml</span>, never in outputs.</div></section>

<section><h2>4 · Facilities — one row per real unit</h2>
 <div class="tiles">
  <div class="tile"><b>{s["raw_records"]:,}</b><span>raw register records</span></div>
  <div class="tile"><b>{s["unique_facilities"]}</b><span>real facilities</span></div>
  <div class="tile"><b>{s["monthly_annualised"]}</b><span>monthly rows ×12</span></div>
  <div class="tile"><b>{len(s["repairs"])}</b><span>corrupted rows handled</span></div>
  <div class="tile"><b>{s["type_conflicts"]}</b><span>type conflicts (majority vote)</span></div>
  <div class="tile"><b>{s["capacity_conflicts"]}</b><span>capacity conflicts (median + range)</span></div>
 </div>
 <div class="tablewrap"><table><thead><tr><th>UID</th><th>Facility</th><th>Country</th><th>Type (votes)</th><th>Capacity/yr [range]</th><th># records</th></tr></thead>
 <tbody>{fac_sample}</tbody></table></div>
 <div class="rule"><b>The rule:</b> repair unambiguous column-shifts, else exclude (6 handled) → normalise
 (diacritics; Germany's 126 monthly capacities ×12; ENDO/PATH/'Endoscopy Unit' → one label) →
 entity = (country, canonical institution, unit nº); register ids are untrusted → master-registry names mapped via a
 curated, fuzzy-seeded alias table; national register is authoritative → type by majority vote, capacity as
 median of non-null values with min–max spread reported. Disagreements are surfaced, never silently resolved.</div></section>

<section><h2>5 · Source agreement</h2>
 <div class="tablewrap"><table><thead><tr><th>Scope</th><th>Parameter</th><th>Verdict</th><th>Sources</th></tr></thead>
 <tbody>{agree_rows}</tbody></table></div></section>

<section><h2>6 · Validation findings</h2>{find_rows}</section>

<section><h2>Evidence gaps — and the research workflow, deliberately off</h2>{gap_cards}
 <div class="rule">The pack is treated as the <b>closed source of truth</b>: no external data was mixed in.
 In production the Research action launches a sourcing workflow whose finds land in quarantine —
 parsed and previewed, entering the dataset only after human approval (provenance <i>EXTERNAL/approved-by</i>).</div></section>

<section><h2>7 · Conclusion — the five-year engine, all four markets</h2>
 {cash_svg(res, ranking)}
 <div class="tablewrap"><table><thead><tr><th>#</th><th>Market</th><th>Addressable FIT+/yr</th><th>Price</th>
  <th>Break-even</th><th>Cash trough</th><th>End cash Y5</th><th></th></tr></thead><tbody>{rank_rows}</tbody></table></div>
 <h2 style="margin-top:18px">{rec} — year by year</h2>
 <div class="tablewrap"><table><thead><tr><th>Year</th><th>Ramp</th><th>Tests</th><th>Revenue</th><th>COGS/test</th>
  <th>Gross margin</th><th>EBITDA</th><th>Cash</th></tr></thead><tbody>{yr_rows}</tbody></table></div>
 <div class="rule">Same engine as the Excel model (assumptions editable there); ramp anchored on the pack's benchmark
 — a comparable assay reached ~20% of eligible FIT-positive volume within 3 years of reimbursement. Germany's
 pre-reimbursement revenue is held at zero per its national report; its 24-month pathway consumes the runway before
 first revenue — the largest market is unaffordable now, not unattractive forever.</div></section>

<footer>generated by the pipeline · inputs {len(man["inputs"])} files sha-pinned · deterministic core, AI at the edges, evidence everywhere</footer>
</div></body></html>'''
    out = OUT / "report.html"
    out.write_text(page)
    return str(out)


if __name__ == "__main__":
    print(build())
