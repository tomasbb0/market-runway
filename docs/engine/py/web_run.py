"""Browser engine driver: run the seven stages on a workspace, emit state + report."""
import json, sys, time
from datetime import datetime, timezone
from pathlib import Path

# rapidfuzz shim (no wasm build): difflib-based token_set_ratio, used only as
# the fallback behind the curated alias map
try:
    import rapidfuzz  # noqa: F401
except ModuleNotFoundError:
    import difflib, types
    def token_set_ratio(a, b):
        ta, tb = set(a.lower().split()), set(b.lower().split())
        inter = " ".join(sorted(ta & tb))
        sa, sb = " ".join(sorted(ta)), " ".join(sorted(tb))
        r = max(difflib.SequenceMatcher(None, inter, sa).ratio(),
                difflib.SequenceMatcher(None, inter, sb).ratio(),
                difflib.SequenceMatcher(None, sa, sb).ratio())
        return r * 100
    m = types.ModuleType("rapidfuzz"); m.fuzz = types.ModuleType("rapidfuzz.fuzz")
    m.fuzz.token_set_ratio = token_set_ratio
    sys.modules["rapidfuzz"] = m; sys.modules["rapidfuzz.fuzz"] = m.fuzz

sys.path.insert(0, "/app")

def run(ws_name: str, ai: str = "off") -> dict:
    t0 = time.time()
    from src import llm
    from src.util import load_yaml
    from src.paths import set_workspace
    from src.mapper import build_manifest
    from src.stage1_read import read_pack
    from src.stage2_extract import extract_all
    from src.stage3_schema import build_dataset, apply_overrides, derive
    from src.stage4_facilities import dedupe
    from src.stage5_reconcile import agreement_matrix
    from src.stage6_validate import run_checks
    from src.stage7_conclude import conclude, gap_report
    from src.report import build as build_report

    ws = set_workspace(ws_name, new_run=True)
    cfg = build_manifest(ws)
    schema = load_yaml("schema.yaml")
    docs = read_pack(cfg)
    extractions, unresolved, audit = extract_all(docs, schema, ai)
    dataset, all_ex = build_dataset(extractions)
    overrides = apply_overrides(dataset)
    derive(dataset)
    fac = dedupe(docs, cfg)
    agreement = agreement_matrix(all_ex)
    findings = run_checks(dataset, agreement, fac)
    conclusion = conclude(dataset)
    gaps = gap_report(dataset, unresolved)

    det = sum(e.method == "DET" for e in extractions)
    manifest = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "workspace": ws.name, "ai_mode": ai,
        "llm_calls": llm.calls_made, "llm_tokens": llm.tokens_used,
        "llm_cost_eur": round(llm.tokens_used * 3e-6, 4),
        "inputs": {d.file: d.sha for d in docs.values()},
        "stage_timings_s": {}, "total_s": round(time.time() - t0, 2),
        "extraction": {"total": len(extractions), "deterministic": det,
                       "ai": sum(e.method == "LLM" for e in extractions),
                       "manual_overrides": len(overrides), "unresolved": len(unresolved)},
        "versions": {"python": sys.version.split()[0] + " (browser/wasm)"},
    }
    state = {"dataset": {s: {p: e.dict() for p, e in d.items()} for s, d in dataset.items()},
             "facilities": fac, "agreement": agreement, "findings": findings,
             "workspace": ws.name,
             "files": {"skipped": cfg.get("skipped", []), "unassigned": cfg.get("unassigned", [])},
             "conclusion": {"ranking": conclusion["ranking"], "recommendation": conclusion["recommendation"],
                            "results": conclusion["results"], "skipped": conclusion.get("skipped", {})},
             "gaps": gaps, "manifest": manifest,
             "ingestion": [{"key": d.key, "file": d.file, "format": d.format, "status": d.status,
                            "detail": d.detail, "ms": d.ms, "sha": d.sha} for d in docs.values()],
             "overrides": overrides, "unresolved": unresolved, "audit": audit}
    from src.paths import out_dir
    out = out_dir()
    state_path = out / "state.json"
    state_path.write_text(json.dumps(state, default=str))
    build_report(str(state_path))
    report_html = (out / "report.html").read_text()
    return {"state": state, "report": report_html,
            "summary": {"recommendation": conclusion["recommendation"],
                        "ranking": conclusion["ranking"],
                        "unresolved": len(unresolved), "det": det,
                        "seconds": manifest["total_s"]}}
