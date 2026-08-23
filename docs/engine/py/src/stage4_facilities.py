"""Stage 4 - one row per real facility, with the rule stated.

THE DEDUPLICATION RULE (also printed in the dashboard):
  1. Repair structurally corrupted rows where the shift pattern is unambiguous
     (Poland CSV carries 6 column-shifted rows); otherwise exclude and report.
  2. Normalise: strip diacritics, annualise capacity (Germany reports 126 rows
     MONTHLY - x12), map register-specific type labels (ENDO/PATH/'Endoscopy
     Unit'...) to {Endoscopy, Pathology}.
  3. Entity key = (country, canonical institution, unit number). Register IDs
     are NOT trusted: the same physical unit appears under many ids (e.g.
     'IPO Porto - Unit 1' under 14 different FAC ids). Unit TYPE is an
     attribute, not identity: 208 of 228 units appear under BOTH type labels
     across duplicate records, so type is resolved by majority vote (ties
     broken toward Endoscopy when capacity evidence exists) and every
     conflict is flagged, never silently dropped.
  4. Master-registry institution names are translated to national-register
     canonical names via a curated alias map (config/aliases.yaml), seeded by
     fuzzy matching and human-reviewed; unresolved names fall back to
     rapidfuzz token_set_ratio >= 90.
  5. Precedence: the national register is authoritative. Master rows matching
     a national entity become corroboration; master-only entities are ADDED,
     flagged source=master-only.
  6. Where duplicate records disagree on capacity, the median of non-null
     annualised values is used and the min-max spread is reported - the
     disagreement is surfaced, not silently resolved.
"""
import statistics
from collections import defaultdict

from rapidfuzz import fuzz

from .util import load_yaml, strip_diacritics, split_unit, norm_type


def _annualise(cap, period) -> float | None:
    if cap in (None, ""):
        return None
    try:
        v = float(str(cap).replace(",", ""))
    except ValueError:
        return None
    if period and str(period).strip().lower() == "monthly":
        v *= 12
    return v


def _repair_poland(row: dict) -> tuple[dict | None, str]:
    """Fix the 3 observed shift patterns; return (fixed_row|None, action)."""
    if row["type"] in ("ENDO", "PATH"):
        return row, "ok"
    # pattern A: id cell holds 'id name', values shifted left by one
    if row["country"] in ("ENDO", "PATH") and " " in row["id"]:
        rid, name = row["id"].split(" ", 1)
        return ({"id": rid, "name": name, "country": "Poland", "type": row["country"],
                 "capacity_annual": row["type"]}, "repaired:left-shift")
    # pattern B: country missing, fields shifted left from country on
    if row["country"] in ("ENDO", "PATH"):
        return ({"id": row["id"], "name": row["name"], "country": "Poland",
                 "type": row["country"], "capacity_annual": row["type"]}, "repaired:no-country")
    # pattern C: type and capacity swapped
    if row["capacity_annual"] in ("ENDO", "PATH"):
        return ({"id": row["id"], "name": row["name"], "country": row["country"],
                 "type": row["capacity_annual"], "capacity_annual": row["type"]}, "repaired:swap")
    return None, "excluded:unrepairable"


def _norm_records(docs, markets_cfg):
    """Yield normalised records {source, country, institution, unit, type, capacity}."""
    records, repairs = [], []
    monthly = 0
    for market, mspec in markets_cfg["markets"].items():
        spec = mspec.get("facility_register")
        if not spec or f"{market}/facility_register" not in docs:
            continue
        cols = spec.get("columns") or {}
        doc = docs[f"{market}/facility_register"]
        for raw in doc.rows:
            row = {k: raw.get(v) for k, v in cols.items()}
            if market == "Poland":
                fixed, action = _repair_poland({**raw})
                if action != "ok":
                    repairs.append({"market": market, "raw": dict(raw), "action": action})
                if fixed is None:
                    continue
                row = {k: fixed.get(v) for k, v in cols.items()}
            name = str(row["name"] or "").strip()
            if not name:
                continue
            if str(row.get("period") or "").strip().lower() == "monthly":
                monthly += 1
            inst, unit = split_unit(strip_diacritics(name))
            records.append({
                "register": f"national:{market}", "country": market, "institution": inst,
                "unit": unit, "type": norm_type(row.get("type")),
                "capacity": _annualise(row.get("capacity"), row.get("period")),
                "orig_name": name, "orig_id": str(row.get("id") or ""),
            })
    # legacy master registry (optional)
    mspec = markets_cfg.get("shared_docs", {}).get("master_registry")
    doc = docs.get("shared/master_registry")
    cols = mspec["columns"] if mspec else {}
    for raw in (doc.rows if doc and mspec else []):
        row = {k: raw.get(v) for k, v in cols.items()}
        name = str(row["name"] or "").strip()
        if not name or row["country"] not in markets_cfg["markets"]:
            continue
        inst, unit = split_unit(strip_diacritics(name))
        records.append({
            "register": "master", "country": row["country"], "institution": inst,
            "unit": unit, "type": norm_type(row.get("type")),
            "capacity": _annualise(row.get("capacity"), None),
            "orig_name": name, "orig_id": str(row.get("id") or ""),
        })
    return records, repairs, monthly


