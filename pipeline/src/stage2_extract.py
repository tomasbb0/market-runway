"""Stage 2 - pull market parameters out of prose and tables (Tier A), with
per-field LLM escalation (Tier B) for anything the patterns cannot resolve.

Every extracted value carries full provenance:
  {scope, param, value, unit, source, method, pattern, confidence}
method: DET (deterministic pattern) | LLM (Tier B) | MANUAL (override) | INTERNAL
"""
import re
from dataclasses import dataclass, asdict

from . import llm
from .util import load_yaml, parse_number


@dataclass
class Extraction:
    scope: str          # market name | company | competitor | funding
    param: str
    value: object
    unit: str
    source: str         # doc key e.g. "Portugal/screening_report"
    method: str         # DET | LLM | MANUAL
    pattern: str = ""
    confidence: float = 1.0

    def dict(self):
        return asdict(self)


def _apply_patterns(text: str, param: str, spec: dict, word_numbers: dict):
    # PDFs and HTML wrap sentences across lines; patterns are written against
    # single-spaced text, so collapse all whitespace runs first.
    text = re.sub(r"\s+", " ", text)
    for i, pat in enumerate(spec.get("patterns", [])):
        m = re.search(pat, text, re.S)
        if m:
            val = parse_number(m.group(1), word_numbers)
            return val, f"P{i+1}", pat
    return None, None, None


def _postprocess(param: str, unit: str, value):
    if isinstance(value, str):
        return value
    if unit == "fraction" and value > 1:
        value = value / 100.0
    if param in ("cash_runway", "corporate_cost_per_year") and value < 1000:
        value = value * 1_000_000  # 'EUR 4.0 million'
    return round(value, 6) if isinstance(value, float) else value


def extract_all(docs: dict, schema: dict, mode: str) -> tuple[list[Extraction], list[dict], list[dict]]:
    wn = schema["word_numbers"]
    out: list[Extraction] = []
    unresolved: list[dict] = []
    audit: list[dict] = []

    def run_block(scope: str, doc_key: str, params: dict):
        doc = docs.get(doc_key)
        if not doc or doc.status == "failed":
            for p in params:
                unresolved.append({"scope": scope, "param": p, "source": doc_key, "why": "source unreadable"})
            return
        for param, spec in params.items():
            val, pid, pat = _apply_patterns(doc.text, param, spec, wn)
            if val is not None:
                out.append(Extraction(scope, param, _postprocess(param, spec.get("unit", ""), val),
                                      spec.get("unit", ""), doc_key, "DET", pid))
                continue
            ans = llm.extract_field(doc.text, scope, param, spec.get("unit", ""), mode)
            if ans and ans.get("value") is not None:
                out.append(Extraction(scope, param, _postprocess(param, spec.get("unit", ""), ans["value"]),
                                      spec.get("unit", ""), doc_key, "LLM", ans.get("quote", "")[:120],
                                      ans.get("confidence", 0.5)))
            else:
                unresolved.append({"scope": scope, "param": param, "source": doc_key,
                                   "why": "no pattern matched" + ("" if mode != "off" else " (AI off)")})

    # national screening reports: the market parameters
    market_params = schema["market_parameters"]
    for market in [k.split("/")[0] for k in docs if k.endswith("/screening_report")]:
        run_block(market, f"{market}/screening_report", market_params)

    # the landscape summary table: same params again (for agreement), plus internal
    # cost estimates. Optional - a new market pack may not carry one.
    ldoc = docs.get("company/market_landscape")
    order = ["Portugal", "Germany", "Netherlands", "Poland"]
    for table in (ldoc.tables if ldoc else []):
        for row in table:
            if not row or row[0] is None:
                continue
            label = str(row[0]).lower()
            cells = [str(c) if c is not None else "" for c in row[1:5]]
            def emit(param, unit, transform=lambda v: v):
                for mk, cell in zip(order, cells):
                    num = parse_number(re.sub(r"[^\d\.,%]", "", cell).replace("%", ""))
                    if isinstance(num, (int, float)):
                        out.append(Extraction(mk, param, transform(num), unit,
                                              "company/market_landscape", "DET", "table"))
            if "eligible population" in label:
                emit("eligible_population", "persons")
            elif "participation" in label:
                emit("participation", "fraction", lambda v: v / 100)
            elif "positivity" in label:
                emit("fit_positivity", "fraction", lambda v: v / 100)
            elif "price per test" in label:
                emit("price_per_test", "EUR")
            elif "time to reimbursed" in label:
                emit("time_to_reimbursement_months", "months")
            elif "entry cost" in label:
                emit("entry_cost", "EUR")
            elif "in-market cost" in label:
                emit("inmarket_cost_per_year", "EUR")
            elif "colonoscopy reimbursement" in label:
                emit("colonoscopy_tariff", "EUR")

    run_block("company", "company/company_briefing", schema["company_parameters"])
    run_block("competitor", "company/competitor_brief", schema["competitor_parameters"])
    run_block("funding", "company/funding_call", schema["funding_parameters"])

    # --ai max: audit pass - the model independently re-extracts every
    # deterministic value from its source document; disagreements are reported,
    # never silently applied (the deterministic value stays canonical).
    if mode == "max":
        det_all = [e for e in out if e.method == "DET" and e.source in docs]
        for _ai_i, e in enumerate(det_all):
            if _ai_i % 10 == 0:
                print(f"  audit progress: {_ai_i}/{len(det_all)} values re-checked", flush=True)
            ans = llm.extract_field(docs[e.source].text, e.scope, e.param,
                                    e.unit, mode, purpose="audit")
            if ans is None:
                audit.append({"scope": e.scope, "param": e.param, "det": e.value,
                              "llm": None, "verdict": "SKIPPED (no API key / no cache)"})
                continue
            llm_val = _postprocess(e.param, e.unit, ans["value"])
            same = (isinstance(llm_val, (int, float)) and isinstance(e.value, (int, float))
                    and abs(llm_val - e.value) <= max(abs(e.value) * 0.005, 1e-9)) or llm_val == e.value
            audit.append({"scope": e.scope, "param": e.param, "det": e.value,
                          "llm": llm_val, "verdict": "AGREE" if same else "DISAGREE"})
    return out, unresolved, audit
