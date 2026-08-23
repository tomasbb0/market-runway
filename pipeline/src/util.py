"""Shared helpers: paths, config loading, number parsing, name normalisation."""
import hashlib
import re
import unicodedata
from pathlib import Path

import yaml

from .paths import raw_dir, out_dir, current_ws  # noqa: F401  (workspace-aware paths)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"          # legacy seed location (kept for bootstrap)
OUT = ROOT / "data" / "out"          # legacy output location (unused by runs)
CONFIG = ROOT / "config"


def load_yaml(name: str):
    with open(CONFIG / name) as f:
        return yaml.safe_load(f)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def parse_number(raw: str, word_numbers: dict | None = None):
    """'3,050,000' -> 3050000; '6.2' -> 6.2; 'twelve' -> 12 (via word map)."""
    raw = raw.strip()
    if word_numbers and raw.lower() in word_numbers:
        return word_numbers[raw.lower()]
    cleaned = raw.replace(",", "").replace(" ", "")
    try:
        val = float(cleaned)
        return int(val) if val == int(val) else val
    except ValueError:
        return raw


def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


UNIT_RE = re.compile(r"(?:\s*[-–—]\s*Unit\s*(\d+)\s*$)|(?:\s*\(Unit\s*(\d+)\)\s*$)", re.I)


def split_unit(name: str) -> tuple[str, int | None]:
    """'IPO Porto - Unit 4' / 'CHU Coimbra (Unit 6)' -> ('IPO Porto', 4)."""
    m = UNIT_RE.search(name.strip())
    if not m:
        return name.strip(), None
    unit = int(m.group(1) or m.group(2))
    return name[: m.start()].strip(), unit


TYPE_MAP = {
    "endoscopy": "Endoscopy", "endo": "Endoscopy", "endoscopy unit": "Endoscopy",
    "pathology": "Pathology", "path": "Pathology", "pathology unit": "Pathology",
}


def norm_type(t) -> str | None:
    return TYPE_MAP.get(str(t).strip().lower()) if t else None
