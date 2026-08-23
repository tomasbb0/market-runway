"""Stage 5 - where the same parameter appears in more than one source, compare
them and report agreement or disagreement explicitly (never silently pick one).
"""
from collections import defaultdict


def agreement_matrix(all_extractions) -> list[dict]:
    groups = defaultdict(dict)
    for e in all_extractions:
        if e.method == "INTERNAL":
            continue
        groups[(e.scope, e.param)][e.source] = e.value
    rows = []
    for (scope, param), by_source in sorted(groups.items()):
        if len(by_source) < 2:
            continue
        vals = list(by_source.values())
        numeric = [v for v in vals if isinstance(v, (int, float))]
        if len(numeric) == len(vals) and numeric:
            ref = numeric[0]
            agree = all(abs(v - ref) <= max(abs(ref) * 0.005, 1e-9) for v in numeric)
        else:
            agree = len({str(v).lower() for v in vals}) == 1
        rows.append({"scope": scope, "param": param, "sources": by_source, "agree": agree})
    return rows
