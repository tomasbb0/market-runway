"""Stage 1 - read every file in its native format. No manual retyping.

Each reader returns a `Doc`: full plain text (for pattern extraction), any
tables found, and a per-file ingestion record for the dashboard board.
"""
import re
import time
from dataclasses import dataclass, field

import pdfplumber
import openpyxl
from bs4 import BeautifulSoup

from .util import raw_dir, sha256


@dataclass
class Doc:
    key: str                 # e.g. "Portugal/screening_report"
    file: str
    format: str
    text: str = ""
    tables: list = field(default_factory=list)   # list[list[list[str]]]
    rows: list = field(default_factory=list)     # for tabular registers
    status: str = "parsed"                       # parsed | partial | failed
    detail: str = ""
    sha: str = ""
    ms: int = 0


def read_pdf(path) -> tuple[str, list]:
    text_parts, tables = [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
            for t in page.extract_tables():
                tables.append(t)
    return "\n".join(text_parts), tables


def read_xlsx(path, sheet=None) -> tuple[str, list, list]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb.active
    grid = [[c.value for c in row] for row in ws.iter_rows()]
    # text view: every non-empty cell, pipe-joined per row (for regex extraction)
    text = "\n".join(
        " | ".join(str(c) for c in row if c is not None) for row in grid if any(c is not None for c in row)
    )
    # dict rows if first non-empty row looks like a header
    rows = []
    header = next((r for r in grid if r and all(isinstance(c, str) for c in r if c is not None) and sum(c is not None for c in r) >= 3), None)
    if header and grid.index(header) == 0:
        hdr = [str(c) for c in header]
        rows = [dict(zip(hdr, r)) for r in grid[1:] if any(c is not None for c in r)]
    return text, [grid], rows


def read_html(path) -> tuple[str, list, list]:
    soup = BeautifulSoup(open(path).read(), "html.parser")
    text = soup.get_text("\n")
    tables, rows = [], []
    for table in soup.find_all("table"):
        grid = [[td.get_text(strip=True) for td in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
        tables.append(grid)
        if grid and len(grid) > 1:
            hdr = grid[0]
            rows += [dict(zip(hdr, r)) for r in grid[1:]]
    return text, tables, rows


def read_csv(path) -> list:
    import csv
    with open(path) as f:
        return list(csv.DictReader(f))


def read_doc(key: str, spec: dict) -> Doc:
    path = raw_dir() / spec["file"]
    doc = Doc(key=key, file=spec["file"], format=spec["format"], sha=sha256(path))
    t0 = time.time()
    try:
        if spec["format"] == "pdf":
            doc.text, doc.tables = read_pdf(path)
            if not doc.text.strip():
                doc.status, doc.detail = "failed", "no text layer - would escalate to vision tier"
        elif spec["format"] == "xlsx":
            doc.text, doc.tables, doc.rows = read_xlsx(path, spec.get("sheet"))
        elif spec["format"] == "html":
            doc.text, doc.tables, doc.rows = read_html(path)
        elif spec["format"] == "csv":
            doc.rows = read_csv(path)
            doc.text = "\n".join(" | ".join(str(v) for v in r.values()) for r in doc.rows[:5])
        else:
            doc.status, doc.detail = "failed", f"unknown format {spec['format']}"
    except Exception as e:  # noqa: BLE001 - a reader failure must never kill the run
        doc.status, doc.detail = "failed", f"{type(e).__name__}: {e}"
    doc.ms = int((time.time() - t0) * 1000)
    return doc


def read_pack(markets_cfg: dict) -> dict[str, Doc]:
    docs: dict[str, Doc] = {}
    for key, spec in markets_cfg["company_docs"].items():
        docs[f"company/{key}"] = read_doc(f"company/{key}", spec)
    for market, mspec in markets_cfg["markets"].items():
        for key, spec in mspec.items():
            docs[f"{market}/{key}"] = read_doc(f"{market}/{key}", spec)
    for key, spec in markets_cfg["shared_docs"].items():
        docs[f"shared/{key}"] = read_doc(f"shared/{key}", spec)
    return docs
