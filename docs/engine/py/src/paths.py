"""Workspace-aware path resolution.

A workspace is a folder under workspaces/ holding one assessment:
    workspaces/<name>/raw/         source documents
    workspaces/<name>/manifest.yaml  file -> role mapping (auto-seeded, editable)
    workspaces/<name>/overrides.yaml
    workspaces/<name>/runs/<stamp>/  outputs of one run (state.json, report.html, csvs)
    workspaces/<name>/runs/latest    symlink to the newest run
"""
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACES = ROOT / "workspaces"
CONFIG = ROOT / "config"
DEFAULT_WS = "eu4-case-pack"

_current = {"ws": None, "run": None}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "workspace"


def ws_dir(name: str) -> Path:
    return WORKSPACES / slugify(name)


def list_workspaces() -> list[Path]:
    if not WORKSPACES.exists():
        return []
    return sorted((p for p in WORKSPACES.iterdir() if p.is_dir()), key=lambda p: p.name)


def set_workspace(name: str, new_run: bool = False) -> Path:
    ws = ws_dir(name)
    (ws / "raw").mkdir(parents=True, exist_ok=True)
    (ws / "runs").mkdir(exist_ok=True)
    _current["ws"] = ws
    if new_run:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run = ws / "runs" / stamp
        run.mkdir(parents=True, exist_ok=True)
        latest = ws / "runs" / "latest"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run.name)
        _current["run"] = run
    else:
        _current["run"] = latest_run(ws)
    return ws


def current_ws() -> Path:
    if _current["ws"] is None:
        set_workspace(DEFAULT_WS)
    return _current["ws"]


def raw_dir() -> Path:
    return current_ws() / "raw"


def out_dir() -> Path:
    if _current["run"] is None:
        set_workspace(current_ws().name, new_run=True)
    return _current["run"]


def latest_run(ws: Path) -> Path | None:
    latest = ws / "runs" / "latest"
    if latest.exists():
        return latest.resolve()
    runs = sorted((p for p in (ws / "runs").glob("*") if p.is_dir() and p.name != "latest"))
    return runs[-1] if runs else None


def list_runs(ws: Path) -> list[Path]:
    return sorted((p for p in (ws / "runs").iterdir()
                   if p.is_dir() and not p.is_symlink()), reverse=True)
