"""Stage 3 - resolve extractions into one canonical dataset.

Precedence per (market, parameter): national screening report > landscape
table > other. Where multiple sources carry the same parameter both values are
KEPT for stage 5's agreement matrix; this stage only selects the canonical one
and records what it was selected over. Manual overrides (overrides.yaml) are
applied last and badged MANUAL.
"""
from collections import defaultdict

from .stage2_extract import Extraction
from .util import ROOT, current_ws

import yaml

PRIORITY = {"screening_report": 0, "company_briefing": 0, "competitor_brief": 0,
            "funding_call": 0, "market_landscape": 1}


def _prio(source: str) -> int:
    return PRIORITY.get(source.split("/")[-1], 2)


def build_dataset(extractions: list[Extraction]) -> tuple[dict, list[dict]]:
    """-> (dataset[scope][param] = chosen Extraction, all_candidates list)."""
    groups = defaultdict(list)
    for e in extractions:
        groups[(e.scope, e.param)].append(e)
    dataset: dict[str, dict[str, Extraction]] = defaultdict(dict)
    for (scope, param), cands in groups.items():
        chosen = sorted(cands, key=lambda e: _prio(e.source))[0]
        dataset[scope][param] = chosen
    return dataset, extractions


def apply_overrides(dataset: dict) -> list[dict]:
    ov_path = current_ws() / "overrides.yaml"
    if not ov_path.exists():
        ov_path = ROOT / "overrides.yaml"
    cfg = yaml.safe_load(open(ov_path)) or {}
    applied = []
    for ov in cfg.get("overrides") or []:
        scope, param = ov["field"].split(".", 1)
        prev = dataset.get(scope, {}).get(param)
        dataset.setdefault(scope, {})[param] = Extraction(
            scope, param, ov["value"], prev.unit if prev else "", "overrides.yaml",
            "MANUAL", ov.get("reason", ""), 1.0)
        applied.append({**ov, "previous": prev.value if prev else None})
    return applied


def derive(dataset: dict) -> None:
    """Derived fields, computed not extracted - provenance method INTERNAL."""
    for market, params in list(dataset.items()):
        if market in ("company", "competitor", "funding"):
            continue
        need = ("eligible_population", "participation", "fit_positivity")
        if all(p in params for p in need):
            pop, part, pos = (params[p].value for p in need)
            screened = pop * part / 2
            fitpos = screened * pos
            params["annual_screened"] = Extraction(market, "annual_screened", round(screened),
                                                   "persons", "derived", "INTERNAL",
                                                   "eligible x participation / 2 (biennial)")
            params["addressable_fit_positive"] = Extraction(market, "addressable_fit_positive", round(fitpos),
                                                            "persons", "derived", "INTERNAL",
                                                            "annual_screened x positivity")
    comp = dataset.get("company", {})
    if "sensitivity" in comp and "specificity" in comp and "deferral_rate" in comp:
        sens, spec, defer = comp["sensitivity"].value, comp["specificity"].value, comp["deferral_rate"].value
        # deferred = (1-sens)*p + spec*(1-p)  ->  p = (spec-deferred)/(spec-(1-sens))
        p = (spec - defer) / (spec - (1 - sens))
        comp["implied_prevalence"] = Extraction("company", "implied_prevalence", round(p, 4),
                                                "fraction", "derived", "INTERNAL",
                                                "solved from sens/spec/deferral")
