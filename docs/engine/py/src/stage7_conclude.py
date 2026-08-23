"""Stage 7 - reach a final conclusion.

Runs the five-year financial engine over EVERY market from the validated
dataset (the same math the Excel model implements for the selected market),
ranks the markets, and produces the evidence-gap report that would drive the
(deliberately disabled) research workflow.

Model, annual granularity:
  ramp_since_reimbursement = [7%, 13%, 20%, 22%, 24%] of addressable
    (anchored on the pack's benchmark: ~20% of eligible volume within
     3 years of reimbursement)
  revenue offset years = ceil(time_to_reimbursement / 12)
  COGS: linear 58 -> 44 over Y1..Y5 (company briefing)
  EBITDA_y = tests_y * (price - cogs_y) - inmarket_cost - corporate_cost
  cash_y  = cash_{y-1} + EBITDA_y   (entry cost deducted at Y1)
Germany pre-reimbursement revenue is held at zero per the national report
("planning assumptions should treat pre-reimbursement revenue as immaterial").
"""
import math

RAMP = [0.07, 0.13, 0.20, 0.22, 0.24]
YEARS = 5


def project(params: dict, company: dict, ramp_mult: float = 1.0, delay_extra_months: int = 0) -> dict:
    fitpos = params["addressable_fit_positive"]
    price = params["price_per_test"]
    ttr = params["time_to_reimbursement_months"] + delay_extra_months
    offset = math.ceil(ttr / 12)
    cogs1, cogs5 = company["cogs_year1"], company["cogs_year5"]
    corp = company["corporate_cost_per_year"]
    cash = company["cash_runway"] - params["entry_cost"]
    years, be_year, min_cash = [], None, cash
    for y in range(1, YEARS + 1):
        ramp = RAMP[y - offset - 1] * ramp_mult if y > offset and (y - offset - 1) < len(RAMP) else 0.0
        tests = fitpos * ramp
        cogs = cogs1 + (cogs5 - cogs1) * (y - 1) / (YEARS - 1)
        gm = tests * (price - cogs)
        ebitda = gm - params["inmarket_cost_per_year"] - corp
        cash += ebitda
        min_cash = min(min_cash, cash)
        if be_year is None and ebitda > 0:
            be_year = y
        years.append({"year": y, "ramp": ramp, "tests": round(tests), "cogs": round(cogs, 2),
                      "revenue": round(tests * price), "gross_margin": round(gm),
                      "ebitda": round(ebitda), "cash": round(cash)})
    return {"years": years, "break_even_year": be_year, "min_cash": round(min_cash),
            "end_cash": round(cash), "insolvent": min_cash < 0, "offset_years": offset}


REQUIRED_MARKET = ("addressable_fit_positive", "price_per_test", "time_to_reimbursement_months",
                   "entry_cost", "inmarket_cost_per_year")
REQUIRED_COMPANY = ("cogs_year1", "cogs_year5", "corporate_cost_per_year", "cash_runway", "deferral_rate")


def conclude(dataset) -> dict:
    company = {p: e.value for p, e in dataset.get("company", {}).items()}
    results, skipped = {}, {}
    missing_company = [k for k in REQUIRED_COMPANY if k not in company]
    for market, params in dataset.items():
        if market in ("company", "competitor", "funding"):
            continue
        p = {k: e.value for k, e in params.items()}
        missing = [k for k in REQUIRED_MARKET if k not in p] + missing_company
        if missing:
            skipped[market] = sorted(set(missing))
            continue
        r = project(p, company)
        defer = company["deferral_rate"]
        if "colonoscopy_tariff" in p:
            r["system_saving_per_100"] = round(defer * 100 * p["colonoscopy_tariff"] - 100 * p["price_per_test"])
        r["params"] = p
        results[market] = r
    if not results:
        return {"results": {}, "ranking": [], "recommendation": None, "skipped": skipped}

    def rank_key(m):
        r = results[m]
        return (r["insolvent"], -(r["end_cash"]))
    ranking = sorted(results, key=rank_key)
    return {"results": results, "ranking": ranking, "recommendation": ranking[0], "skipped": skipped}


def gap_report(dataset, unresolved) -> list[dict]:
    """Evidence gaps: fields the schema wants but the pack cannot support, plus
    single-source parameters that materially drive the model. Each gap carries
    the research plan the (disabled) sourcing workflow would execute."""
    gaps = [
        {"id": "GAP-01", "market": "Germany", "field": "opportunistic testing volume",
         "why": "Explicitly not centrally reported; excluded from the base case per the national report.",
         "impact": "Upside only - could enlarge German addressable volume.",
         "plan": ["Query: KBV/G-BA opportunistic FIT volume statistics",
                  "Source type: statutory insurance billing data (EBM codes)",
                  "Fills: Germany.opportunistic_volume (quarantined until human-approved)"]},
        {"id": "GAP-02", "market": "all", "field": "competitor list price",
         "why": "Competitor brief says 'broadly similar list price' - no number anywhere in the pack.",
         "impact": "Pricing pressure scenario in NL/PT/PL cannot be quantified.",
         "plan": ["Query: OncoStream tender records, national procurement portals",
                  "Source type: public tender award notices",
                  "Fills: competitor.list_price per market (quarantined until human-approved)"]},
        {"id": "GAP-03", "market": "company", "field": "IVDR certification timeline",
         "why": "Single source (company briefing, 'expected within about a year'); no corroboration.",
         "impact": "A slip would not block CE-marked sales but matters for tenders.",
         "plan": ["Query: notified-body queue times for IVDR class C assays",
                  "Source type: MedTech Europe / notified body reports",
                  "Fills: company.ivdr_expected_months (quarantined until human-approved)"]},
        {"id": "GAP-04", "market": "all", "field": "penetration benchmark",
         "why": "Ramp rests on ONE comparable pilot ('one fifth of eligible volume within three years').",
         "impact": "The single most sensitive model input; the ±50% ramp scenario brackets it.",
         "plan": ["Query: published uptake curves for triage assays post-reimbursement",
                  "Source type: peer-reviewed screening-programme evaluations",
                  "Fills: company.penetration_benchmark corroboration (quarantined until human-approved)"]},
    ]
    for u in unresolved:
        gaps.append({"id": f"GAP-U{len(gaps)+1}", "market": u["scope"], "field": u["param"],
                     "why": u["why"], "impact": "Field unresolved by extraction.",
                     "plan": ["Escalate to Tier B extraction or manual review"]})
    return gaps
