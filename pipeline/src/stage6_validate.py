"""Stage 6 - check the extracted figures against each other and against basic
arithmetic. Checks are DATA (config/checks.yaml), not code: a new market means
new checks without touching the engine.
"""
from .util import load_yaml


def _values(dataset, scope):
    return {p: e.value for p, e in dataset.get(scope, {}).items()}


def run_checks(dataset, agreement, facilities) -> list[dict]:
    cfg = load_yaml("checks.yaml")["checks"]
    findings = []
    markets = [m for m in dataset if m not in ("company", "competitor", "funding")]

    for chk in cfg:
        kind = chk["kind"]
        if kind == "cross_source_agreement":
            bad = [r for r in agreement if not r["agree"]]
            findings.append(_f(chk, not bad,
                              f"{len(agreement)} multi-source parameters compared; "
                              f"{len(bad)} disagreement(s)" + (f": {[(b['scope'], b['param']) for b in bad]}" if bad else "")))
        elif kind == "range":
            bad = []
            for scope in list(markets) + ["company", "funding"]:
                for f_ in chk["fields"]:
                    v = _values(dataset, scope).get(f_)
                    if v is not None and not (chk["min"] <= v <= chk["max"]):
                        bad.append((scope, f_, v))
            findings.append(_f(chk, not bad, f"{len(bad)} out-of-range value(s)" + (f": {bad}" if bad else "")))
        elif kind == "expression":
            scopes = markets if chk.get("per_market") else [chk.get("market", "company")]
            bad, detail = [], []
            for scope in scopes:
                env = {**_values(dataset, "company"), **_values(dataset, "competitor"),
                       **_values(dataset, scope)}
                env["abs"] = abs
                try:
                    ok = bool(eval(chk["expression"], {"__builtins__": {}}, env))  # noqa: S307 - closed config, no user input
                except Exception as e:  # noqa: BLE001
                    ok, detail = False, [f"could not evaluate: {e}"]
                if not ok:
                    bad.append(scope)
                    if chk["id"] == "CHK-02" and isinstance(env.get("onco_tests_per_year"), (int, float)) \
                            and isinstance(env.get("addressable_fit_positive"), (int, float)):
                        detail = [f"OncoStream claims {env.get('onco_tests_per_year'):,} tests/yr but Germany's "
                                  f"entire organised addressable volume is {env.get('addressable_fit_positive'):,.0f}/yr "
                                  f"({env.get('onco_tests_per_year')/env.get('addressable_fit_positive'):.1f}x the whole market). "
                                  "Company-reported figure REJECTED for modelling; the independent 35-40% share "
                                  "estimate (~61-70k tests/yr) is retained instead."]
            if detail:
                msg = "; ".join(detail)
            elif bad:
                msg = "fails for " + ", ".join(bad)
            else:
                msg = "holds for " + ", ".join(scopes)
            findings.append(_f(chk, not bad, msg))
        elif kind == "facility":
            no_cap = [f_ for f_ in facilities["facilities"] if f_["type"] == "Endoscopy" and f_["capacity_annual"] in (None, 0)]
            findings.append(_f(chk, not no_cap,
                              f"{facilities['summary']['monthly_annualised']} monthly rows annualised x12; "
                              f"{len(no_cap)} endoscopy unit(s) without resolvable capacity"))
        elif kind == "capacity_pressure":
            lines = []
            for m in markets:
                fitpos = _values(dataset, m).get("addressable_fit_positive")
                cap = sum(f_["capacity_annual"] or 0 for f_ in facilities["facilities"]
                          if f_["country"] == m and f_["type"] == "Endoscopy")
                if fitpos and cap:
                    lines.append(f"{m}: {fitpos:,.0f} referrals vs {cap:,.0f} register capacity ({fitpos/cap:.0%} utilisation)")
            findings.append(_f(chk, True, " | ".join(lines)))
    return findings


def _f(chk, ok, detail):
    status = "PASS" if ok else ("FAIL" if chk["severity"] == "fail" else "WARN")
    if chk["severity"] == "info":
        status = "INFO"
    return {"id": chk["id"], "name": chk["name"], "status": status,
            "severity": chk["severity"], "detail": detail, "note": chk.get("note", "")}
