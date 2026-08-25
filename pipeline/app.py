#!/usr/bin/env python3
"""Runway, the market-entry desk. Local product UI over the pipeline.

    .venv/bin/python app.py      →  http://127.0.0.1:8765

Structure:
  /                      home: workspace finder (one folder per assessment)
  /new                   create a workspace
  /w/<ws>                workspace: files (upload/delete/clean, role-mapped,
                         unassigned surfaced), run panel, run history
  /w/<ws>/run            execute the pipeline for that workspace
  /w/<ws>/report/<run>   that run's dashboard
  /w/<ws>/chat           grounded AI chat over the latest run (can propose
                         overrides; applying re-runs the pipeline)

The Anthropic key is session-only: memory, never disk, never logged.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import uuid

import yaml
from flask import (Flask, Response, jsonify, redirect, request, send_file,
                   session, stream_with_context)

sys.path.insert(0, str(Path(__file__).parent))
from src.paths import WORKSPACES, ws_dir, list_workspaces, list_runs, latest_run, slugify  # noqa: E402
from src.mapper import build_manifest  # noqa: E402

ROOT = Path(__file__).resolve().parent
PY = sys.executable
ROBOT = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
         'stroke-linecap="round" stroke-linejoin="round" '
         'style="width:15px;height:15px;vertical-align:-2px;margin-left:7px">'
         '<rect x="5" y="8" width="14" height="11" rx="3"/>'
         '<path d="M12 8V4.5"/><circle cx="12" cy="3.4" r="1" fill="currentColor" stroke="none"/>'
         '<circle cx="9.3" cy="12.5" r="1.15" fill="currentColor" stroke="none"/>'
         '<circle cx="14.7" cy="12.5" r="1.15" fill="currentColor" stroke="none"/>'
         '<path d="M9.5 16h5"/></svg>')
TRASH = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
         'stroke-linecap="round" stroke-linejoin="round">'
         '<path d="M4 7h16M10 7V5h4v2M6 7l1 13h10l1-13M10 11v6M14 11v6"/></svg>')

EXTS = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" style="width:12px;height:12px;'
        'vertical-align:-1px;margin-left:5px">'
        '<path d="M14 5h5v5M19 5l-8 8M19 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h4"/></svg>')
EYE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
       'stroke-linecap="round" stroke-linejoin="round" style="width:15px;height:15px">'
       '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/>'
       '<circle cx="12" cy="12" r="2.6"/></svg>')
DLI = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
       'stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px">'
       '<path d="M12 4v11M7 10l5 5 5-5M5 19h14"/></svg>')
GEARS = ('<svg viewBox="0 0 24 24" fill="currentColor" fill-rule="evenodd"><path d="M18.79 10.31 '
         'L21.70 10.64 L21.70 13.36 L18.79 13.69 L18.00 15.61 L19.83 17.90 L17.90 19.83 L15.61 18.00 '
         'L13.69 18.79 L13.36 21.70 L10.64 21.70 L10.31 18.79 L8.39 18.00 L6.10 19.83 L4.17 17.90 '
         'L6.00 15.61 L5.21 13.69 L2.30 13.36 L2.30 10.64 L5.21 10.31 L6.00 8.39 L4.17 6.10 L6.10 4.17 '
         'L8.39 6.00 L10.31 5.21 L10.64 2.30 L13.36 2.30 L13.69 5.21 L15.61 6.00 L17.90 4.17 L19.83 6.10 '
         'L18.00 8.39 Z M15.1 12 A3.1 3.1 0 1 0 8.9 12 A3.1 3.1 0 1 0 15.1 12 Z"/></svg>')

app = Flask(__name__)
app.secret_key = os.environ.get("RUNWAY_SECRET") or os.urandom(24).hex()
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024   # 30 MB per upload batch
RUNWAY_PASS = os.environ.get("RUNWAY_PASS", "")

KEYS: dict = {}   # per-browser-session provider keys; mirrored to a gitignored file
KEYSTORE = Path(__file__).resolve().parent / "workspaces" / ".keys.json"


def _keys_save():
    try:
        KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
        KEYSTORE.write_text(json.dumps(KEYS))
        os.chmod(KEYSTORE, 0o600)
    except OSError:
        pass


try:
    KEYS.update(json.loads(KEYSTORE.read_text()))
except (OSError, ValueError):
    pass
RUNTASKS: dict = {}   # run token -> {lines, done, ok, ws, run}


app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30   # 30 days


def _sid() -> str:
    session.permanent = True
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]


# --- fuzzy password: Portuguese QWERTY neighbourhood tolerance -----------
_ROWS = [("1234567890'", 0.0), ("qwertyuiop+", 0.5), ("asdfghjklç", 0.75), ("zxcvbnm,.-", 1.25)]
_POS = {}
for _r, (_keys, _off) in enumerate(_ROWS):
    for _i, _ch in enumerate(_keys):
        _POS[_ch] = (_r, _i + _off)


def _adjacent(x: str, y: str) -> bool:
    x, y = x.lower(), y.lower()
    if x == y:
        return True
    px, py = _POS.get(x), _POS.get(y)
    if not px or not py:
        return False
    return abs(px[0] - py[0]) <= 1 and abs(px[1] - py[1]) <= 1.3


def fuzzy_pass(typed: str, real: str, budget: int = 2) -> bool:
    # Damerau-style: case-free; adjacent-key substitution costs 1; adjacent
    # transposition costs 0; insert/delete cost 1; accept if total <= budget.
    t, r = typed.lower(), real.lower()
    if abs(len(t) - len(r)) > budget:
        return False
    INF = 99
    n, m = len(t), len(r)
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0
    for i in range(n + 1):
        for j in range(m + 1):
            c = dp[i][j]
            if c > budget:
                continue
            if i < n and j < m:
                if t[i] == r[j]:
                    dp[i + 1][j + 1] = min(dp[i + 1][j + 1], c)
                elif _adjacent(t[i], r[j]):
                    dp[i + 1][j + 1] = min(dp[i + 1][j + 1], c + 1)
            if i < n:
                dp[i + 1][j] = min(dp[i + 1][j], c + 2)
            if j < m:
                dp[i][j + 1] = min(dp[i][j + 1], c + 2)
            if i + 1 < n and j + 1 < m and t[i] == r[j + 1] and t[i + 1] == r[j]:
                dp[i + 2][j + 2] = min(dp[i + 2][j + 2], c)
    return dp[n][m] <= budget


def sk() -> dict:
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    return KEYS.setdefault(_sid(), {"value": k, "provider": detect_provider(k)})


@app.before_request
def _gate():
    if not RUNWAY_PASS or request.path == "/login" or session.get("authed"):
        return None
    return redirect("/login")


@app.get("/login")
def login_page():
    return (f'<!doctype html><meta charset="utf-8"><title>Market Runway</title>{STYLE}'
            '<div style="min-height:100svh;display:grid;place-content:center;gap:14px;text-align:center">'
            '<div class="eyebrow"><span class="tag"></span>MARKET RUNWAY · PRIVATE DESK</div>'
            '<form method="post" action="/login" style="display:flex;gap:10px">'
            '<input type="password" name="p" placeholder="access password" autofocus '
            'style="font-family:monospace">'
            '<button class="primary">Enter</button></form></div>')


@app.post("/login")
def login_post():
    typed = request.form.get("p", "")
    if typed == RUNWAY_PASS or fuzzy_pass(typed, RUNWAY_PASS):
        session["authed"] = True
        return redirect("/")
    return redirect("/login")


def detect_provider(key: str) -> str | None:
    """Key-format detection: deterministic, instant, and it cannot hallucinate."""
    key = (key or "").strip()
    if key.startswith("sk-ant-"):
        return "anthropic"
    if re.match(r"^AIza[0-9A-Za-z_-]{30,}$", key):
        return "google"
    if key.startswith("sk-"):
        return "openai"
    return None


PROVIDERS = {
    "anthropic": {"label": "Anthropic", "models": {
        "claude-sonnet-5": "Claude Sonnet 5 (default)",
        "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
        "claude-fable-5": "Claude Fable 5"}},
    "openai": {"label": "OpenAI", "models": {
        "gpt-5.1": "GPT-5.1 (default)",
        "gpt-5-mini": "GPT-5 mini"}},
    "google": {"label": "Google", "models": {
        "gemini-3-pro-preview": "Gemini 3 Pro (default)",
        "gemini-2.5-flash": "Gemini 2.5 Flash"}},
}


def _chat_call(provider: str, key: str, model: str, system: str, msgs: list) -> str:
    """Route one grounded chat turn to the detected provider. Returns reply text."""
    import urllib.request
    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(model=model, max_tokens=900,
                                      system=system, messages=msgs)
        return resp.content[0].text
    if provider == "openai":
        body = {"model": model, "max_completion_tokens": 900,
                "messages": [{"role": "system", "content": system}] + msgs}
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=90) as r:
            out = json.load(r)
        return out["choices"][0]["message"]["content"]
    if provider == "google":
        contents = [{"role": "model" if m["role"] == "assistant" else "user",
                     "parts": [{"text": m["content"]}]} for m in msgs]
        body = {"system_instruction": {"parts": [{"text": system}]}, "contents": contents,
                "generationConfig": {"maxOutputTokens": 900, "temperature": 0}}
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            out = json.load(r)
        return out["candidates"][0]["content"]["parts"][0]["text"]
    raise ValueError("unknown provider")

# ---------------------------------------------------------------- iLoF skin
STYLE = """
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:ital,wght@0,400;0,600;0,700;1,400&family=Newsreader:ital,wght@1,300;1,400&family=Spline+Sans+Mono:wght@400;600&display=swap">
<style>
 :root{--bg:#101c31;--sf:#293b5a;--ink:#f4f7fc;--deep:#2f4a73;--soft:#93a9c9;--line:#33486b;
   --acc:#00d4ff;--accdark:#00a3d9;--softblue:#b8cdea;--softblue2:#152a4a;--bordeaux:#a34d6e;
   --tan:#9fb6d9;--cream2:#0e1930;--ok:#b8cdea;--okbg:#152a4a;--warnbg:#3d2f16;--failbg:#3d1c16}
 *{box-sizing:border-box}
 body{margin:0;color:var(--ink);font:15px/1.6 'Hanken Grotesk',system-ui,sans-serif;
   background:var(--bg) fixed;
   background-image:radial-gradient(900px 600px at 12% -10%,rgba(47,74,115,.5),transparent 60%),
     radial-gradient(800px 560px at 105% 8%,rgba(0,212,255,.06),transparent 55%)}
 body.lightbg{background:#eaf1fa;height:100vh;overflow:hidden;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='m'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23m)' opacity='0.045'/%3E%3C/svg%3E"),linear-gradient(rgba(47,74,115,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(47,74,115,.05) 1px,transparent 1px),linear-gradient(rgba(47,74,115,.085) 1px,transparent 1px),linear-gradient(90deg,rgba(47,74,115,.085) 1px,transparent 1px),radial-gradient(950px 640px at 12% -10%,rgba(0,163,217,.14),transparent 60%),radial-gradient(860px 600px at 104% 10%,rgba(47,74,115,.12),transparent 58%),radial-gradient(700px 520px at 50% 115%,rgba(0,212,255,.08),transparent 60%);background-size:auto,24px 24px,24px 24px,120px 120px,120px 120px,auto,auto,auto}
 body.lightbg .wrap{height:100%;box-sizing:border-box;padding:22px}
 body.lightbg .deskpanel{flex:1;min-height:0}
 body.lightbg .desk{flex:1;min-height:0;align-items:stretch}
 body.lightbg .rail{position:static;max-height:none;min-height:0}
 body.lightbg .pane2{min-height:0;overflow:visible}
 body.lightbg #pane-files{flex:1;min-height:0;display:flex;flex-direction:column}
 body.lightbg #fl-list{flex:1;min-height:0;overflow-y:auto}
 body.lightbg #fl-grid{flex:1;min-height:0;overflow-y:auto;align-content:start}
 body.lightbg #pane-runs{flex:1;min-height:0;align-items:stretch}
 body.lightbg #pane-runs .card{min-height:0;display:flex;flex-direction:column;overflow:visible}
 body.lightbg .runscroll{flex:1;min-height:0;overflow-y:auto}
 body.lightbg .stage2{height:auto;flex:1;min-height:0}
 @media(max-width:900px){body.lightbg{height:auto;overflow:auto}
   body.lightbg .pane2{overflow:visible}}
 a{color:var(--deep)} .serif{font-family:'Newsreader',serif} .mono{font-family:'Spline Sans Mono',monospace}
 nav{display:flex;align-items:center;gap:10px;padding:16px 26px;border-bottom:1px solid var(--line);background:var(--sf)}
 nav .dot{width:11px;height:11px;border-radius:50%;background:var(--acc)}
 nav b{font-size:16px;letter-spacing:-.01em} nav .crumb{color:var(--soft);font-size:14px}
 nav .right{margin-left:auto;display:flex;gap:14px;align-items:center;font-size:13.5px}
 .wrap{max-width:1060px;margin:0 auto;padding:34px 24px 80px;display:flex;flex-direction:column;gap:22px}
 h1{font-size:32px;margin:0;letter-spacing:-.02em;font-weight:700}
 h1 em{font-family:'Newsreader',serif;font-style:italic;font-weight:300;color:var(--acc)}
 h2{font-size:15px;font-weight:700;margin:0 0 12px;letter-spacing:-.01em}
 .eyebrow{font-family:'Spline Sans Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--tan)}
 .card{background:var(--sf);border:1px solid var(--line);border-radius:14px;padding:20px 22px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
 .folder{display:block;background:var(--sf);border:1px solid var(--line);border-radius:14px;padding:18px;
   text-decoration:none;color:var(--ink);transition:border-color .15s, transform .15s}
 .folder:hover{border-color:var(--acc);transform:translateY(-2px)}
 .folder .tab{width:44px;height:10px;background:var(--deep);border-radius:4px 4px 0 0;margin-bottom:-1px}
 .folder .body{background:var(--cream2);border-radius:0 8px 8px 8px;padding:12px 12px 10px;min-height:74px}
 .folder b{font-size:15.5px} .folder .meta{font-size:12.5px;color:var(--soft);margin-top:4px;line-height:1.5}
 .folder.new{border-style:dashed;color:var(--soft)} .folder.new:hover{color:var(--acc)}
 button,.btn{font:600 13.5px 'Hanken Grotesk';border-radius:9px;border:1px solid var(--line);
   padding:9px 16px;background:var(--sf);color:var(--ink);cursor:pointer;text-decoration:none;display:inline-block}
 button.primary,.btn.primary{background:var(--acc);border-color:var(--acc);color:#fff}
 button.primary:hover,.btn.primary:hover{background:var(--accdark)}
 button.ghost{border:none;background:none;color:var(--soft);padding:4px 6px}
 button.ghost:hover{color:var(--accdark)}
 input[type=text],input[type=password],select{font:14px 'Hanken Grotesk';border:1px solid var(--line);
   border-radius:9px;padding:9px 12px;background:var(--sf);color:var(--ink)}
 .chip{font-family:'Spline Sans Mono',monospace;font-size:10.5px;border-radius:99px;padding:2px 9px;white-space:nowrap}
 .chip.role{background:var(--softblue2);color:var(--softblue)}
 .chip.warn{background:var(--warnbg);color:#f2d9a7}
 .chip.skip{background:var(--cream2);color:var(--soft)}
 .chip.fail{background:var(--failbg);color:#f2b3a7}
 .chip.ok{background:var(--okbg);color:var(--softblue)}
 .filerow{display:flex;align-items:center;gap:10px;padding:7px 4px;border-bottom:1px solid var(--cream2);font-size:13.5px}
 .filerow:last-child{border-bottom:none}
 .filerow .name{font-family:'Spline Sans Mono',monospace;font-size:12.5px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .filerow .sz{color:var(--soft);font-size:12px}
 .drop{display:block;border:1.5px dashed var(--deep);border-radius:11px;background:var(--softblue2);
   padding:20px;text-align:center;cursor:pointer;color:var(--softblue);font-weight:600}
 .drop.drag{background:#1d3450} .drop input{display:none} .drop small{display:block;font-weight:400;color:var(--soft);margin-top:3px}
 .runrow{display:flex;align-items:center;gap:12px;padding:11px 4px;border-bottom:1px solid var(--cream2);font-size:13.5px}
 .runrow:last-child{border-bottom:none}
 .runrow .stamp{font-family:'Spline Sans Mono',monospace;font-size:12px;color:var(--soft)}
 .runrow .rec{font-weight:600}
 .hint{font-size:13px;color:var(--soft)}
 .two{display:grid;grid-template-columns:var(--runw,minmax(280px,340px)) 18px 1fr;gap:0;align-items:start}
 @media(max-width:860px){.two{grid-template-columns:1fr}.rowgrip{display:none}}
 pre.log{background:#0c1522;border:1px solid var(--line);color:#e8e2d9;border-radius:12px;padding:16px;font:12.5px 'Spline Sans Mono',monospace;overflow-x:auto;line-height:1.55;white-space:pre-wrap}
 .pb{height:6px;background:var(--line);border-radius:99px;overflow:hidden;margin:12px 0 4px}
 .pb i{display:block;height:100%;width:4%;background:linear-gradient(90deg,var(--acc),#7ae9ff);
   border-radius:99px;transition:width .5s ease;position:relative;overflow:hidden}
 .pb i::after{content:"";position:absolute;inset:0;
   background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);
   animation:pbs 1.1s linear infinite}
 .pb.done i::after,.pb.fail i::after{animation:none}
 .pb.fail i{background:#c12d00;width:100% !important}
 @keyframes pbs{from{transform:translateX(-100%)}to{transform:translateX(100%)}}
 @media(prefers-reduced-motion:reduce){.pb i::after{animation:none}}
 details.pillpop{position:relative;display:inline-block}
 details.pillpop summary{list-style:none;cursor:pointer}
 details.pillpop summary::-webkit-details-marker{display:none}
 details.pillpop .pop{position:absolute;right:0;top:26px;z-index:40;width:360px;background:var(--sf);
   border:1px solid var(--line);border-radius:11px;padding:13px 15px;box-shadow:0 14px 44px rgba(0,0,0,.18);
   font-size:12.5px;text-align:left}
 details.pillpop .pop b{display:block;margin-top:8px} details.pillpop .pop b:first-child{margin-top:0}
 details.pillpop .pop p{margin:2px 0 0;color:var(--soft)}
 pre.log .ok{color:#9fd0b8}pre.log .fail{color:#ff9d7a}pre.log .warn{color:#ecd9a0}
 .banner{background:var(--softblue2);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:11px;padding:13px 16px;font-size:13.5px}
 .tabsbar{display:flex;gap:6px;margin-left:auto}
 .tabbtn{font:600 13.5px 'Hanken Grotesk';border:1px solid var(--line);background:var(--sf);
   color:var(--softblue);border-radius:9px;padding:9px 20px;cursor:pointer}
 .tabbtn.on{background:var(--acc);color:#fff;border-color:var(--acc)}
 .modes{display:flex;flex-direction:column;gap:12px}
 .mode{display:flex;flex-direction:column;gap:5px;align-items:flex-start;text-align:left;cursor:pointer;
   background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:14px 18px;width:100%;
   color:var(--ink);transition:border-color .15s,transform .15s}
 .mode:hover{border-color:var(--acc);transform:translateY(-1px)}
 .mode b{font:700 14.5px 'Hanken Grotesk'} .mode span{font-size:12px;color:var(--soft);line-height:1.5}
 .mode.after{border-color:var(--deep)} .mode.after b{color:var(--acc)}
 .viewtog{display:flex;gap:6px}
 .viewtog button{font:600 12px 'Spline Sans Mono',monospace;border:1px solid var(--line);background:transparent;
   color:var(--soft);border-radius:7px;width:30px;height:26px;cursor:pointer;
   display:grid;place-items:center;line-height:1;padding:0}
 .viewtog button.on{background:var(--softblue2);color:var(--ink);border-color:var(--deep)}
 .fgridV{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
 .ftile{aspect-ratio:1;border:none;background:#14233c;border-radius:11px;position:relative;
   padding:12px 10px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;
   text-align:center;clip-path:polygon(0 0,calc(100% - 24px) 0,100% 24px,100% 100%,0 100%)}
 .ftile::after{content:"";position:absolute;top:0;right:0;width:24px;height:24px;
   background:#101b2f;clip-path:polygon(0 0,0 100%,100% 100%)}
 .ftile:hover::after{background:var(--deep)}
 .ftile .chip{white-space:normal;max-width:100%;line-height:1.6;border-radius:10px}
 .ftile .fmt{font:600 11px 'Spline Sans Mono',monospace;background:var(--softblue2);color:var(--softblue);
   border:1px solid var(--line);border-radius:8px;padding:8px 10px}
 .ftile .nm{font:10.5px 'Spline Sans Mono',monospace;max-width:100%;overflow:hidden;display:-webkit-box;
   -webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-all}
 .ftile form{position:absolute;top:5px;left:5px}
 .ftile .ghost{opacity:0} .ftile:hover .ghost{opacity:1}
 .rdel{opacity:0;border:none;background:none;color:var(--soft);cursor:pointer;padding:2px}
 .runrow:hover .rdel{opacity:1} .rdel:hover{color:var(--acc)} .rdel svg{width:14px;height:14px}
 /* chat */
 .chatbox{display:flex;flex-direction:column;gap:12px;max-width:820px;margin:0 auto}
 .msg{border-radius:14px;padding:12px 16px;max-width:88%;font-size:14.5px;white-space:pre-wrap}
 .msg.user{background:var(--deep);color:#fff;align-self:flex-end}
 .msg.ai{background:none;border:none;padding:12px 2px;max-width:100%;align-self:flex-start}
 .thinking{align-self:flex-start;padding:12px 2px;font-weight:600;font-size:13.5px;
   background:linear-gradient(90deg,var(--soft) 25%,var(--ink) 50%,var(--soft) 75%);
   background-size:200% 100%;-webkit-background-clip:text;background-clip:text;
   color:transparent;-webkit-text-fill-color:transparent;animation:think 1.3s linear infinite}
 @keyframes think{from{background-position:200% 0}to{background-position:0% 0}}
 @media(prefers-reduced-motion:reduce){.thinking{animation:none;color:var(--soft);
   -webkit-text-fill-color:var(--soft)}}
 .msg.ai .ov{background:var(--cream2);border:1px solid var(--line);border-radius:9px;padding:10px 12px;
   font:12.5px 'Spline Sans Mono',monospace;margin-top:8px;white-space:pre-wrap}
 .chatinput{display:flex;gap:10px;position:sticky;bottom:0;background:var(--bg);padding:12px 0}
 .chatinput input[type=text]{flex:1}
/* v1 desk layout - exercises rail + results stage (ported from market-runway) */
 .desk{display:grid;grid-template-columns:var(--railw,270px) 18px 1fr;gap:0;align-items:start}
 @media(max-width:900px){.desk{grid-template-columns:1fr}.colgrip{display:none}}
 .pane2{display:flex;flex-direction:column;gap:14px;min-width:0}
 .rail{background:var(--sf);border:1px solid var(--line);border-radius:14px;display:flex;flex-direction:column;
   box-shadow:0 18px 50px -30px rgba(0,0,0,.8);position:sticky;top:14px;max-height:calc(100vh - 90px)}
 .rail header{display:flex;align-items:center;gap:8px;padding:13px 14px;border-bottom:1px solid var(--line)}
 .rail header .mono{font-size:10px;letter-spacing:.18em;color:var(--tan)}
 .rail header button{margin-left:auto;font-weight:600;font-size:12px;background:var(--acc);color:#fff;
   border:none;border-radius:7px;padding:6px 10px;cursor:pointer}
 .rail header button:hover{background:var(--accdark)}
 .exlist{flex:1;overflow-y:auto;min-height:0;padding:10px;display:flex;flex-direction:column;gap:9px}
 .fol{display:block;text-decoration:none;color:var(--ink)}
 .fol .ftab{width:30px;height:8px;background:var(--deep);border-radius:4px 4px 0 0;margin-bottom:-1px}
 .fol .fbody{background:var(--cream2);border:1px solid var(--line);border-radius:0 8px 8px 8px;padding:9px 11px}
 .fol b{font-size:13.5px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .fol .meta{font-size:11px;color:var(--soft);margin-top:2px;line-height:1.5}
 .fol:hover .fbody,.fol.on .fbody{border-color:var(--acc)} .fol.on .ftab{background:var(--acc)}
 .railset{display:flex;align-items:center;gap:9px;padding:12px 14px;border:none;border-top:1px solid var(--line);
   background:none;color:var(--softblue);cursor:pointer;font-weight:600;font-size:13px;text-align:left;width:100%}
 .railset:hover{color:var(--ink)} .railset svg{width:15px;height:15px}
 .rail footer{padding:10px 14px;border-top:1px solid var(--line);font-family:'Spline Sans Mono',monospace;
   font-size:10px;letter-spacing:.1em;color:var(--soft)}
 .stage2{background:var(--sf);border:1px solid var(--line);border-radius:14px;padding:18px;display:flex;
   flex-direction:column;min-height:420px;height:calc(100vh - 295px)}
 .seg{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}
 .seg button{font-weight:600;font-size:12px;border:1px solid var(--line);background:transparent;
   color:var(--softblue);border-radius:99px;padding:7px 14px;cursor:pointer}
 .seg button.on{background:var(--softblue2);border-color:var(--deep);color:var(--ink)}
 .recnote{margin:0 0 10px;font-family:'Spline Sans Mono',monospace;font-size:11.5px;color:var(--soft);letter-spacing:.02em}
 .segbody{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column}
 .segbody iframe{flex:1;width:100%;border:1px solid var(--line);border-radius:10px;background:var(--sf);min-height:320px}
 .openfull{font-weight:600;font-size:12px;color:var(--softblue);text-decoration:none;align-self:flex-end;margin-bottom:8px}
 .openfull:hover{color:var(--acc)}
 .facts{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:1px;background:var(--line);
   border:1px solid var(--line);border-radius:12px;overflow:hidden}
 .facts div{background:var(--bg);padding:16px}
 .facts span{display:block;font-family:'Spline Sans Mono',monospace;font-size:10px;letter-spacing:.14em;
   color:var(--soft);text-transform:uppercase}
 .facts b{font-size:20px;letter-spacing:-.01em}
 .steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
 .steps>div{background:var(--cream2);border:1px solid var(--line);border-radius:12px;padding:14px}
 .steps span{font-family:'Spline Sans Mono',monospace;font-size:10px;letter-spacing:.14em;color:var(--tan)}
 .steps b{display:block;margin:4px 0 6px;font-size:14.5px}
 .steps p{margin:0;font-size:12.5px;color:var(--soft);line-height:1.5}
 .iband{display:flex;flex-direction:column;gap:3px;background:var(--softblue2);border:1px solid var(--deep);
   border-radius:12px;padding:13px 16px;margin-bottom:12px}
 .iband b{font-size:14.5px} .iband span{font-size:12px;color:var(--soft)}
 .folwrap{position:relative}
 .fmenu{position:absolute;top:16px;right:7px;width:24px;height:24px;border:none;background:none;cursor:pointer;
   padding:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;
   opacity:0;transition:opacity .15s}
 .folwrap:hover .fmenu,.folwrap.open .fmenu{opacity:1}
 .fmenu span{display:block;width:13px;height:1.6px;background:var(--soft);border-radius:2px;transition:transform .18s}
 .fmenu:hover span{background:var(--ink)}
 .folwrap.open .fmenu span:first-child{transform:translateY(2.8px) rotate(45deg)}
 .folwrap.open .fmenu span:last-child{transform:translateY(-2.8px) rotate(-45deg)}
 .fdrop{display:none;position:absolute;right:6px;top:40px;z-index:30;background:var(--sf);
   border:1px solid var(--line);border-radius:10px;overflow:hidden;min-width:124px;
   box-shadow:0 14px 34px rgba(0,0,0,.55)}
 .folwrap.open .fdrop{display:block}
 .fdrop button{display:block;width:100%;text-align:left;border:none;background:none;color:var(--ink);
   font-size:12.5px;font-weight:600;padding:9px 13px;cursor:pointer;border-radius:0}
 .fdrop button:hover{background:var(--softblue2)}
 .fdrop button.danger{color:#ff6d5a}
 .addrow{display:flex;align-items:center;justify-content:center;border:1.5px dashed var(--line);
   border-radius:9px;padding:10px;color:var(--soft);cursor:pointer;margin-top:8px;
   font-size:17px;font-weight:600;line-height:1}
 .addrow:hover{color:var(--acc);border-color:var(--acc)}
 .ftile.addtile{border:1.5px dashed var(--line);color:var(--soft);cursor:pointer;
   font-size:26px;font-weight:600;line-height:1;background:transparent;clip-path:none}
 .ftile.addtile::after{display:none}
 .ftile.addtile:hover{color:var(--acc);border-color:var(--acc)}
 .xtitle{text-transform:uppercase;letter-spacing:-.02em;font-size:clamp(24px,3vw,34px);font-weight:700}
 .xtitle em{font-family:'Newsreader',serif;font-style:italic;font-weight:300;
   text-transform:lowercase;color:var(--acc)}
 .wrap.fluid{max-width:none;padding:22px 22px 60px}
 .deskpanel{position:relative;background:rgba(24,39,64,.96);border:1px solid var(--line);border-radius:16px;
   padding:16px 18px 18px;display:flex;flex-direction:column;gap:14px;
   box-shadow:0 24px 60px -35px rgba(0,0,0,.8);-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px)}
 nav.innav{position:relative;background:none;border-bottom:none;padding:2px 4px 8px;margin:0}
 .xtitle{cursor:text;border-bottom:1.5px dashed transparent}
 .xtitle:hover{border-bottom-color:var(--deep)}
 input.titled{font:700 28px 'Hanken Grotesk';text-transform:uppercase;letter-spacing:-.02em;
   background:var(--sf);color:var(--ink);border:1px solid var(--deep);border-radius:8px;
   padding:2px 10px;min-width:0;max-width:48vw}
 .homescroll{flex:1;min-height:0;overflow-y:auto;display:flex;flex-direction:column;gap:22px}
 body.lightbg .chatbox{flex:1;min-height:0;width:100%;max-width:860px;margin:0 auto;display:flex;flex-direction:column}
 body.lightbg #msgs{flex:1;min-height:0;overflow-y:auto;padding-right:4px}
 body.lightbg .chatinput{position:static;background:none;padding:6px 0 0}
 body.lightbg pre.log{flex:1;min-height:0;overflow:auto;margin:0}
 .msg.ai{white-space:normal}
 .msg.ai p{margin:0 0 10px} .msg.ai p:last-child{margin-bottom:0}
 .msg.ai ul,.msg.ai ol{margin:0 0 10px;padding-left:22px} .msg.ai li{margin:2px 0}
 .msg.ai code{font-family:'Spline Sans Mono',monospace;font-size:12.5px;background:var(--cream2);
   border:1px solid var(--line);border-radius:5px;padding:1px 5px}
 .msg.ai pre{background:var(--cream2);border:1px solid var(--line);border-radius:9px;
   padding:10px 12px;overflow-x:auto;margin:0 0 10px}
 .msg.ai pre code{background:none;border:none;padding:0}
 .msg.ai h3{margin:0 0 8px;font-size:15px}
 .railcol{display:flex;flex-direction:column;gap:14px;min-height:0}
 .railcol .rail{flex:1;min-height:0}
 .railchat{background:var(--sf);border:1px solid var(--line);border-radius:14px;display:flex;
   flex-direction:column;flex:0 0 auto;height:280px;min-height:0;overflow:hidden;
   box-shadow:0 18px 50px -30px rgba(0,0,0,.8);transition:height .35s ease}
 .railchat.dragging{transition:none}
 .rcgrip{flex:0 0 10px;cursor:ns-resize;touch-action:none}
 .rcgrip::after{content:"";display:block;width:38px;height:3px;border-radius:2px;
   background:var(--line);margin:4px auto 0}
 .rcfbtn{margin-left:auto;border:none;background:none;cursor:pointer;padding:0;
   width:24px;height:24px;display:flex;flex-direction:column;align-items:center;
   justify-content:center;gap:4px}
 .rcfbtn span{display:block;width:13px;height:1.6px;background:var(--soft);border-radius:2px;
   transition:transform .18s}
 .rcfbtn:hover span{background:var(--ink)}
 .railchat.fopen .rcfbtn span:first-child{transform:translateY(2.8px) rotate(45deg)}
 .railchat.fopen .rcfbtn span:last-child{transform:translateY(-2.8px) rotate(-45deg)}
 .rchead{padding:10px 14px 6px;font-family:'Spline Sans Mono',monospace;font-size:9.5px;
   letter-spacing:.14em;color:var(--tan);text-transform:uppercase;display:flex;align-items:center}
 .rcmsgs{flex:1;min-height:0;overflow-y:auto;padding:4px 14px 8px;display:flex;flex-direction:column;
   gap:8px;font-size:12.5px;line-height:1.5}
 .rcmsgs .u{align-self:flex-end;background:var(--deep);color:#fff;border-radius:10px;padding:6px 10px;max-width:92%}
 .rcmsgs .a{align-self:flex-start;max-width:100%}
 .rcmsgs .a code{font-family:'Spline Sans Mono',monospace;font-size:11.5px;background:var(--cream2);
   border:1px solid var(--line);border-radius:4px;padding:0 4px}
 .rcin{display:flex;gap:6px;padding:10px 12px;border-top:1px solid var(--line)}
 .rcin input{flex:1;font-size:12.5px;min-width:0}
 /* light inner windows on the dark shell: tokens flip inside these containers */
 .card,.rail,.railchat,.stage2,dialog{
   --sf:#ffffff;--bg:#f7fafd;--ink:#17263f;--soft:#5c7392;--line:#d4deec;
   --cream2:#e6edf6;--softblue:#3a5a80;--softblue2:#e2eaf5;--tan:#6b81a3;
   --acc:#0090c8;--accdark:#006e99;--okbg:#ddefe3;--warnbg:#f6ead9;--failbg:#f8e3dc;
   background:rgba(255,255,255,.55);color:var(--ink);
   -webkit-backdrop-filter:blur(20px) saturate(1.3);backdrop-filter:blur(20px) saturate(1.3)}
 dialog{background:#ffffff}
 .card .chip.warn,.rail .chip.warn,.stage2 .chip.warn,.railchat .chip.warn{color:#7a5510}
 .card .chip.fail,.rail .chip.fail,.stage2 .chip.fail,.railchat .chip.fail{color:#b3341c}
 .card .ftile{background:#ffffff}
 .card .ftile::after{background:#dbe4f0}
 .card .ftile:hover::after{background:#c7d4e6}
 .railchat .rcmsgs .u{color:#fff}
 .railchat{position:relative}
 .rchead{cursor:pointer;user-select:none}
 .rcws{margin-left:6px;color:var(--soft);letter-spacing:0;text-transform:none;
   overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
 .railchat.closed .rchead{justify-content:center;height:100%;padding:0 14px;align-items:center}
 .railchat.closed .rcws,.railchat.closed .rcfbtn,.railchat.closed .rcgrip,
 .railchat.closed .rcmsgs,.railchat.closed .rcin,.railchat.closed .rcfilter{display:none}
 .rcfilter{position:absolute;top:38px;left:8px;right:8px;z-index:40;background:var(--sf);
   border:1px solid var(--line);border-radius:10px;max-height:230px;overflow-y:auto;display:none;
   box-shadow:0 16px 40px rgba(16,28,49,.25)}
 .rcfilter.open{display:block}
 .rcfhead{padding:8px 12px 3px;font-family:'Spline Sans Mono',monospace;font-size:9.5px;
   letter-spacing:.14em;color:var(--tan);text-transform:uppercase}
 .rcfrow{display:flex;align-items:center;gap:6px;padding:7px 12px;font-size:12.5px;
   cursor:pointer;color:var(--ink);text-decoration:none}
 .rcfrow:hover,.rcfrow.on{background:var(--softblue2)}
 .rcfrow .nm2{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .rcren{margin-left:auto;border:none;background:none;color:var(--soft);cursor:pointer;
   padding:2px;opacity:0;display:grid;place-items:center}
 .rcfrow:hover .rcren{opacity:1} .rcren:hover{color:var(--ink)}
 /* inline report expansion in the Runs window */
 .two{transition:grid-template-columns .35s ease}
 .two > form.card{min-width:0;transition:opacity .3s ease,padding .35s ease}
 #pane-runs.wide{grid-template-columns:0fr 0px 1fr}
 #pane-runs.wide .rowgrip{pointer-events:none}
 #pane-runs.wide > form.card{opacity:0;padding:0;border-width:0;overflow:hidden}
 .repwrap{flex:1;min-height:0;display:flex;flex-direction:column;gap:10px}
 .repwrap iframe{flex:1;width:100%;border:none;border-radius:10px;
   background:transparent;min-height:300px}
 /* glass texture on the backdrop slab */
 .deskpanel::before{content:"";position:absolute;inset:0;border-radius:16px;pointer-events:none;
   opacity:.10;mix-blend-mode:overlay;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
 .deskpanel{background-image:radial-gradient(720px 420px at 16% -4%,rgba(0,212,255,.11),transparent 60%),radial-gradient(640px 420px at 96% 104%,rgba(47,74,115,.5),transparent 65%),linear-gradient(165deg,rgba(255,255,255,.05),transparent 45%)}
 .brand{text-decoration:none;color:var(--ink);font-weight:700;font-size:13px;letter-spacing:.09em}
 .brand em{font-family:'Newsreader',serif;font-style:italic;font-weight:300;letter-spacing:0;
   font-size:15.5px;color:var(--acc);margin-left:7px}
 .brand:hover em{color:var(--softblue)}
 .colgrip,.rowgrip{cursor:col-resize;touch-action:none;position:relative}
 .colgrip::after,.rowgrip::after{content:"";position:absolute;top:0;bottom:0;left:50%;width:2.5px;
   transform:translateX(-50%);border-radius:2px;background:transparent;transition:background .15s}
 .colgrip:hover::after,.colgrip.dragging::after,
 .rowgrip:hover::after,.rowgrip.dragging::after{background:rgba(255,255,255,.28)}
 .folwrap.lift{opacity:.45}
 .folwrap[draggable=true]{cursor:grab}
 .pdfdl{display:grid;place-items:center;width:30px;height:30px;border:1px solid var(--line);
   border-radius:8px;color:var(--soft)}
 .pdfdl:hover{color:var(--acc);border-color:var(--acc)}
 /* glass edges: a light-refracting gradient rim instead of a flat gray border */
 .card,.rail,.railchat,.stage2{position:relative;border-color:rgba(255,255,255,.38);
   box-shadow:inset 0 1px 0 rgba(255,255,255,.6),inset 0 -1px 0 rgba(255,255,255,.08),
   0 14px 34px -18px rgba(16,28,49,.45)}
 .card::after,.rail::after,.railchat::after,.stage2::after{content:"";position:absolute;inset:-1px;
   border-radius:inherit;padding:1px;pointer-events:none;
   background:linear-gradient(160deg,rgba(255,255,255,.85),rgba(255,255,255,.16) 34%,
     rgba(255,255,255,.05) 60%,rgba(255,255,255,.42));
   -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
   -webkit-mask-composite:xor;
   mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude}
 .deskpanel{border-color:rgba(255,255,255,.14)}
 .deskpanel::after{content:"";position:absolute;inset:-1px;border-radius:inherit;padding:1px;
   pointer-events:none;background:linear-gradient(165deg,rgba(255,255,255,.5),
     rgba(255,255,255,.08) 30%,rgba(0,212,255,.10) 70%,rgba(255,255,255,.22));
   -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
   -webkit-mask-composite:xor;
   mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude}
 /* experiment: outer slab hidden: windows float directly on the white ground */
 .deskpanel{background:none;background-image:none;border-color:transparent;box-shadow:none;
   -webkit-backdrop-filter:none;backdrop-filter:none;
   --sf:#ffffff;--bg:#f7fafd;--ink:#17263f;--soft:#5c7392;--line:#d4deec;--cream2:#e6edf6;
   --softblue:#3a5a80;--softblue2:#e2eaf5;--tan:#6b81a3;--acc:#0090c8;--accdark:#006e99;
   --okbg:#ddefe3;--warnbg:#f6ead9;--failbg:#f8e3dc;color:var(--ink)}
 .deskpanel::before,.deskpanel::after{display:none}
 .card,.rail,.railchat,.stage2{border-color:rgba(23,38,63,.10)}
 .segbody iframe[data-autoh]{min-height:0;border:none;background:transparent;border-radius:0}
 .eyebtn{margin-left:auto;display:grid;place-items:center;width:24px;height:24px;
   color:var(--soft);border-radius:6px}
 .eyebtn:hover{color:var(--ink)}
 .rail header button{margin-left:8px}
 .headbar{padding:10px 18px}
 .headbar h1{font-size:clamp(20px,2.2vw,28px)}
 </style>"""


def nav(crumbs=""):
    key = sk()["value"]
    prov = PROVIDERS.get(sk().get("provider") or "", {}).get("label", "key")
    key_chip = (f'<span class="chip ok">{prov} key ·…{html.escape(key[-4:])}</span>'
                '<form method="post" action="/clearkey" style="display:inline">'
                '<button class="ghost" title="Forget the API key">clear</button></form>'
                if key else
                '<button class="chip skip" id="addkey" style="cursor:pointer;border:none" '
                'onclick="navKey()">no API key · add</button>')
    key_chip += (
        '<div id="navkeypanel" style="display:none;position:absolute;top:52px;right:22px;z-index:50;'
        'background:var(--sf);border:1px solid var(--line);border-radius:12px;padding:14px;width:300px;'
        'box-shadow:0 12px 40px rgba(0,0,0,.18)">'
        '<input type="password" id="navkeyin" placeholder="sk-ant-… / sk-… / AIza…" autocomplete="off" '
        'style="width:100%;font-family:monospace;font-size:12.5px" onchange="navKeyCheck(this)">'
        '<div class="hint" id="navkeystat" style="min-height:15px;margin-top:6px">'
        'validated live; kept for your session (30 days)</div></div>'
        '<script>function navKey(){var p=document.getElementById("navkeypanel");'
        'p.style.display=p.style.display==="none"?"block":"none";'
        'if(p.style.display==="block")document.getElementById("navkeyin").focus();}'
        'async function navKeyCheck(el){var st=document.getElementById("navkeystat");'
        'var v=el.value.trim();if(!v)return;st.textContent="checking…";st.style.color="";'
        'const r=await fetch("/keycheck",{method:"POST",headers:{"Content-Type":"application/json"},'
        'body:JSON.stringify({key:v})});const j=await r.json();'
        'el.style.borderColor=j.ok?"#2F7D4F":"#c12d00";'
        'st.style.color=j.ok?"#2F7D4F":"#c12d00";st.textContent=j.detail;'
        'if(j.ok)setTimeout(function(){location.reload()},900);}'
        '</script>')
    return (f'<nav>'
            '<a href="/" class="brand">MARKET RUNWAY<em>Model</em></a>'
            f'<span class="right">{key_chip}</span></nav>')


def page(title, body, crumbs="", rail=None, shell=False):
    if shell:
        innav = nav(crumbs).replace("<nav>", '<nav class="innav">', 1)
        body = (f'<section class="deskpanel">{innav}'
                f'<div class="homescroll">{body}</div></section>')
        return (f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
                f'<title>{html.escape(title)}</title>{STYLE}<body class="lightbg">'
                f'<div class="wrap fluid">{body}</div></body>')
    if rail:
        innav = nav(crumbs).replace("<nav>", '<nav class="innav">', 1)
        body = (f'<section class="deskpanel">{innav}'
                f'<div class="desk">{rail}'
                '<div class="colgrip" id="colgrip" title="Drag to resize"></div>'
                f'<div class="pane2">{body}</div></div></section>')
        return (f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
                f'<title>{html.escape(title)}</title>{STYLE}<body class="lightbg">'
                f'<div class="wrap fluid">{body}</div></body>')
    return (f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
            f'<title>{html.escape(title)}</title>{STYLE}{nav(crumbs)}<div class="wrap">{body}</div>')


def ws_summary(ws: Path) -> dict:
    files = [p for p in (ws / "raw").glob("*") if p.is_file() and not p.name.startswith(".")] if (ws / "raw").exists() else []
    runs = list_runs(ws)
    rec, markets = None, []
    lr = latest_run(ws)
    if lr and (lr / "state.json").exists():
        try:
            st = json.load(open(lr / "state.json"))
            rec = st["conclusion"]["recommendation"]
            markets = st["conclusion"]["ranking"] or list(st["dataset"].keys())
        except Exception:  # noqa: BLE001
            pass
    return {"files": len(files), "runs": len(runs), "rec": rec, "markets": markets}


RAIL_JS = ('<script>document.querySelectorAll(".fmenu").forEach(function(b){'
           'b.onclick=function(e){e.preventDefault();e.stopPropagation();'
           'var w=b.closest(".folwrap");'
           'document.querySelectorAll(".folwrap.open").forEach(function(o){if(o!==w)o.classList.remove("open")});'
           'w.classList.toggle("open")}});'
           'document.addEventListener("click",function(e){'
           'if(!e.target.closest(".folwrap"))document.querySelectorAll(".folwrap.open").forEach('
           'function(o){o.classList.remove("open")})});'
           "var DRAGW=null;"
           "document.querySelectorAll('.folwrap').forEach(function(w){"
           "w.setAttribute('draggable','true');"
           "var lk=w.querySelector('a.fol');if(lk)lk.setAttribute('draggable','false');"
           "w.addEventListener('dragstart',function(e){DRAGW=w;w.classList.add('lift');"
           "e.dataTransfer.effectAllowed='move';try{e.dataTransfer.setData('text/plain',w.dataset.ws)}catch(x){}});"
           "w.addEventListener('dragend',function(){w.classList.remove('lift');"
           "if(DRAGW){DRAGW=null;"
           "var names=[].map.call(document.querySelectorAll('.folwrap'),function(x){return x.dataset.ws});"
           "fetch('/reorder',{method:'POST',headers:{'Content-Type':'application/json'},"
           "body:JSON.stringify({order:names})})}});"
           "w.addEventListener('dragover',function(e){if(!DRAGW||DRAGW===w)return;e.preventDefault();"
           "var r=w.getBoundingClientRect();"
           "w.parentNode.insertBefore(DRAGW,e.clientY<r.top+r.height/2?w:w.nextSibling)});});"
           "var exl=document.querySelector('.exlist');"
           "if(exl)exl.addEventListener('dragover',function(e){if(DRAGW)e.preventDefault()});"
           "document.addEventListener('DOMContentLoaded',function(){"
           "var cg=document.getElementById('colgrip');"
           "if(cg){var dk=cg.parentElement;"
           "try{var sw=parseInt(localStorage.getItem('mr-railw'));"
           "if(sw)dk.style.setProperty('--railw',sw+'px')}catch(e){}"
           "cg.addEventListener('pointerdown',function(e){e.preventDefault();"
           "var x0=e.clientX,w0=dk.querySelector('.railcol').offsetWidth;cg.classList.add('dragging');"
           "function mv(ev){dk.style.setProperty('--railw',"
           "Math.max(200,Math.min(430,w0+(ev.clientX-x0)))+'px')}"
           "function up(){cg.classList.remove('dragging');"
           "try{localStorage.setItem('mr-railw',dk.querySelector('.railcol').offsetWidth)}catch(e){}"
           "window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up)}"
           "window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up)});}"
           "});"
           '</script>')

RAILCHAT_JS = ('<script>(function(){'
    "var q=document.getElementById('rcq'),ms=document.getElementById('rcmsgs');if(!q)return;"
    "var rc=document.querySelector('.railchat'),gp=document.querySelector('.rcgrip'),"
    "hd=document.getElementById('rchead'),fb=document.getElementById('rcfbtn'),"
    "fp=document.getElementById('rcfilter'),lbl=document.getElementById('rcthread');"
    "var RUNC='__RUN__'||null;var store=null;"
    "try{store=JSON.parse(localStorage.getItem('rcconv-__WS__'))}catch(e){}"
    "if(!store||!store.threads)store={threads:{general:{name:'General',msgs:[]}}};"
    "try{var oh=JSON.parse(localStorage.getItem('rchist-__WS__'));"
    "if(oh&&oh.length){store.threads.general.msgs=oh;localStorage.removeItem('rchist-__WS__')}}catch(e){}"
    "function save(){try{localStorage.setItem('rcconv-__WS__',JSON.stringify(store))}catch(e){}}"
    "function th(k){if(!store.threads[k]){"
    "var d=document.querySelector('.rcfrow[data-thread=\"'+k+'\"]');"
    "store.threads[k]={name:(d&&d.dataset.def)||(k==='general'?'General':'Run '+k),msgs:[]}}"
    "return store.threads[k]}"
    "var cur=RUNC?RUNC:'general';th(cur);"
    "function fmt(s){var d=document.createElement('div');d.textContent=s;var h=d.innerHTML;"
    "return h.replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>')"
    ".replace(/`([^`\\n]+)`/g,'<code>$1</code>')}"
    "function add(cls,htm){var d=document.createElement('div');d.className=cls;d.innerHTML=htm;"
    "ms.appendChild(d);ms.scrollTop=ms.scrollHeight;return d}"
    "function paint(){ms.innerHTML='';var t=th(cur);lbl.textContent='· '+t.name;"
    "document.querySelectorAll('.rcfrow[data-thread]').forEach(function(r){"
    "r.classList.toggle('on',r.dataset.thread===cur);"
    "var s=store.threads[r.dataset.thread];"
    "if(s&&s.name)r.querySelector('.nm2').textContent=s.name});"
    "if(!t.msgs.length)add('a','<span style=\"color:var(--soft)\">'+(cur==='general'?"
    "'General conversation for this exercise.':'New conversation about this report.')+'</span>');"
    "t.msgs.forEach(function(m){add(m.role==='user'?'u':'a',fmt(m.content))})}"
    "paint();"
    "window.rcSend=async function(){var t=q.value.trim();if(!t)return;q.value='';"
    "var kk=t.replace(/\\s+/g,'');"
    "if(/^(sk-|AIza)[A-Za-z0-9_-]{15,}$/.test(kk)){add('u','key ····'+kk.slice(-4));"
    "var kth=document.createElement('div');kth.className='thinking';kth.textContent='Checking key';"
    "ms.appendChild(kth);ms.scrollTop=ms.scrollHeight;"
    "fetch('/keycheck',{method:'POST',headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({key:kk})}).then(function(r){return r.json()}).then(function(j){"
    "kth.remove();var msg=(j.ok?'Key saved: ':'⚠ ')+j.detail;add('a',fmt(msg));"
    "if(j.ok){th(cur).msgs.push({role:'assistant',content:msg});save();"
    "setTimeout(function(){location.reload()},900)}});return}"
    "var T=th(cur);add('u',fmt(t));T.msgs.push({role:'user',content:t});save();"
    "var tk=document.createElement('div');tk.className='thinking';tk.textContent='Thinking';"
    "ms.appendChild(tk);ms.scrollTop=ms.scrollHeight;"
    "try{var r=await fetch('/w/__WS__/chat/send',{method:'POST',"
    "headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({messages:T.msgs.slice(-20),"
    "run:cur!=='general'?cur:null,context:'__VIEW__ · conversation: '+T.name})});"
    "var j=await r.json();tk.remove();"
    "if(j.error){add('a','⚠ '+fmt(j.error));return}"
    "add('a',fmt(j.text));T.msgs.push({role:'assistant',content:j.text});save();}"
    "catch(e){tk.remove();add('a','⚠ network error - try again')}};"
    "q.addEventListener('keydown',function(e){if(e.key==='Enter')rcSend()});"
    "var svH=parseInt(localStorage.getItem('rch-__WS__'))||280;"
    "var cl=localStorage.getItem('rc-__WS__')==='1';"
    "function setH(h){rc.style.height=h+'px'}"
    "rc.classList.toggle('closed',cl);setH(cl?40:svH);"
    "hd.addEventListener('click',function(e){if(e.target.closest('.rcfbtn'))return;"
    "cl=!cl;rc.classList.toggle('closed',cl);setH(cl?40:svH);"
    "fp.classList.remove('open');rc.classList.remove('fopen');"
    "try{localStorage.setItem('rc-__WS__',cl?'1':'0')}catch(e){}});"
    "fb.addEventListener('click',function(e){e.stopPropagation();"
    "fp.classList.toggle('open');"
    "rc.classList.toggle('fopen',fp.classList.contains('open'));paint()});"
    "document.addEventListener('click',function(e){"
    "if(!e.target.closest('.railchat')){fp.classList.remove('open');rc.classList.remove('fopen')}});"
    "fp.addEventListener('click',function(e){"
    "var rn=e.target.closest('.rcren');"
    "if(rn){e.stopPropagation();var k=rn.dataset.ren;var t0=th(k);"
    "var nn=prompt('Name this conversation',t0.name);"
    "if(nn){t0.name=nn.trim()||t0.name;save();paint()}return}"
    "var row=e.target.closest('.rcfrow[data-thread]');"
    "if(row){cur=row.dataset.thread;th(cur);fp.classList.remove('open');"
    "rc.classList.remove('fopen');paint()}});"
    "if(gp){gp.addEventListener('pointerdown',function(e){if(cl)return;e.preventDefault();"
    "var y0=e.clientY,h0=rc.offsetHeight;rc.classList.add('dragging');"
    "function mv(ev){setH(Math.max(120,Math.min(window.innerHeight*0.75,h0+(y0-ev.clientY))))}"
    "function up(){rc.classList.remove('dragging');svH=rc.offsetHeight;"
    "try{localStorage.setItem('rch-__WS__',svH)}catch(e){}"
    "window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up)}"
    "window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up)});}"
    '})();</script>')

NEWWS_DLG = (
    '<dialog id="newws" style="border:1px solid var(--line);border-radius:14px;padding:22px;max-width:380px">'
    '<form method="post" action="/new" style="display:flex;flex-direction:column;gap:12px">'
    '<h2 style="margin:0">New exercise</h2>'
    '<input type="text" name="name" placeholder="e.g. Spain 2027" required>'
    '<div style="display:flex;gap:10px;justify-content:flex-end">'
    '<button type="button" onclick="this.closest(\'dialog\').close()">Cancel</button>'
    '<button class="primary">Create</button></div></form></dialog>')


def fancy_title(name: str) -> str:
    """Case-driven: UPPERCASE tokens render dark caps; lowercase tokens serif italic."""
    parts = [p for p in re.split(r"[-_ ]+", name.strip()) if p]
    out, buf, mode = [], [], None

    def flush():
        if buf:
            seg = html.escape(" ".join(buf))
            out.append(seg if mode == "up" else f"<em>{seg}</em>")

    for tok in parts:
        m = "low" if any(c.islower() for c in tok) else "up"
        if m != mode:
            flush()
            buf, mode = [], m
        buf.append(tok)
    flush()
    return " ".join(out) or html.escape(name)


def rail_html(current: str, run: str = None, view: str = "") -> str:
    """The v1 exercises rail: every workspace as a little folder."""
    wss = list_workspaces()
    items = ""
    for ws in wss:
        s = ws_summary(ws)
        meta = f'{s["files"]} docs · {s["runs"]} run(s)'
        if s["rec"]:
            meta += f' · <span style="color:var(--acc)">{html.escape(s["rec"])}</span>'
        items += (
            f'<div class="folwrap" data-ws="{ws.name}"><a class="fol{" on" if ws.name == current else ""}" href="/w/{ws.name}">'
            f'<div class="ftab"></div><div class="fbody"><b>{ws.name}</b>'
            f'<div class="meta">{meta}</div></div></a>'
            f'<button class="fmenu" aria-label="exercise menu"><span></span><span></span></button>'
            f'<div class="fdrop">'
            f'<form method="post" action="/w/{ws.name}/duplicate"><button>Duplicate</button></form>'
            f'<form method="post" action="/w/{ws.name}/delete" '
            f'onsubmit="return confirm(\'Delete {ws.name} and everything in it?\')">'
            f'<button class="danger">Delete</button></form></div></div>')
    PEN = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
           'stroke-linecap="round" stroke-linejoin="round" style="width:12px;height:12px">'
           '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>')
    filter_rows = ""
    for w2 in wss:
        filter_rows += f'<div class="rcfhead">{w2.name}</div>'
        if w2.name == current:
            filter_rows += ('<div class="rcfrow" data-thread="general" data-def="General">'
                            '<span class="nm2">General</span>'
                            f'<button class="rcren" data-ren="general" title="Rename">{PEN}</button></div>')
            for r2 in list_runs(w2):
                ts2 = datetime.strptime(r2.name, "%Y%m%d-%H%M%S").strftime("%d %b · %H:%M")
                filter_rows += (f'<div class="rcfrow" data-thread="{r2.name}" data-def="Run {ts2}">'
                                f'<span class="nm2">Run {ts2}</span>'
                                f'<button class="rcren" data-ren="{r2.name}" title="Rename">{PEN}</button></div>')
        else:
            filter_rows += f'<a class="rcfrow" href="/w/{w2.name}">General</a>'
            for r2 in list_runs(w2):
                ts2 = datetime.strptime(r2.name, "%Y%m%d-%H%M%S").strftime("%d %b · %H:%M")
                filter_rows += f'<a class="rcfrow" href="/w/{w2.name}/results/{r2.name}">Run {ts2}</a>'
    return ('<div class="railcol">'
            f'<aside class="rail"><header><span class="mono">EXERCISES</span>'
            f'<a class="eyebtn" href="/" title="Overview - all exercises">{EYE}</a>'
            '<button onclick="document.getElementById(\'newws\').showModal()">+ New</button></header>'
            f'<div class="exlist">{items}</div></aside>'
            f'<div class="railchat"><div class="rcgrip" title="Drag to resize"></div>'
            f'<div class="rchead" id="rchead" title="Click to open or close">ASK THE DATA{ROBOT}'
            '<span class="rcws" id="rcthread"></span>'
            '<button class="rcfbtn" id="rcfbtn" title="Conversations" aria-label="Conversations">'
            '<span></span><span></span>'
            "</button></div>"
            f'<div class="rcfilter" id="rcfilter">{filter_rows}</div>'
            '<div class="rcmsgs" id="rcmsgs"></div>'
            '<div class="rcin"><input type="text" id="rcq" placeholder="Type" autocomplete="off" '
            'style="padding:7px 11px;font-size:12.5px">'
            '<button class="primary" style="font-size:12px;padding:6px 12px" onclick="rcSend()">Ask</button>'
            '</div></div></div>'
            + NEWWS_DLG + RAIL_JS
            + RAILCHAT_JS.replace("__WS__", current).replace("__RUN__", run or "")
                         .replace("__VIEW__", view.replace("'", "")))


# ---------------------------------------------------------------- home
@app.get("/")
def home():
    cards = ""
    for ws in list_workspaces():
        s = ws_summary(ws)
        rec = f'→ recommends <b style="color:var(--acc)">{s["rec"]}</b>' if s["rec"] else "not run yet"
        cards += (f'<a class="folder" href="/w/{ws.name}"><div class="tab"></div><div class="body">'
                  f'<b>{ws.name}</b><div class="meta">{s["files"]} documents · {s["runs"]} run(s)<br>{rec}</div>'
                  f'</div></a>')
    cards += ('<a class="folder new" href="#" onclick="document.getElementById(\'newws\').showModal();return false">'
              '<div class="tab" style="background:var(--line)"></div><div class="body" style="display:grid;place-content:center">'
              '<b>+ New search</b><div class="meta">start a market assessment</div></div></a>')
    body = f"""
    <section class="card" style="display:flex;flex-direction:column;gap:22px;flex:1;min-height:0">
    <div><div class="eyebrow">Market Runway · the market-entry desk</div>
    <h1>Every market, <em>one folder away.</em></h1>
    <p class="hint" style="max-width:60ch">Drop a market pack into a workspace, run the seven-stage pipeline,
    and get a validated dataset, a ranked recommendation and a full evidence report. Deterministic first;
    AI only where it earns its place.</p></div>
    <div class="grid" style="overflow-y:auto;min-height:0;flex:1;align-content:start">{cards}</div>
    </section>
    <dialog id="newws" style="border:1px solid var(--line);border-radius:14px;padding:22px;max-width:380px">
      <form method="post" action="/new" style="display:flex;flex-direction:column;gap:12px">
        <h2 style="margin:0">New workspace</h2>
        <input type="text" name="name" placeholder="e.g. Spain 2027" required autofocus>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button type="button" onclick="this.closest('dialog').close()">Cancel</button>
          <button class="primary">Create</button></div>
      </form></dialog>"""
    return page("Market Runway · workspaces", body, shell=True)


@app.post("/new")
def new_ws():
    name = slugify(request.form.get("name", ""))
    if name:
        (ws_dir(name) / "raw").mkdir(parents=True, exist_ok=True)
        (ws_dir(name) / "runs").mkdir(exist_ok=True)
        return redirect(f"/w/{name}")
    return redirect("/")


# ---------------------------------------------------------------- workspace
def _manifest_roles(ws: Path) -> dict:
    """{filename: (chip_label, chip_class)}"""
    man = build_manifest(ws)
    roles = {}
    for k, v in man["company_docs"].items():
        roles[v["file"]] = (k.replace("_", " "), "role")
    for mk, m in man["markets"].items():
        for k, v in m.items():
            roles[v["file"]] = (f"{mk} · {k.replace('_', ' ')}", "role")
    for k, v in man["shared_docs"].items():
        roles[v["file"]] = (k.replace("_", " "), "role")
    for f in man["skipped"]:
        roles[f] = ("reference - not analysed", "skip")
    for f in man["unassigned"]:
        roles[f] = ("unassigned - not analysed", "warn")
    return roles


@app.get("/w/<ws_name>")
def workspace(ws_name):
    ws = ws_dir(ws_name)
    if not ws.exists():
        return redirect("/")
    roles = _manifest_roles(ws)
    rows, tiles = "", ""
    for p in sorted((ws / "raw").glob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        label, cls = roles.get(p.name, ("unassigned", "warn"))
        delform = (f'<form method="post" action="/w/{ws.name}/files/delete" '
                   f'onsubmit="return confirm(\'Delete {html.escape(p.name)}?\')">'
                   f'<input type="hidden" name="f" value="{html.escape(p.name)}">'
                   f'<button class="ghost" title="Delete">✕</button></form>')
        rows += (f'<div class="filerow"><span class="name" title="{html.escape(p.name)}">{html.escape(p.name)}</span>'
                 f'<span class="chip {cls}">{html.escape(label)}</span>'
                 f'<span class="sz">{p.stat().st_size//1024} KB</span>{delform}</div>')
        tiles += (f'<div class="ftile">{delform}'
                  f'<span class="fmt">{html.escape(p.suffix.lstrip(".").upper() or "?")}</span>'
                  f'<span class="nm" title="{html.escape(p.name)}">{html.escape(p.name)}</span>'
                  f'<span class="chip {cls}">{html.escape(label).replace(" · ", "<br>")}</span></div>')
    if not rows:
        rows = tiles = '<div class="hint" style="padding:8px 4px">No documents yet. Drop the pack above.</div>'
    addcard = 'onclick="document.getElementById(\'fi\').click()" title="Add documents"'
    rows += f'<div class="addrow" {addcard}>+</div>'
    tiles += f'<div class="ftile addtile" {addcard}>+</div>'
    unassigned = [f for f, (_, c) in roles.items() if c == "warn"]
    warn_banner = (f'<div class="banner">⚠ {len(unassigned)} file(s) are <b>not being analysed</b> '
                   f'(no role matched): {", ".join(html.escape(u) for u in unassigned)}. Rename to include '
                   f'their market and kind, or delete them.</div>' if unassigned else "")

    runrows = ""
    for run in list_runs(ws):
        rec, chip = "-", '<span class="chip skip">no result</span>'
        if (run / "state.json").exists():
            try:
                st = json.load(open(run / "state.json"))
                r = st["conclusion"]["recommendation"]
                notable = [f for f in st["findings"] if f["status"] in ("FAIL", "WARN")]
                fails = sum(1 for f in notable if f["status"] == "FAIL")
                rec = f"recommends {r}" if r else "no market modelled"
                if notable:
                    label = (f'{fails} check failed' if fails else f'{len(notable)} warning(s)')
                    cls = "fail" if fails else "warn"
                    items = "".join(
                        f'<b>{f["id"]} · {html.escape(f["name"])} '
                        f'<span class="chip {"fail" if f["status"] == "FAIL" else "warn"}">{f["status"]}</span></b>'
                        f'<p>{html.escape(f["detail"])}</p>'
                        + (f'<p><i>{html.escape(f["note"])}</i></p>' if f.get("note") else "")
                        for f in notable)
                    chip = (f'<details class="pillpop"><summary class="chip {cls}">{label} ▾</summary>'
                            f'<div class="pop">{items}</div></details>')
                else:
                    passes = sum(1 for f in st["findings"] if f["status"] == "PASS")
                    infos = "".join(f'<b>{f["id"]} · {html.escape(f["name"])}</b><p>{html.escape(f["detail"])}</p>'
                                    for f in st["findings"] if f["status"] == "INFO")
                    chip = (f'<details class="pillpop"><summary class="chip ok">checks clean ▾</summary>'
                            f'<div class="pop"><b>{passes} checks passed</b>{infos}</div></details>')
            except Exception:  # noqa: BLE001
                pass
        ts = datetime.strptime(run.name, "%Y%m%d-%H%M%S").strftime("%d %b · %H:%M")
        repbtn = (f'<a class="btn" href="/w/{ws.name}/results/{run.name}">Report</a>'
                  f'<a class="pdfdl" href="/w/{ws.name}/report/{run.name}/pdf" '
                  f'title="Download as PDF">{DLI}</a>'
                  if (run / "state.json").exists() else "")
        runrows += (f'<div class="runrow"><span class="stamp">{ts}</span>'
                    f'<span class="rec" style="flex:1">{rec}</span>{chip}{repbtn}'
                    f'<form method="post" action="/w/{ws.name}/runs/{run.name}/delete" '
                    f'onsubmit="return confirm(\'Delete this run and its report?\')">'
                    f'<button class="rdel" title="Delete run">{TRASH}</button></form></div>')
    if not runrows:
        runrows = '<div class="hint" style="padding:8px 4px">No runs yet.</div>'

    key = sk()["value"]
    key_field = (
        '<input type="password" name="api_key" id="kf" autocomplete="off" '
        + ('placeholder="key set for this session. Paste another to replace" '
           if key else 'placeholder="API key, optional (Anthropic / OpenAI / Gemini; auto-detected)" ')
        + 'style="width:100%;font-family:monospace;font-size:12.5px" '
        'onchange="checkKey(this)">'
        '<div class="hint" id="kstat" style="min-height:15px"></div>'
        '<script>async function checkKey(el){'
        'const v=el.value.trim();const st=document.getElementById("kstat");'
        'if(!v){st.textContent="";el.style.borderColor="";return}'
        'st.textContent="checking…";st.style.color="";'
        'const r=await fetch("/keycheck",{method:"POST",headers:{"Content-Type":"application/json"},'
        'body:JSON.stringify({key:v})});const j=await r.json();'
        'el.style.borderColor=j.ok?"#2F7D4F":"#c12d00";'
        'st.style.color=j.ok?"#7bd8b8":"#f2b3a7";st.textContent=j.detail;}'
        '</script>')

    body = f"""
    <div class="card headbar" style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
      <h1 class="xtitle">{fancy_title(ws.name)}</h1>
      <div class="tabsbar">
        <button class="tabbtn" id="tb-files" onclick="setTab('files')">Files</button>
        <button class="tabbtn" id="tb-runs" onclick="setTab('runs')">Runs</button>
      </div>
    </div>
    {warn_banner}
    <section id="pane-files" class="card">
      <div style="display:flex;align-items:center;gap:12px">
        <h2 style="margin:0;flex:1">Documents</h2>
        <div class="viewtog">
          <button id="vt-grid" onclick="setView('grid')" title="Icon view">⊞</button>
          <button id="vt-list" onclick="setView('list')" title="List view">≡</button>
        </div>
        <form method="post" action="/w/{ws.name}/files/clean"
          onsubmit="return confirm('Remove ALL documents from this workspace?')">
          <button class="ghost">Clean all</button></form>
      </div>
      <form method="post" action="/w/{ws.name}/files/upload" enctype="multipart/form-data" id="upf" style="margin-top:12px">
        <label class="drop" id="drop">Drop documents here, or click to choose
          <small>PDF · XLSX · HTML · CSV · roles auto-detected; anything unrecognised is flagged, never ignored</small>
          <input type="file" name="docs" multiple id="fi"></label>
      </form>
      <div id="fl-list" style="margin-top:12px">{rows}</div>
      <div id="fl-grid" class="fgridV" style="margin-top:12px;display:none">{tiles}</div>
    </section>
    <section id="pane-runs" class="two" style="display:none">
      <form class="card" method="post" action="/w/{ws.name}/run" style="display:flex;flex-direction:column;gap:12px">
        <h2 style="margin:0">New run</h2>
        <div class="modes">
          <button class="mode" name="ai" value="auto"><b>Glide</b>
            <span>deterministic core; AI only where patterns fail · seconds, ~€0</span></button>
          <button class="mode after" name="ai" value="max"><b>Afterburner</b>
            <span>Glide, then the model re-checks every extracted value · needs a key</span></button>
        </div>
        {key_field}
        <span class="hint">read → extract → unify → dedupe → compare → check → conclude
         · <button class="ghost" name="ai" value="off" style="font-size:11px;padding:0">run with AI fully off</button></span>
      </form>
      <div class="rowgrip" id="rowgrip" title="Drag to resize"></div>
      <div class="card"><h2>Runs</h2><div class="runscroll">{runrows}</div></div>
    </section>
    <script>
     const WS={json.dumps(ws.name)};
     function setTab(t){{localStorage.setItem('tab-'+WS,t);
       document.getElementById('pane-files').style.display=t==='files'?'':'none';
       document.getElementById('pane-runs').style.display=t==='runs'?'':'none';
       document.getElementById('tb-files').classList.toggle('on',t==='files');
       document.getElementById('tb-runs').classList.toggle('on',t==='runs');}}
     function setView(v){{localStorage.setItem('view-'+WS,v);
       document.getElementById('fl-list').style.display=v==='list'?'':'none';
       document.getElementById('fl-grid').style.display=v==='grid'?'grid':'none';
       document.getElementById('vt-grid').classList.toggle('on',v==='grid');
       document.getElementById('vt-list').classList.toggle('on',v==='list');}}
     setTab(localStorage.getItem('tab-'+WS)||'files');
     setView(localStorage.getItem('view-'+WS)||'list');
     const drop=document.getElementById('drop'),fi=document.getElementById('fi'),upf=document.getElementById('upf');
     fi.addEventListener('change',()=>upf.submit());
     ;['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{{ev.preventDefault();drop.classList.add('drag')}}));
     ;['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{{ev.preventDefault();drop.classList.remove('drag')}}));
     drop.addEventListener('drop',ev=>{{fi.files=ev.dataTransfer.files;upf.submit()}});
     document.addEventListener('click',e=>{{document.querySelectorAll('details.pillpop[open]').forEach(d=>{{if(!d.contains(e.target))d.removeAttribute('open')}})}});
     const XT=document.querySelector('.xtitle');
     if(XT){{XT.title='Click to rename';
      XT.addEventListener('click',()=>{{
       if(document.querySelector('input.titled'))return;
       const inp=document.createElement('input');inp.className='titled';inp.value=WS;
       XT.replaceWith(inp);inp.focus();inp.select();let fin=false;
       const done=save=>{{if(fin)return;fin=true;const v=inp.value.trim();
        if(save&&v&&v!==WS){{const f=document.createElement('form');f.method='post';
         f.action='/w/'+WS+'/rename';const i=document.createElement('input');
         i.type='hidden';i.name='name';i.value=v;f.appendChild(i);
         document.body.appendChild(f);f.submit();}}
        else inp.replaceWith(XT);}};
       inp.addEventListener('keydown',e=>{{if(e.key==='Enter')done(true);
        if(e.key==='Escape')done(false)}});
       inp.addEventListener('blur',()=>done(true));}});}}
     document.querySelectorAll('.runrow a.btn').forEach(a=>{{a.addEventListener('click',ev=>{{
       if(ev.metaKey||ev.ctrlKey)return;const parts=a.getAttribute('href').split('/results/');
       if(parts.length<2)return;ev.preventDefault();openRep(parts[1]);}});}});
     let repOpen=null;
     function openRep(run){{
       if(!/^[0-9]{{8}}-[0-9]{{6}}$/.test(run))return;
       const pr=document.getElementById('pane-runs');pr.classList.add('wide');
       history.pushState({{rep:run}},'','#report-'+run);
       setTimeout(()=>{{if(repOpen)return;
         const card=pr.querySelector('div.card');
         const w=document.createElement('div');w.className='repwrap';
         w.innerHTML='<div><button class="btn" id="repback">← Back to runs</button></div>'
           +'<iframe src="/w/'+WS+'/results/'+run+'?embed=1" title="report"></iframe>';
         card.querySelector('h2').style.display='none';
         const rs=card.querySelector('.runscroll');if(rs)rs.style.display='none';
         card.appendChild(w);repOpen=w;
         document.getElementById('repback').onclick=()=>closeRep(true);
       }},360);
     }}
     function closeRep(push){{
       const pr=document.getElementById('pane-runs');
       if(repOpen){{repOpen.remove();repOpen=null;
         const card=pr.querySelector('div.card');
         card.querySelector('h2').style.display='';
         const rs=card.querySelector('.runscroll');if(rs)rs.style.display='';}}
       pr.classList.remove('wide');
       if(push&&location.hash.indexOf('#report-')===0)history.pushState({{}},'',location.pathname);
     }}
     window.addEventListener('popstate',()=>{{if(repOpen)closeRep(false)}});
     if(location.hash.indexOf('#report-')===0){{setTab('runs');openRep(location.hash.slice(8))}}
     const rg=document.getElementById('rowgrip');
     if(rg){{const two=document.getElementById('pane-runs');
      try{{const s=parseInt(localStorage.getItem('mr-runw-'+WS));
       if(s)two.style.setProperty('--runw',s+'px')}}catch(e){{}}
      rg.addEventListener('pointerdown',e=>{{e.preventDefault();
       const x0=e.clientX,w0=two.querySelector('form.card').offsetWidth;rg.classList.add('dragging');
       const mv=ev=>{{two.style.setProperty('--runw',
         Math.max(220,Math.min(560,w0+(ev.clientX-x0)))+'px')}};
       const up=()=>{{rg.classList.remove('dragging');
        try{{localStorage.setItem('mr-runw-'+WS,two.querySelector('form.card').offsetWidth)}}catch(e){{}}
        window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up)}};
       window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up)}});}}
    </script>"""
    return page(f"{ws.name} · Market Runway", body, f"/ {ws.name}", rail=rail_html(ws.name, view="the workspace Files and Runs view"))


@app.post("/w/<ws_name>/files/upload")
def upload(ws_name):
    ws = ws_dir(ws_name)
    for fs in request.files.getlist("docs"):
        if fs.filename:
            fs.save(ws / "raw" / Path(fs.filename).name)
    build_manifest(ws)
    return redirect(f"/w/{ws.name}")


@app.post("/w/<ws_name>/files/delete")
def delete_file(ws_name):
    ws = ws_dir(ws_name)
    name = Path(request.form.get("f", "")).name
    target = ws / "raw" / name
    if target.is_file():
        target.unlink()
        # drop any manifest assignment pointing at it, then re-map
        mpath = ws / "manifest.yaml"
        if mpath.exists():
            man = yaml.safe_load(open(mpath)) or {}
            for sec in ("company_docs", "shared_docs"):
                man[sec] = {k: v for k, v in (man.get(sec) or {}).items() if v.get("file") != name}
            for mk in list(man.get("markets") or {}):
                man["markets"][mk] = {k: v for k, v in man["markets"][mk].items() if v.get("file") != name}
                if not man["markets"][mk]:
                    del man["markets"][mk]
            yaml.safe_dump(man, open(mpath, "w"), sort_keys=False)
        build_manifest(ws)
    return redirect(f"/w/{ws.name}")


@app.post("/w/<ws_name>/files/clean")
def clean_files(ws_name):
    ws = ws_dir(ws_name)
    for p in (ws / "raw").glob("*"):
        if p.is_file():
            p.unlink()
    (ws / "manifest.yaml").unlink(missing_ok=True)
    return redirect(f"/w/{ws.name}")


ANSI = re.compile(r"\x1b\[[0-9;]*m")


@app.post("/w/<ws_name>/run")
def run_ws(ws_name):
    ws = ws_dir(ws_name)
    ai = request.form.get("ai", "auto")
    if ai not in ("off", "auto", "max"):
        ai = "auto"
    submitted = (request.form.get("api_key") or "").strip()
    if submitted:
        sk()["value"] = submitted
        sk()["provider"] = detect_provider(submitted)
        _keys_save()
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("RUNWAY_KEY", None); env.pop("RUNWAY_PROVIDER", None)
    if sk()["value"] and sk().get("provider"):
        env["RUNWAY_KEY"] = sk()["value"]
        env["RUNWAY_PROVIDER"] = sk()["provider"]
        if sk()["provider"] == "anthropic":
            env["ANTHROPIC_API_KEY"] = sk()["value"]
    token = uuid.uuid4().hex[:12]
    RUNTASKS[token] = {"lines": [], "done": False, "ok": None, "ws": ws.name, "run": None, "ai": ai}
    threading.Thread(target=_runner, args=(token, ws.name, ai, env), daemon=True).start()
    return redirect(f"/w/{ws.name}/run/{token}", code=303)


def _runner(token, ws_name, ai, env):
    t = RUNTASKS[token]
    try:
        proc = subprocess.Popen([PY, str(ROOT / "run.py"), "--ai", ai, "--workspace", ws_name],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, cwd=ROOT, env=env, bufsize=1)
        for line in proc.stdout:
            t["lines"].append(ANSI.sub("", line.rstrip()))
        proc.wait()
        run = latest_run(ws_dir(ws_name))
        ok = proc.returncode == 0 and run is not None
        if ok:
            t["lines"].append("generating the evidence report…")
            subprocess.run([PY, "-c",
                            f"import sys; sys.path.insert(0,'{ROOT}'); from src.report import build; build(r'{run}/state.json')"],
                           cwd=ROOT, capture_output=True, timeout=120)
            t["run"] = run.name
        t["ok"] = ok
    except Exception as e:  # noqa: BLE001
        t["lines"].append(f"runner error: {e}")
        t["ok"] = False
    t["done"] = True


def _stage_of(line: str):
    m = re.search(r"\[stage (\d)\]", line)
    if m:
        return int(m.group(1))
    if "generating the evidence report" in line:
        return 8
    return None


@app.get("/w/<ws_name>/run/<token>")
def run_view(ws_name, token):
    ws = ws_dir(ws_name)
    t = RUNTASKS.get(token)
    if t is None or t["ws"] != ws.name:
        return redirect(f"/w/{ws.name}")
    mode_label = {"auto": "Glide", "max": "Afterburner", "off": "AI off"}.get(t["ai"], t["ai"])

    def colorize(line: str) -> str:
        e = html.escape(line)
        return (e.replace("PASS", '<span class="ok">PASS</span>')
                 .replace("FAIL", '<span class="fail">FAIL</span>')
                 .replace("WARN", '<span class="warn">WARN</span>'))

    def emit(line):
        out = colorize(line) + "\n"
        n = _stage_of(line)
        if n:
            out += f'<script>bar({n})</script>'
        return out

    def generate():
        full = page("Run · Market Runway", "@@CUT@@", f"/ {ws.name} / run", rail=rail_html(ws.name, view="a live pipeline run streaming"))
        head, tail = full.split("@@CUT@@")
        yield head + (
            f'<div><div class="eyebrow">{ws.name} · pipeline run · {mode_label}</div>'
            '<h1 class="xtitle" id="rt" style="font-size:clamp(20px,2.2vw,26px)">Running…</h1>'
            '<div class="pb" id="pb"><i></i></div></div>'
            '<script>function bar(n){document.querySelector("#pb i").style.width='
            'Math.min(96,Math.round(n/8*100))+"%";'
            'var l=document.getElementById("lg");if(l)l.scrollTop=l.scrollHeight}</script>'
            '<pre class="log" id="lg">')
        yield "<!--" + " " * 2048 + "-->\n"
        i = 0
        idle = 0.0
        while True:
            lines = t["lines"]
            while i < len(lines):
                yield emit(lines[i])
                i += 1
                idle = 0.0
            if t["done"]:
                break
            time.sleep(0.25)
            idle += 0.25
            if idle >= 3.0:
                yield "<!-- hb -->"
                idle = 0.0
        ok = bool(t["ok"])
        actions = (f'<a class="btn primary" href="/w/{ws.name}#report-{t["run"]}">Open the report →</a>'
                   '' if ok and t["run"] else "")
        yield ('</pre><div style="display:flex;gap:10px;margin-top:12px">' + actions
               + f'<a class="btn" href="/w/{ws.name}">← workspace</a></div>'
               + '<script>document.getElementById("rt").textContent='
               + ('"Run complete"' if ok else '"Run failed"')
               + f';document.getElementById("pb").classList.add("{"done" if ok else "fail"}");'
               + 'document.querySelector("#pb i").style.width="100%";'
               + 'var l=document.getElementById("lg");l.scrollTop=l.scrollHeight;'
               + (f'setTimeout(function(){{location.href="/w/{ws.name}#report-{t["run"]}"}},700);'
                  if ok and t["run"] else '')
               + '</script>' + tail)

    return Response(stream_with_context(generate()), mimetype="text/html",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


SEG_JS = ('<script>(function(){var KEY="seg-__WS__";'
          'var segs=["evidence","deck","dataset","insights"];'
          'function show(s){segs.forEach(function(x){'
          'document.getElementById("sb-"+x).style.display=x===s?"flex":"none";'
          'document.getElementById("sg-"+x).classList.toggle("on",x===s);});'
          'try{localStorage.setItem(KEY,s)}catch(e){}'
          'var f=document.querySelector("#sb-"+s+" iframe");'
          'if(f&&!f.getAttribute("src")){f.src=f.dataset.src;'
          'if(f.dataset.autoh)f.onload=function(){var fit=function(){try{'
          'f.style.height=(f.contentDocument.documentElement.scrollHeight+24)+"px";'
          'f.style.flex="none"}catch(e){}};fit();setTimeout(fit,700)}}}'
          'segs.forEach(function(x){document.getElementById("sg-"+x).onclick=function(){show(x)}});'
          'var init="evidence";'
          'try{var st=localStorage.getItem(KEY);if(segs.indexOf(st)>=0)init=st}catch(e){}'
          'show(init);})();</script>')


@app.get("/w/<ws_name>/results/<run_name>")
def results_view(ws_name, run_name):
    ws = ws_dir(ws_name)
    run = ws / "runs" / Path(run_name).name
    if not (run / "state.json").exists():
        return redirect(f"/w/{ws.name}")
    st = json.load(open(run / "state.json"))
    man, con = st.get("manifest", {}), st.get("conclusion", {})
    ranking = con.get("ranking") or []
    res = con.get("results") or {}
    rec = con.get("recommendation")
    ts = datetime.strptime(run.name, "%Y%m%d-%H%M%S").strftime("%d %b %Y · %H:%M")

    def eur_m(v):
        try:
            return f"€{v/1e6:.1f}M"
        except Exception:  # noqa: BLE001
            return "-"

    def be(r):
        return (f"break-even Y{r['break_even_year']}" if r and r.get("break_even_year")
                else "no break-even in 5y")

    win = res.get(rec) if rec else None
    runner = ranking[1] if len(ranking) > 1 else None
    rr = res.get(runner) if runner else None
    seq = " → ".join(ranking) if ranking else "-"
    if con.get("skipped"):
        seq += " · not modelled: " + ", ".join(con["skipped"])
    slides = [
        ("S1", "Recommendation",
         (f"enter {rec} first: {be(win)}, trough {eur_m(win['min_cash'])}" if win else "no market modelled")),
        ("S2", "The counter-case",
         (f"{runner}: {be(rr)}, trough {eur_m(rr['min_cash'])}, end cash {eur_m(rr['end_cash'])}"
          if rr else "no runner-up modelled")),
        ("S3", "The winning market",
         (f"{rec}: end cash {eur_m(win['end_cash'])}, minimum cash {eur_m(win['min_cash'])}" if win else "-")),
        ("S4", "Sensitivity",
         (" · ".join(f"{m}: {'insolvent' if res[m].get('insolvent') else 'fundable'}" for m in ranking)
          or "full grids in the evidence report")),
        ("S5", "Sequencing", seq),
    ]
    ev = (f'<iframe data-src="/w/{ws.name}/report/{run.name}?bare=1" data-autoh="1" '
          f'title="evidence"></iframe>')
    deck = ""
    if rec:
        deck += (f'<div class="iband"><b>Engine verdict: enter {rec} first</b>'
                 f'<span>ranking: {" → ".join(ranking)}</span></div>')
    deck += ('<div class="steps">'
             + "".join(f'<div><span>{s}</span><b>{t}</b><p>{html.escape(d)}</p></div>' for s, t, d in slides)
             + '</div><p class="hint" style="margin-top:12px">The outline is fixed by the method; '
               'every number on it comes from this run.</p>')
    fnd = st.get("findings", [])
    ext = man.get("extraction", {})
    facts = [
        ("Files", len(st.get("ingestion", []))),
        ("Markets modelled", len(res)),
        ("Values extracted", f'{ext.get("total", "-")} · {ext.get("deterministic", 0)} det / {ext.get("ai", 0)} AI'),
        ("Checks", f'{sum(1 for x in fnd if x["status"] == "PASS")} / {len(fnd)} passed'),
        ("Recommendation", rec or "-"),
        ("Break-even", f"Y{win['break_even_year']}" if win and win.get("break_even_year") else "-"),
        ("Cash trough", eur_m(win["min_cash"]) if win else "-"),
        ("LLM calls", f'{man.get("llm_calls", 0)} · €{man.get("llm_cost_eur", 0):.2f}'),
    ]
    dls = "".join(f'<a class="btn" style="font-size:12px" href="/w/{ws.name}/runs/{run.name}/f/{n}">{n}</a>'
                  for n in ("markets.csv", "facilities.csv", "validation_findings.csv", "state.json")
                  if (run / n).exists())
    dataset = ('<div class="facts">'
               + "".join(f'<div><span>{k}</span><b>{html.escape(str(v))}</b></div>' for k, v in facts)
               + f'</div><div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">{dls}</div>')
    gaps = st.get("gaps", [])
    audit = st.get("audit", [])
    agree = sum(1 for x in audit if x.get("verdict") == "AGREE")
    dis = [x for x in audit if x.get("verdict") == "DISAGREE"]
    unass = st.get("files", {}).get("unassigned", [])
    audit_line = (f"{len(audit)} values re-checked by the model · {agree} agree · {len(dis)} disagree"
                  if audit else "no AI audit in this run (Glide or AI off)")
    gap_cards = "".join(
        f'<div><span>{g["id"]}</span><b>{html.escape(g["field"])}</b>'
        f'<p>{html.escape(g["market"])} · {html.escape(g["why"])}</p></div>'
        for g in gaps) or '<div><span>-</span><b>None</b><p>No open evidence gaps.</p></div>'
    ins = (f'<div class="iband"><b>Model audit</b><span>{audit_line}</span></div>'
           + "".join(f'<div class="banner" style="margin-bottom:10px">DISAGREE {x["scope"]}.{x["param"]}: '
                     f'det={x["det"]} vs llm={x["llm"]}</div>' for x in dis[:6])
           + '<p class="hint" style="margin:4px 0 8px">Evidence gaps: what the pack does not establish</p>'
           + f'<div class="steps">{gap_cards}</div>'
           + (f'<p class="hint" style="margin-top:10px">Unrecognised files (not analysed): '
              f'{html.escape(", ".join(unass))}</p>' if unass else ""))
    segbar = "".join(f'<button id="sg-{k}">{lbl}</button>' for k, lbl in
                     (("evidence", "Evidence report"), ("deck", "Deck"),
                      ("dataset", "Dataset"), ("insights", "Insights")))
    if request.args.get("embed"):
        doc = (f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
               f'<title>Results</title>{STYLE}'
               '<body style="background:transparent;margin:0">'
               '<style>.segbody iframe{min-height:68vh}</style>'
               '<div class="stage2" style="background:none;border:none;box-shadow:none;padding:0;'
               'height:auto;min-height:0;-webkit-backdrop-filter:none;backdrop-filter:none">'
               f'<div class="seg">{segbar}</div>'
               f'<div class="segbody" id="sb-evidence">{ev}</div>'
               f'<div class="segbody" id="sb-deck" style="display:none">{deck}</div>'
               f'<div class="segbody" id="sb-dataset" style="display:none">{dataset}</div>'
               f'<div class="segbody" id="sb-insights" style="display:none">{ins}</div></div>'
               + SEG_JS.replace("__WS__", ws.name) + '</body>')
        return doc
    body = (f'<div class="card headbar" style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">'
            f'<div style="flex:1"><div class="eyebrow">{ws.name} · results</div>'
            f'<h1 class="xtitle" style="margin-top:4px;font-size:clamp(20px,2.2vw,26px)">Run {ts}</h1></div>'
            f'<a class="btn" href="/w/{ws.name}">← workspace</a></div>'
            f'<div class="stage2"><div class="seg">{segbar}</div>'
            f'<p class="recnote">Computed by the pipeline on this desk · every number from this run’s '
            f'state.json - nothing hand-edited.</p>'
            f'<div class="segbody" id="sb-evidence">{ev}</div>'
            f'<div class="segbody" id="sb-deck" style="display:none">{deck}</div>'
            f'<div class="segbody" id="sb-dataset" style="display:none">{dataset}</div>'
            f'<div class="segbody" id="sb-insights" style="display:none">{ins}</div></div>'
            + SEG_JS.replace("__WS__", ws.name))
    return page(f"Results · {ws.name}", body, f"/ {ws.name} / results", rail=rail_html(ws.name, run=run.name, view=f"the results windows of run {run.name}"))


@app.get("/w/<ws_name>/report/<run_name>/pdf")
def report_pdf(ws_name, run_name):
    ws = ws_dir(ws_name)
    run = ws / "runs" / Path(run_name).name
    src = run / "report.html"
    if not src.exists():
        return redirect(f"/w/{ws.name}")
    out = run / "report.pdf"
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        try:
            from weasyprint import HTML
            HTML(string=src.read_text(), base_url=str(run)).write_pdf(str(out))
        except Exception as e:  # noqa: BLE001
            return Response(f"PDF engine unavailable on this host: {html.escape(str(e))}", status=503)
    return send_file(out, as_attachment=True,
                     download_name=f"MarketRunway_Report_{run.name}.pdf")


@app.get("/w/<ws_name>/runs/<run_name>/f/<name>")
def run_file(ws_name, run_name, name):
    ws = ws_dir(ws_name)
    allowed = {"markets.csv", "facilities.csv", "agreement_matrix.csv",
               "validation_findings.csv", "state.json", "manifest.json"}
    f = ws / "runs" / Path(run_name).name / name
    if name not in allowed or not f.exists():
        return redirect(f"/w/{ws.name}")
    return send_file(f)


@app.post("/reorder")
def reorder():
    names = (request.get_json(force=True) or {}).get("order", [])
    valid = [n for n in names if isinstance(n, str) and ws_dir(Path(n).name).exists()]
    try:
        (WORKSPACES / ".order.json").write_text(json.dumps(valid))
    except OSError:
        pass
    return jsonify({"ok": True})


@app.post("/w/<ws_name>/rename")
def ws_rename(ws_name):
    ws = ws_dir(ws_name)
    new = slugify(request.form.get("name", ""))
    if ws.exists() and new and new != ws.name and not ws_dir(new).exists():
        ws.rename(ws_dir(new))
        return redirect(f"/w/{new}")
    return redirect(f"/w/{ws.name}")


@app.post("/w/<ws_name>/duplicate")
def ws_duplicate(ws_name):
    ws = ws_dir(ws_name)
    if not ws.exists():
        return redirect("/")
    base, new, i = f"{ws.name}-copy", f"{ws.name}-copy", 2
    while ws_dir(new).exists():
        new, i = f"{base}-{i}", i + 1
    nd = ws_dir(new)
    (nd / "raw").mkdir(parents=True)
    (nd / "runs").mkdir()
    for p in (ws / "raw").glob("*"):
        if p.is_file():
            shutil.copy2(p, nd / "raw" / p.name)
    return redirect(f"/w/{new}")


@app.post("/w/<ws_name>/delete")
def ws_delete(ws_name):
    ws = ws_dir(ws_name)
    if ws.exists():
        shutil.rmtree(ws)
    return redirect("/")


@app.post("/w/<ws_name>/runs/<run_name>/delete")
def delete_run(ws_name, run_name):
    ws = ws_dir(ws_name)
    if re.fullmatch(r"[0-9]{8}-[0-9]{6}", run_name):
        target = ws / "runs" / run_name
        if target.is_dir():
            shutil.rmtree(target)
        latest = ws / "runs" / "latest"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        rem = sorted(p for p in (ws / "runs").iterdir() if p.is_dir())
        if rem:
            latest.symlink_to(rem[-1].name)
    return redirect(f"/w/{ws.name}")


@app.post("/w/<ws_name>/research/<run_name>/<gap_id>")
def research(ws_name, run_name, gap_id):
    ws = ws_dir(ws_name)
    key, prov = sk()["value"], sk().get("provider")
    if not key or not prov:
        return jsonify({"ok": False, "error": "No API key. Add one via the chip top-right, then retry."})
    run = ws / "runs" / Path(run_name).name
    try:
        state = json.load(open(run / "state.json"))
        gap = next(g for g in state["gaps"] if g["id"] == gap_id)
    except Exception:  # noqa: BLE001
        return jsonify({"ok": False, "error": "gap not found for this run"})
    plan = "; ".join(gap.get("plan", []))
    prompt = (
        f"You are the sourcing workflow of a market-entry pipeline. Execute this research plan from your "
        f"own knowledge, as a DRAFT for human review.\n"
        f"Gap {gap['id']}: {gap['field']} (scope: {gap['market']}).\nWhy it matters: {gap['why']}\n"
        f"Plan: {plan}\n"
        f"Give: (1) a best estimate or range with units and reasoning, (2) three named sources or report "
        f"types to verify it (organisations/publications, no URLs needed), (3) a confidence level. "
        f"Under 180 words. End with exactly: DRAFT: quarantined; not merged into the dataset.")
    model = next(iter(PROVIDERS[prov]["models"]))
    try:
        text = _chat_call(prov, key, model, "You answer concisely and factually.", 
                          [{"role": "user", "content": prompt}])
        return jsonify({"ok": True, "text": text,
                        "meta": f"{PROVIDERS[prov]['label']} · {PROVIDERS[prov]['models'][model]}"})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"{PROVIDERS[prov]['label']} call failed: {e}"})


@app.get("/w/<ws_name>/report/<run_name>")
def report(ws_name, run_name):
    run = ws_dir(ws_name) / "runs" / Path(run_name).name
    f = run / "report.html"
    if not f.exists() and (run / "state.json").exists():
        subprocess.run([PY, "-c",
                        f"import sys; sys.path.insert(0,'{ROOT}'); from src.report import build; build(r'{run}/state.json')"],
                       cwd=ROOT, capture_output=True, timeout=120)
    if not f.exists():
        return redirect(f"/w/{ws_name}")
    doc = f.read_text()
    if 'class="research"' in doc:
        doc = doc.replace('class="research" disabled', 'class="research"')
        hook = (
            "<script>const WSN=" + json.dumps(ws_name) + ",RUNN=" + json.dumps(run.name) + ";"
            "document.querySelectorAll('.research').forEach(b=>b.onclick=async()=>{"
            "b.disabled=true;b.textContent='Researching…';"
            "const r=await fetch(`/w/${WSN}/research/${RUNN}/${b.dataset.gap}`,{method:'POST'});"
            "const j=await r.json();const d=document.createElement('div');d.className='rsx';"
            "d.textContent=j.ok?(j.text+'\\n\\n['+j.meta+']'):('⚠ '+j.error);"
            "b.closest('.gap').appendChild(d);"
            "b.textContent=j.ok?'Researched: draft below':'Research this';if(!j.ok)b.disabled=false;});"
            "</script></body>")
        doc = doc.replace("</body>", hook, 1)
    if request.args.get("bare"):
        doc = doc.replace("</body>", (
            "<style>body{background:transparent !important;margin:0;padding:0}"
            ".wrap{max-width:none;padding:2px 4px 18px}</style></body>"), 1)
    return Response(doc, mimetype="text/html")


# ---------------------------------------------------------------- chat
def _grounding(ws: Path, run_name: str = None) -> tuple[str, str]:
    run = (ws / "runs" / Path(run_name).name) if run_name else latest_run(ws)
    if run_name and not (run / "state.json").exists():
        run = latest_run(ws)
    if not run or not (run / "state.json").exists():
        return "", ""
    st = json.load(open(run / "state.json"))
    compact = {
        "workspace": ws.name, "run": run.name,
        "dataset": {s: {p: {"value": e["value"], "unit": e["unit"], "method": e["method"],
                            "source": e["source"]} for p, e in d.items()}
                    for s, d in st["dataset"].items()},
        "conclusion": st["conclusion"],
        "validation_findings": st["findings"],
        "facilities_summary": st["facilities"]["summary"],
        "evidence_gaps": [{k: g[k] for k in ("id", "market", "field", "why")} for g in st["gaps"]],
        "files": st.get("files", {}),
    }
    return json.dumps(compact, default=str), run.name


SYSTEM = """You are Runway's analyst assistant for a market-entry assessment.
GROUNDING RULES - absolute:
- Answer ONLY from the JSON dataset below (the pipeline's validated output). If something is not
  in it, say "not in the validated dataset"; never guess, never use outside knowledge for figures.
- Cite where a figure came from (its `source` and `method`) when giving numbers.
- Be concise and concrete. Currency is EUR.
- If the user asks to CHANGE a value, do not claim it is changed. Instead emit a proposal block:
```override
field: <scope>.<parameter>
value: <new value>
reason: <their stated reason, one line>
```
  and explain in one sentence what will happen (the pipeline re-runs with it, badged MANUAL).
DATASET:
"""


@app.get("/w/<ws_name>/chat")
def chat_page(ws_name):
    ws = ws_dir(ws_name)
    _, run_name = _grounding(ws)
    provider = sk().get("provider")
    if sk()["value"] and provider:
        models = PROVIDERS[provider]["models"]
        first = next(iter(models))
        opts = "".join(f'<option value="{m}" {"selected" if m == first else ""}>{lbl}</option>'
                       for m, lbl in models.items())
        picker = f'<select id="model">{opts}</select>'
        keyrow = ''
    else:
        picker = '<select id="model" hidden></select><span id="prov" class="hint"></span>'
        keyrow = ('<input type="password" id="key" placeholder="API key (Anthropic, OpenAI or Gemini)" '
                  'style="font-family:monospace;font-size:12.5px" oninput="detect()" onchange="verifyKey(this)">')
    banner = (f'grounded on run <b class="mono">{run_name}</b>; answers come only from the validated dataset'
              if run_name else "no runs yet. Run the pipeline first, then chat about its results")
    body = f"""
    <div class="chatbox">
     <div><div class="eyebrow">{ws.name} · ask the data</div>
      <h1 style="font-size:24px">Chat with the <em>validated</em> dataset</h1>
      <div class="hint" style="margin-top:6px">{banner}. To change a value, just say so - I'll draft an override
      you can apply (it re-runs the pipeline, badged MANUAL, fully audited).</div></div>
     <div id="msgs" style="display:flex;flex-direction:column;gap:10px"></div>
     <div class="chatinput">
      {picker}{keyrow}
      <input type="text" id="q" placeholder="e.g. Why not Germany? · Set Netherlands price to 190 because procurement pushback"
        onkeydown="if(event.key==='Enter')send()">
      <button class="primary" onclick="send()">Send</button>
     </div>
    </div>
    <script>
     const PROVIDERS={{anthropic:{{label:'Anthropic',models:{{'claude-sonnet-5':'Claude Sonnet 5 (default)','claude-haiku-4-5-20251001':'Claude Haiku 4.5','claude-fable-5':'Claude Fable 5'}}}},
                       openai:{{label:'OpenAI',models:{{'gpt-5.1':'GPT-5.1 (default)','gpt-5-mini':'GPT-5 mini'}}}},
                       google:{{label:'Google',models:{{'gemini-3-pro-preview':'Gemini 3 Pro (default)','gemini-2.5-flash':'Gemini 2.5 Flash'}}}}}};
     function detectProvider(k){{k=(k||'').trim();
       if(k.startsWith('sk-ant-'))return 'anthropic';
       if(/^AIza[0-9A-Za-z_-]{{30,}}$/.test(k))return 'google';
       if(k.startsWith('sk-'))return 'openai';return null}}
     async function verifyKey(el){{
       const v=el.value.trim();const badge=document.getElementById('prov');if(!v||!badge)return;
       badge.textContent='checking…';badge.style.color='';
       const r=await fetch('/keycheck',{{method:'POST',headers:{{'Content-Type':'application/json'}},
         body:JSON.stringify({{key:v}})}});const j=await r.json();
       el.style.borderColor=j.ok?'#2F7D4F':'#c12d00';
       badge.style.color=j.ok?'#2F7D4F':'#c12d00';badge.textContent=j.detail;
     }}
     function detect(){{const el=document.getElementById('key');if(!el)return;
       const p=detectProvider(el.value);const sel=document.getElementById('model');
       const badge=document.getElementById('prov');
       if(!p){{sel.hidden=true;if(badge)badge.textContent=el.value.trim()?'key format not recognised':'';return}}
       const m=PROVIDERS[p].models;sel.innerHTML=Object.entries(m).map(([v,l])=>`<option value="${{v}}">${{l}}</option>`).join('');
       sel.hidden=false;if(badge)badge.textContent=PROVIDERS[p].label+' key detected';}}
     const msgs=document.getElementById('msgs');let hist=[];
     function esc(s){{const d=document.createElement('div');d.textContent=s;return d.innerHTML}}
     function inline(t){{return t
       .replace(/`([^`\\n]+)`/g,'<code>$1</code>')
       .replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>')
       .replace(/(^|[^*])\\*([^*\\n]+)\\*(?!\\*)/g,'$1<em>$2</em>')}}
     function md(src){{
       const parts=esc(src).split(/```(?:\\w*\\n)?/);let out='';
       parts.forEach((seg,i)=>{{
         if(i%2){{out+='<pre><code>'+seg.replace(/\\n$/,'')+'</code></pre>';return}}
         const blocks=seg.split(/\\n{{2,}}/);
         blocks.forEach(b=>{{
           if(!b.trim())return;
           const lines=b.split('\\n');
           if(lines.every(l=>/^\\s*[-•]\\s+/.test(l)))
             out+='<ul>'+lines.map(l=>'<li>'+inline(l.replace(/^\\s*[-•]\\s+/,''))+'</li>').join('')+'</ul>';
           else if(lines.every(l=>/^\\s*\\d+[.)]\\s+/.test(l)))
             out+='<ol>'+lines.map(l=>'<li>'+inline(l.replace(/^\\s*\\d+[.)]\\s+/,''))+'</li>').join('')+'</ol>';
           else if(/^#{{1,3}}\\s/.test(lines[0])&&lines.length===1)
             out+='<h3>'+inline(lines[0].replace(/^#+\\s*/,''))+'</h3>';
           else out+='<p>'+lines.map(inline).join('<br>')+'</p>';
         }});
       }});
       return out}}
     function render(role,text){{
       const div=document.createElement('div');div.className='msg '+(role==='user'?'user':'ai');
       const m=text.match(/```override\\n([\\s\\S]*?)```/);
       let bodyTxt=text.replace(/```override\\n[\\s\\S]*?```/,'').trim();
       div.innerHTML=role==='user'?esc(bodyTxt):md(bodyTxt);
       if(m){{const ov=document.createElement('div');ov.className='ov';ov.textContent=m[1].trim();
         const b=document.createElement('button');b.className='primary';b.style.marginTop='8px';
         b.textContent='Apply override & re-run';b.onclick=()=>applyOv(m[1].trim(),b);
         div.appendChild(ov);div.appendChild(b);}}
       msgs.appendChild(div);div.scrollIntoView({{behavior:'smooth',block:'end'}});
     }}
     try{{hist=JSON.parse(localStorage.getItem('chathist-{ws.name}'))||[]}}catch(e){{hist=[]}}
     function saveH(){{try{{localStorage.setItem('chathist-{ws.name}',
       JSON.stringify(hist.slice(-40)))}}catch(e){{}}}}
     hist.forEach(m=>render(m.role==='user'?'user':'ai',m.content));
     async function send(){{
       const q=document.getElementById('q');const text=q.value.trim();if(!text)return;q.value='';
       const kk=text.replace(/\\s+/g,'');
       if(/^(sk-|AIza)[A-Za-z0-9_-]{{15,}}$/.test(kk)){{
         render('user','key ····'+kk.slice(-4));
         const kr=await fetch('/keycheck',{{method:'POST',headers:{{'Content-Type':'application/json'}},
           body:JSON.stringify({{key:kk}})}});
         const kj=await kr.json();
         const msg=(kj.ok?'Key saved: ':'⚠ ')+kj.detail;render('ai',msg);
         if(kj.ok){{hist.push({{role:'assistant',content:msg}});saveH();
           setTimeout(()=>location.reload(),900)}}
         return;
       }}
       render('user',text);hist.push({{role:'user',content:text}});saveH();
       const th=document.createElement('div');th.className='thinking';th.textContent='Thinking';
       msgs.appendChild(th);th.scrollIntoView({{behavior:'smooth',block:'end'}});
       const keyEl=document.getElementById('key');
       const r=await fetch('/w/{ws.name}/chat/send',{{method:'POST',headers:{{'Content-Type':'application/json'}},
         body:JSON.stringify({{messages:hist,model:document.getElementById('model').value,
                              key:keyEl?keyEl.value:null}})}});
       const j=await r.json().catch(()=>({{error:'network error - try again'}}));
       th.remove();
       if(j.error){{render('ai','⚠ '+j.error);return}}
       render('ai',j.text);hist.push({{role:'assistant',content:j.text}});saveH();
     }}
     async function applyOv(block,btn){{
       btn.disabled=true;btn.textContent='Applying & re-running…';
       const r=await fetch('/w/{ws.name}/override',{{method:'POST',headers:{{'Content-Type':'application/json'}},
         body:JSON.stringify({{block}})}});
       const j=await r.json();
       btn.textContent=j.ok?'Applied ✓ · open the new report':'Failed: '+j.error;
       if(j.ok){{btn.onclick=()=>location.href='/w/{ws.name}/report/'+j.run;btn.disabled=false}}
     }}
    </script>"""
    if request.args.get("embed"):
        doc = page(f"Chat · {ws.name}", body, f"/ {ws.name} / chat")
        return re.sub(r"<nav>.*?</nav>", "", doc, count=1, flags=re.S)
    return page(f"Chat · {ws.name}", body, f"/ {ws.name} / chat", rail=rail_html(ws.name, view="the full-page chat"))


@app.post("/w/<ws_name>/chat/send")
def chat_send(ws_name):
    ws = ws_dir(ws_name)
    data = request.get_json(force=True)
    if data.get("key"):
        sk()["value"] = data["key"].strip()
        sk()["provider"] = detect_provider(sk()["value"])
        _keys_save()
    if not sk()["value"]:
        return jsonify({"error": "No API key set. Paste an Anthropic, OpenAI or Gemini key next to the message box."})
    provider = sk().get("provider")
    if not provider:
        return jsonify({"error": "Key format not recognised. Expected sk-ant-… (Anthropic), sk-… (OpenAI) or AIza… (Gemini)."})
    grounding, run_name = _grounding(ws, data.get("run"))
    if not grounding:
        return jsonify({"error": "No completed run in this workspace yet."})
    models = PROVIDERS[provider]["models"]
    model = data.get("model") if data.get("model") in models else next(iter(models))
    try:
        msgs = [{"role": m["role"], "content": m["content"]}
                for m in data.get("messages", []) if m.get("role") in ("user", "assistant")][-20:]
        ctx = (data.get("context") or "").strip()[:200]
        sysmsg = SYSTEM + grounding + (f"\n\nThe user is currently looking at: {ctx}" if ctx else "")
        text = _chat_call(provider, sk()["value"], model, sysmsg, msgs)
        return jsonify({"text": text})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"{PROVIDERS[provider]['label']} call failed ({type(e).__name__}): {e}"})


@app.post("/w/<ws_name>/override")
def apply_override(ws_name):
    ws = ws_dir(ws_name)
    block = (request.get_json(force=True).get("block") or "").strip()
    try:
        ov = yaml.safe_load(block)
        assert isinstance(ov, dict) and "field" in ov and "value" in ov, "need field + value"
        ov.setdefault("reason", "requested via chat")
        ov["author"] = "chat"
        ovp = ws / "overrides.yaml"
        cfg = (yaml.safe_load(open(ovp)) if ovp.exists() else None) or {}
        cfg.setdefault("overrides", (cfg.get("overrides") or []))
        cfg["overrides"] = cfg["overrides"] or []
        cfg["overrides"].append(ov)
        yaml.safe_dump(cfg, open(ovp, "w"), sort_keys=False)
        env = dict(os.environ)
        if sk()["value"]:
            env["ANTHROPIC_API_KEY"] = sk()["value"]
        proc = subprocess.run([PY, str(ROOT / "run.py"), "--workspace", ws.name],
                              capture_output=True, text=True, cwd=ROOT, timeout=900, env=env)
        if proc.returncode != 0:
            return jsonify({"ok": False, "error": "pipeline run failed"})
        run = latest_run(ws)
        subprocess.run([PY, "-c",
                        f"import sys; sys.path.insert(0,'{ROOT}'); from src.report import build; build(r'{run}/state.json')"],
                       cwd=ROOT, capture_output=True, timeout=120)
        return jsonify({"ok": True, "run": run.name})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)})


@app.post("/keycheck")
def keycheck():
    import urllib.error
    import urllib.request
    key = (request.get_json(force=True).get("key") or "").strip()
    p = detect_provider(key)
    if not p:
        return jsonify({"ok": False, "detail": "key format not recognised (sk-ant-… / sk-… / AIza…)"})
    urls = {
        "anthropic": ("https://api.anthropic.com/v1/models",
                      {"x-api-key": key, "anthropic-version": "2023-06-01"}),
        "openai": ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"}),
        "google": (f"https://generativelanguage.googleapis.com/v1beta/models?key={key}", {}),
    }
    url, hdrs = urls[p]
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.load(r)
        n = len(out.get("data", out.get("models", [])))
        sk()["value"] = key
        sk()["provider"] = p
        _keys_save()
        return jsonify({"ok": True, "provider": p, "label": PROVIDERS[p]["label"],
                        "detail": f"{PROVIDERS[p]['label']} · key valid · {n} models visible"})
    except urllib.error.HTTPError as e2:
        why = "invalid or unauthorised key" if e2.code in (401, 403) else f"provider returned HTTP {e2.code}"
        return jsonify({"ok": False, "detail": f"{PROVIDERS[p]['label']} · {why}"})
    except Exception as e2:  # noqa: BLE001
        return jsonify({"ok": False, "detail": f"could not reach {PROVIDERS[p]['label']}: {type(e2).__name__}"})


@app.post("/clearkey")
def clearkey():
    sk()["value"] = ""
    sk()["provider"] = None
    _keys_save()
    return redirect(request.referrer or "/")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