def _canonicalise(records, aliases):
    """Map master institution names to national canonical names."""
    unmatched = set()
    national = defaultdict(set)
    for r in records:
        if r["register"] != "master":
            national[r["country"]].add(r["institution"])
    for r in records:
        if r["register"] != "master":
            r["canonical"] = r["institution"]
            continue
        amap = aliases.get(r["country"], {})
        if r["institution"] in amap:
            r["canonical"], r["match"] = amap[r["institution"]], "alias-map"
            continue
        best, score = None, 0
        for cand in national[r["country"]]:
            s = fuzz.token_set_ratio(r["institution"].lower(), cand.lower())
            if s > score:
                best, score = cand, s
        if score >= 90:
            r["canonical"], r["match"] = best, f"fuzzy:{score:.0f}"
        else:
            r["canonical"], r["match"] = r["institution"], "master-only"
            unmatched.add((r["country"], r["institution"]))
    return unmatched


def dedupe(docs, markets_cfg) -> dict:
    aliases = load_yaml("aliases.yaml")
    records, repairs, monthly = _norm_records(docs, markets_cfg)
    unmatched = _canonicalise(records, aliases)

    groups = defaultdict(list)
    for r in records:
        groups[(r["country"], r["canonical"], r["unit"])].append(r)

    facilities, capacity_conflicts, type_conflicts = [], 0, 0
    for i, ((country, inst, unit), grp) in enumerate(sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or 0))):
        types = [g["type"] for g in grp if g["type"]]
        counts = {t: types.count(t) for t in set(types)}
        has_cap = any(g["capacity"] is not None for g in grp)
        if len(counts) > 1:
            type_conflicts += 1
            top = max(counts.values())
            leaders = sorted(t for t, c in counts.items() if c == top)
            ftype = leaders[0] if len(leaders) == 1 else ("Endoscopy" if has_cap else "Pathology")
        else:
            ftype = next(iter(counts), None)
        caps = sorted({g["capacity"] for g in grp if g["capacity"] is not None})
        med = statistics.median(caps) if caps else None
        conflict = len(caps) > 1
        capacity_conflicts += conflict
        regs = sorted({g["register"] for g in grp})
        facilities.append({
            "facility_uid": f"HLX-{country[:2].upper()}-{i+1:03d}",
            "country": country, "institution": inst, "unit": unit, "type": ftype,
            "type_votes": "/".join(f"{t}:{c}" for t, c in sorted(counts.items())),
            "type_conflict": len(counts) > 1,
            "capacity_annual": round(med) if med is not None and ftype == "Endoscopy" else None,
            "capacity_min": min(caps) if caps and ftype == "Endoscopy" else None,
            "capacity_max": max(caps) if caps and ftype == "Endoscopy" else None,
            "capacity_conflict": conflict and ftype == "Endoscopy",
            "n_source_records": len(grp),
            "registers": "+".join(regs),
            "master_only": regs == ["master"],
        })

    raw_counts = defaultdict(int)
    for r in records:
        raw_counts[r["country"]] += 1
    summary = {
        "raw_records": len(records),
        "raw_by_country": dict(raw_counts),
        "unique_facilities": len(facilities),
        "capacity_conflicts": capacity_conflicts,
        "type_conflicts": type_conflicts,
        "master_only": sum(f["master_only"] for f in facilities),
        "repairs": repairs,
        "unmatched_master_institutions": sorted(unmatched),
        "monthly_annualised": monthly,
    }
    return {"facilities": facilities, "summary": summary}
