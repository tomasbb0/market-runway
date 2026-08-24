#!/usr/bin/env python3
"""Helix Optics market-entry pipeline.

Usage:
  python run.py                 # full run, AI mode auto (per-field fallback)
  python run.py --ai off        # deterministic only; unresolved fields reported
  python run.py --ai max        # auto + LLM audit pass over Tier-A extractions
  python run.py --eval          # score the extractor against config/golden.yaml
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

from src import llm  # noqa: E402
from src.util import ROOT, load_yaml  # noqa: E402
from src.paths import set_workspace, DEFAULT_WS  # noqa: E402
from src.mapper import build_manifest  # noqa: E402
from src.stage1_read import read_pack  # noqa: E402
from src.stage2_extract import extract_all  # noqa: E402
from src.stage3_schema import build_dataset, apply_overrides, derive  # noqa: E402
from src.stage4_facilities import dedupe  # noqa: E402
from src.stage5_reconcile import agreement_matrix  # noqa: E402
from src.stage6_validate import run_checks  # noqa: E402
from src.stage7_conclude import conclude, gap_report  # noqa: E402


def stage(n, label):
    print(f"\033[36m[stage {n}]\033[0m {label}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", choices=["off", "auto", "max"], default="auto")
    ap.add_argument("--eval", action="store_true", help="score extractor vs golden set")
    ap.add_argument("--workspace", default=DEFAULT_WS, help="workspace folder name under workspaces/")
    args = ap.parse_args()
    t0 = time.time()
    timings = {}
    ws = set_workspace(args.workspace, new_run=not args.eval)
    cfg = build_manifest(ws)
    if not cfg["markets"] and not cfg["company_docs"]:
        print(f"workspace '{ws.name}' has no mappable documents; unassigned: {cfg['unassigned']}")
        return 2
    schema = load_yaml("schema.yaml")
    print(f"\033[1mworkspace: {ws.name}\033[0m  markets: {', '.join(cfg['markets']) or '—'}"
          + (f"  \033[33munassigned files: {len(cfg['unassigned'])}\033[0m" if cfg["unassigned"] else ""))

    stage(1, "reading pack in native formats")
    t = time.time()
    docs = read_pack(cfg)
    timings["1_read"] = round(time.time() - t, 2)
    ok = sum(d.status == "parsed" for d in docs.values())
    print(f"  {len(docs)} files: {ok} parsed, {len(docs)-ok} with issues")

    stage(2, f"extracting parameters (tier A patterns, tier B ai={args.ai})")
    t = time.time()
    extractions, unresolved, audit = extract_all(docs, schema, args.ai)
    timings["2_extract"] = round(time.time() - t, 2)
    det = sum(e.method == "DET" for e in extractions)
    ai = sum(e.method == "LLM" for e in extractions)
    print(f"  {len(extractions)} values extracted: {det} deterministic, {ai} AI-assisted, {len(unresolved)} unresolved")
    if args.ai == "max":
        dis = [a for a in audit if a["verdict"] == "DISAGREE"]
        skipped = sum(a["verdict"].startswith("SKIPPED") for a in audit)
        msg = f"  audit pass: {len(audit)} values re-checked by the model — {len(dis)} disagreement(s)"
        if skipped:
            msg += f", {skipped} skipped (set ANTHROPIC_API_KEY to enable live audit)"
        print(msg)
        for a in dis:
            print(f"    DISAGREE {a['scope']}.{a['param']}: det={a['det']} vs llm={a['llm']}")

    if args.eval:
        golden = load_yaml("golden.yaml")
        by = {(e.scope, e.param): e.value for e in extractions}
        # golden is scored against the primary (highest-precedence) source value
        ds_tmp, _ = build_dataset(extractions)
        by = {(s, p): e.value for s, d in ds_tmp.items() for p, e in d.items()}
        hits, misses = 0, []
        for g in golden:
            got = by.get((g["market"], g["param"]))
            ok_ = got is not None and abs(float(got) - float(g["expect"])) <= abs(float(g["expect"])) * 0.001
            hits += ok_
            if not ok_:
                misses.append((g["market"], g["param"], g["expect"], got))
        print(f"\n\033[1mEVAL: {hits}/{len(golden)} golden fields correct\033[0m")
        for m in misses:
            print("  MISS", m)
        return 0 if not misses else 1

    stage(3, "resolving into canonical schema + overrides")
    t = time.time()
    dataset, all_ex = build_dataset(extractions)
    overrides = apply_overrides(dataset)
    derive(dataset)
    timings["3_schema"] = round(time.time() - t, 2)
    print(f"  {sum(len(v) for v in dataset.values())} canonical fields; {len(overrides)} manual override(s) active")

    stage(4, "deduplicating facility registers")
    t = time.time()
    fac = dedupe(docs, cfg)
    timings["4_facilities"] = round(time.time() - t, 2)
    s = fac["summary"]
    print(f"  {s['raw_records']} raw records -> {s['unique_facilities']} real facilities "
          f"({s['monthly_annualised']} monthly rows annualised, {len(s['repairs'])} corrupted rows handled, "
          f"{s['master_only']} master-only units added)")

    stage(5, "reconciling multi-source parameters")
    t = time.time()
    agreement = agreement_matrix(all_ex)
    timings["5_reconcile"] = round(time.time() - t, 2)
    dis = [r for r in agreement if not r["agree"]]
    print(f"  {len(agreement)} parameters in >1 source; {len(dis)} disagreement(s)")

    stage(6, "validating figures against each other and basic arithmetic")
    t = time.time()
    findings = run_checks(dataset, agreement, fac)
    timings["6_validate"] = round(time.time() - t, 2)
    for f in findings:
        mark = {"PASS": "\033[32mPASS\033[0m", "FAIL": "\033[31mFAIL\033[0m",
                "WARN": "\033[33mWARN\033[0m", "INFO": "\033[36mINFO\033[0m"}[f["status"]]
        print(f"  {mark} {f['id']} {f['name']}")
        if f["status"] != "PASS":
            print(f"       -> {f['detail']}")

    stage(7, "financial engine + conclusion")
    t = time.time()
    conclusion = conclude(dataset)
    gaps = gap_report(dataset, unresolved)
    timings["7_conclude"] = round(time.time() - t, 2)
    print("  ranking:")
    for i, m in enumerate(conclusion["ranking"]):
        r = conclusion["results"][m]
        be = f"break-even Y{r['break_even_year']}" if r["break_even_year"] else "no break-even in 5y"
        flag = " \033[31m[INSOLVENT]\033[0m" if r["insolvent"] else ""
        print(f"   {i+1}. {m:<12} {be:<22} min cash {r['min_cash']/1e6:6.2f}M  end cash {r['end_cash']/1e6:6.2f}M{flag}")
    for m, missing in conclusion.get("skipped", {}).items():
        print(f"   \033[33m—  {m}: not modelled — missing {', '.join(missing)}\033[0m")
    if conclusion["recommendation"]:
        print(f"  \033[1mRECOMMENDATION: enter {conclusion['recommendation']} first\033[0m")
    else:
        print("  \033[33mno market could be modelled — resolve the missing parameters above\033[0m")

    # ---- outputs ----
    from src.paths import out_dir
    OUT = out_dir()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "markets.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "param", "value", "unit", "source", "method", "pattern", "confidence"])
        for scope, params in sorted(dataset.items()):
            for p, e in sorted(params.items()):
                w.writerow([scope, p, e.value, e.unit, e.source, e.method, e.pattern, e.confidence])
    if fac["facilities"]:
        with open(OUT / "facilities.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(fac["facilities"][0].keys()))
            w.writeheader()
            w.writerows(fac["facilities"])
    with open(OUT / "agreement_matrix.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "param", "agree", "sources"])
        for r in agreement:
            w.writerow([r["scope"], r["param"], "AGREE" if r["agree"] else "DISAGREE",
                        "; ".join(f"{k}={v}" for k, v in r["sources"].items())])
    with open(OUT / "validation_findings.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "status", "severity", "detail", "note"])
        w.writeheader()
        w.writerows(findings)

    manifest = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "workspace": ws.name,
        "ai_mode": args.ai,
        "llm_calls": llm.calls_made, "llm_tokens": llm.tokens_used,
        "llm_cost_eur": round(llm.tokens_used * 3e-6, 4),
        "inputs": {d.file: d.sha for d in docs.values()},
        "stage_timings_s": timings,
        "total_s": round(time.time() - t0, 2),
        "extraction": {"total": len(extractions), "deterministic": det, "ai": ai,
                       "manual_overrides": len(overrides), "unresolved": len(unresolved)},
        "versions": {"python": sys.version.split()[0]},
    }
    with open(OUT / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    state = {"dataset": {s: {p: e.dict() for p, e in d.items()} for s, d in dataset.items()},
             "facilities": fac, "agreement": agreement, "findings": findings,
             "workspace": ws.name,
             "files": {"skipped": cfg.get("skipped", []), "unassigned": cfg.get("unassigned", [])},
             "conclusion": {"ranking": conclusion["ranking"], "recommendation": conclusion["recommendation"],
                            "results": conclusion["results"], "skipped": conclusion.get("skipped", {})},
             "gaps": gaps, "manifest": manifest,
             "ingestion": [{"key": d.key, "file": d.file, "format": d.format, "status": d.status,
                            "detail": d.detail, "ms": d.ms, "sha": d.sha} for d in docs.values()],
             "overrides": overrides, "unresolved": unresolved, "audit": audit,
             "llm_log": llm.call_log}
    with open(OUT / "state.json", "w") as f:
        json.dump(state, f, indent=2, default=str)

    print(f"\n\033[1mdone in {manifest['total_s']}s\033[0m - outputs in "
          f"workspaces/{ws.name}/runs/{OUT.name}/ "
          f"(llm calls: {llm.calls_made}, cost: EUR {manifest['llm_cost_eur']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
