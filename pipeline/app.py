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
app = Flask(__name__)
app.secret_key = os.environ.get("RUNWAY_SECRET") or os.urandom(24).hex()
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024   # 30 MB per upload batch
RUNWAY_PASS = os.environ.get("RUNWAY_PASS", "")

KEYS: dict = {}   # per-browser-session provider keys; never written to disk
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
    return (f'<!doctype html><meta charset="utf-8"><title>Runway</title>{STYLE}'
            '<div style="min-height:100svh;display:grid;place-content:center;gap:14px;text-align:center">'
            '<div class="eyebrow"><span class="tag"></span>RUNWAY · PRIVATE DESK</div>'
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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400..700;1,400&family=Noto+Serif:ital,wght@0,400;0,600;1,400;1,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
 :root{--bg:#f9f7f5;--sf:#ffffff;--ink:#1d2939;--deep:#374b60;--soft:#667085;--line:#e6e1da;
   --acc:#ff4200;--accdark:#c12d00;--softblue:#bdd2e0;--softblue2:#e6eef3;--bordeaux:#661439;
   --tan:#ad836c;--cream2:#f4f1ec;--ok:#374b60;--okbg:#e6eef3;--warnbg:#f6ead9;--failbg:#f8e3dc}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.55 'Instrument Sans',system-ui,sans-serif}
 a{color:var(--deep)} .serif{font-family:'Noto Serif',serif} .mono{font-family:'IBM Plex Mono',monospace}
 nav{display:flex;align-items:center;gap:10px;padding:16px 26px;border-bottom:1px solid var(--line);background:var(--sf)}
 nav .dot{width:11px;height:11px;border-radius:50%;background:var(--acc)}
 nav b{font-size:16px;letter-spacing:-.01em} nav .crumb{color:var(--soft);font-size:14px}
 nav .right{margin-left:auto;display:flex;gap:14px;align-items:center;font-size:13.5px}
 .wrap{max-width:1060px;margin:0 auto;padding:34px 24px 80px;display:flex;flex-direction:column;gap:22px}
 h1{font-size:32px;margin:0;letter-spacing:-.02em;font-weight:650}
 h1 em{font-family:'Noto Serif',serif;font-style:italic;font-weight:300;color:var(--acc)}
 h2{font-size:16px;margin:0 0 12px;letter-spacing:-.01em}
 .eyebrow{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:var(--tan)}
 .card{background:var(--sf);border:1px solid var(--line);border-radius:14px;padding:20px 22px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
 .folder{display:block;background:var(--sf);border:1px solid var(--line);border-radius:14px;padding:18px;
   text-decoration:none;color:var(--ink);transition:border-color .15s, transform .15s}
 .folder:hover{border-color:var(--acc);transform:translateY(-2px)}
 .folder .tab{width:44px;height:10px;background:var(--softblue);border-radius:4px 4px 0 0;margin-bottom:-1px}
 .folder .body{background:var(--cream2);border-radius:0 8px 8px 8px;padding:12px 12px 10px;min-height:74px}
 .folder b{font-size:15.5px} .folder .meta{font-size:12.5px;color:var(--soft);margin-top:4px;line-height:1.5}
 .folder.new{border-style:dashed;color:var(--soft)} .folder.new:hover{color:var(--acc)}
 button,.btn{font:600 14px 'Instrument Sans';border-radius:9px;border:1px solid var(--line);
   padding:9px 16px;background:var(--sf);color:var(--ink);cursor:pointer;text-decoration:none;display:inline-block}
 button.primary,.btn.primary{background:var(--acc);border-color:var(--acc);color:#fff}
 button.primary:hover,.btn.primary:hover{background:var(--accdark)}
 button.ghost{border:none;background:none;color:var(--soft);padding:4px 6px}
 button.ghost:hover{color:var(--accdark)}
 input[type=text],input[type=password],select{font:14px 'Instrument Sans';border:1px solid var(--line);
   border-radius:9px;padding:9px 12px;background:var(--sf);color:var(--ink)}
 .chip{font-family:'IBM Plex Mono',monospace;font-size:10.5px;border-radius:99px;padding:2px 9px;white-space:nowrap}
 .chip.role{background:var(--softblue2);color:var(--deep)}
 .chip.warn{background:var(--warnbg);color:#8a5a10}
 .chip.skip{background:var(--cream2);color:var(--soft)}
 .chip.fail{background:var(--failbg);color:var(--accdark)}
 .chip.ok{background:var(--okbg);color:var(--deep)}
 .filerow{display:flex;align-items:center;gap:10px;padding:7px 4px;border-bottom:1px solid var(--cream2);font-size:13.5px}
 .filerow:last-child{border-bottom:none}
 .filerow .name{font-family:'IBM Plex Mono',monospace;font-size:12.5px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .filerow .sz{color:var(--soft);font-size:12px}
 .drop{display:block;border:1.5px dashed var(--softblue);border-radius:11px;background:var(--softblue2);
   padding:20px;text-align:center;cursor:pointer;color:var(--deep);font-weight:600}
 .drop.drag{background:var(--softblue)} .drop input{display:none} .drop small{display:block;font-weight:400;color:var(--soft);margin-top:3px}
 .runrow{display:flex;align-items:center;gap:12px;padding:11px 4px;border-bottom:1px solid var(--cream2)}
 .runrow:last-child{border-bottom:none}
 .runrow .stamp{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--soft)}
 .runrow .rec{font-weight:600}
 .hint{font-size:13px;color:var(--soft)}
 .two{display:grid;grid-template-columns:1.25fr 1fr;gap:18px;align-items:start}
 @media(max-width:860px){.two{grid-template-columns:1fr}}
 pre.log{background:#1d2939;color:#e8e2d9;border-radius:12px;padding:16px;font:12.5px 'IBM Plex Mono',monospace;overflow-x:auto;line-height:1.55;white-space:pre-wrap}
 .pb{height:6px;background:var(--line);border-radius:99px;overflow:hidden;margin:12px 0 4px}
 .pb i{display:block;height:100%;width:4%;background:linear-gradient(90deg,var(--acc),#ff7a4d);
   border-radius:99px;transition:width .5s ease;position:relative;overflow:hidden}
 .pb i::after{content:"";position:absolute;inset:0;
   background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);
   animation:pbs 1.1s linear infinite}
 .pb.done i{background:#2F7D4F} .pb.done i::after,.pb.fail i::after{animation:none}
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
 .banner{background:var(--softblue2);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:11px;padding:13px 16px;font-size:14px}
 /* chat */
 .chatbox{display:flex;flex-direction:column;gap:12px;max-width:820px;margin:0 auto}
 .msg{border-radius:14px;padding:12px 16px;max-width:88%;font-size:14.5px;white-space:pre-wrap}
 .msg.user{background:var(--deep);color:#fff;align-self:flex-end}
 .msg.ai{background:var(--sf);border:1px solid var(--line);align-self:flex-start}
 .msg.ai .ov{background:var(--cream2);border:1px solid var(--line);border-radius:9px;padding:10px 12px;
   font:12.5px 'IBM Plex Mono',monospace;margin-top:8px;white-space:pre-wrap}
 .chatinput{display:flex;gap:10px;position:sticky;bottom:0;background:var(--bg);padding:12px 0}
 .chatinput input[type=text]{flex:1}
</style>"""


def nav(crumbs=""):
    key = sk()["value"]
    prov = PROVIDERS.get(sk().get("provider") or "", {}).get("label", "key")
    key_chip = (f'<span class="chip ok">{prov} key ·…{html.escape(key[-4:])}</span>'
                '<form method="post" action="/clearkey" style="display:inline">'
                '<button class="ghost" title="Forget the API key">clear</button></form>'
                if key else
                '<button class="chip skip" id="addkey" style="cursor:pointer;border:none" '
                'onclick="navKey()">no API key — add</button>')
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
    return (f'<nav><span class="dot"></span><b><a href="/" style="text-decoration:none;color:inherit">Runway</a></b>'
            f'<span class="crumb">{crumbs}</span><span class="right">{key_chip}</span></nav>')


def page(title, body, crumbs=""):
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
    <div><div class="eyebrow">Runway · the market-entry desk</div>
    <h1>Every market, <em>one folder away.</em></h1>
    <p class="hint" style="max-width:60ch">Drop a market pack into a workspace, run the seven-stage pipeline,
    and get a validated dataset, a ranked recommendation and a full evidence report. Deterministic first;
    AI only where it earns its place.</p></div>
    <div class="grid">{cards}</div>
    <dialog id="newws" style="border:1px solid var(--line);border-radius:14px;padding:22px;max-width:380px">
      <form method="post" action="/new" style="display:flex;flex-direction:column;gap:12px">
        <h2 style="margin:0">New workspace</h2>
        <input type="text" name="name" placeholder="e.g. Spain 2027" required autofocus>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button type="button" onclick="this.closest('dialog').close()">Cancel</button>
          <button class="primary">Create</button></div>
      </form></dialog>"""
    return page("Runway — workspaces", body)


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
        roles[f] = ("reference — not analysed", "skip")
    for f in man["unassigned"]:
        roles[f] = ("unassigned — not analysed", "warn")
    return roles


@app.get("/w/<ws_name>")
def workspace(ws_name):
    ws = ws_dir(ws_name)
    if not ws.exists():
        return redirect("/")
    roles = _manifest_roles(ws)
    rows = ""
    for p in sorted((ws / "raw").glob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        label, cls = roles.get(p.name, ("unassigned", "warn"))
        rows += (f'<div class="filerow"><span class="name" title="{html.escape(p.name)}">{html.escape(p.name)}</span>'
                 f'<span class="chip {cls}">{html.escape(label)}</span>'
                 f'<span class="sz">{p.stat().st_size//1024} KB</span>'
                 f'<form method="post" action="/w/{ws.name}/files/delete" onsubmit="return confirm(\'Delete {html.escape(p.name)}?\')">'
                 f'<input type="hidden" name="f" value="{html.escape(p.name)}">'
                 f'<button class="ghost" title="Delete">✕</button></form></div>')
    if not rows:
        rows = '<div class="hint" style="padding:8px 4px">No documents yet — drop the pack above.</div>'
    unassigned = [f for f, (_, c) in roles.items() if c == "warn"]
    warn_banner = (f'<div class="banner">⚠ {len(unassigned)} file(s) are <b>not being analysed</b> '
                   f'(no role matched): {", ".join(html.escape(u) for u in unassigned)}. Rename them to include '
                   f'their market and kind (e.g. <span class="mono">Screening_Report_Spain.pdf</span>), or delete them.</div>'
                   if unassigned else "")

    runrows = ""
    for run in list_runs(ws):
        rec, chip = "—", '<span class="chip skip">no result</span>'
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
        runrows += (f'<div class="runrow"><span class="stamp">{ts}</span>'
                    f'<span class="rec" style="flex:1">{rec}</span>{chip}'
                    f'<a class="btn" href="/w/{ws.name}/report/{run.name}">Report</a></div>')
    if not runrows:
        runrows = '<div class="hint" style="padding:8px 4px">No runs yet.</div>'

    key = sk()["value"]
    key_field = (
        '<input type="password" name="api_key" id="kf" autocomplete="off" '
        + ('placeholder="key set for this session — paste another to replace" '
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
        'st.style.color=j.ok?"#2F7D4F":"#c12d00";st.textContent=j.detail;}'
        '</script>')
    body = f"""
    <div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap">
      <h1 style="font-size:26px">{ws.name}</h1>
      <a href="/w/{ws.name}/chat" class="btn">Ask the data<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px;vertical-align:-2px;margin-left:5px"><path d="M7 17L17 7M9 7h8v8"/></svg></a>
      <form method="post" action="/w/{ws.name}/files/clean" style="margin-left:auto"
        onsubmit="return confirm('Remove ALL documents from this workspace?')">
        <button class="ghost">Clean raw files</button></form>
    </div>
    {warn_banner}
    <div class="two">
      <div class="card">
        <h2>Documents</h2>
        <form method="post" action="/w/{ws.name}/files/upload" enctype="multipart/form-data" id="upf">
          <label class="drop" id="drop">Drop the pack here — or click to choose
            <small>PDF · XLSX · HTML · CSV — roles are auto-detected, and anything unrecognised is flagged, never silently ignored</small>
            <input type="file" name="docs" multiple id="fi"></label>
        </form>
        <div style="margin-top:10px">{rows}</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:18px">
        <form class="card" method="post" action="/w/{ws.name}/run" style="display:flex;flex-direction:column;gap:10px">
          <h2 style="margin:0">Run the pipeline</h2>
          {key_field}
          <button class="primary" name="ai" value="auto" style="text-align:left">
            <span style="font-size:15px">Glide run</span><br>
            <span style="font-weight:400;font-size:11.5px;opacity:.85">deterministic core; AI only where patterns fail · seconds, ~€0</span></button>
          <button name="ai" value="max" style="text-align:left;border-color:var(--deep)">
            <span style="font-size:15px;color:var(--acc)">Afterburner run</span><br>
            <span style="font-weight:400;font-size:11.5px;color:var(--soft)">Glide + a frontier model audits every extracted value (needs a key)</span></button>
          <span class="hint">read native → extract → one schema → dedupe → compare → checks → conclusion
           · <button class="ghost" name="ai" value="off" style="font-size:11px;padding:0">or run with AI fully off</button></span>
        </form>
        <div class="card"><h2>Runs</h2>{runrows}</div>
      </div>
    </div>
    <script>
     const drop=document.getElementById('drop'),fi=document.getElementById('fi'),f=document.getElementById('upf');
     fi.addEventListener('change',()=>f.submit());
     ;['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{{ev.preventDefault();drop.classList.add('drag')}}));
     ;['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{{ev.preventDefault();drop.classList.remove('drag')}}));
     drop.addEventListener('drop',ev=>{{fi.files=ev.dataTransfer.files;f.submit()}});
    </script>"""
    return page(f"{ws.name} — Runway", body, f"/ {ws.name}")


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
        head = page("Run — Runway", "", f"/ {ws.name} / run")
        head = head.split('<div class="wrap">')[0]
        yield head + (
            f'<div class="wrap"><div><div class="eyebrow">{ws.name} · pipeline run · {mode_label}</div>'
            '<h1 style="font-size:26px" id="rt">Running…</h1>'
            '<div class="pb" id="pb"><i></i></div></div>'
            '<script>function bar(n){document.querySelector("#pb i").style.width='
            'Math.min(96,Math.round(n/8*100))+"%"}</script>'
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
        actions = (f'<a class="btn primary" href="/w/{ws.name}/report/{t["run"]}">Open the report →</a>'
                   f'<a class="btn" href="/w/{ws.name}/chat">Ask the data</a>' if ok and t["run"] else "")
        yield ('</pre><div style="display:flex;gap:10px;margin-top:12px">' + actions
               + f'<a class="btn" href="/w/{ws.name}">← workspace</a></div>'
               + '<script>document.getElementById("rt").textContent='
               + ('"Run complete"' if ok else '"Run failed"')
               + f';document.getElementById("pb").classList.add("{"done" if ok else "fail"}");'
               + 'document.querySelector("#pb i").style.width="100%";</script></div></body></html>')

    return Response(stream_with_context(generate()), mimetype="text/html",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
    return send_file(f)


# ---------------------------------------------------------------- chat
def _grounding(ws: Path) -> tuple[str, str]:
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
GROUNDING RULES — absolute:
- Answer ONLY from the JSON dataset below (the pipeline's validated output). If something is not
  in it, say "not in the validated dataset" — never guess, never use outside knowledge for figures.
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
        keyrow = ('<input type="password" id="key" placeholder="API key — Anthropic, OpenAI or Gemini" '
                  'style="font-family:monospace;font-size:12.5px" oninput="detect()" onchange="verifyKey(this)">')
    banner = (f'grounded on run <b class="mono">{run_name}</b>; answers come only from the validated dataset'
              if run_name else "no runs yet. Run the pipeline first, then chat about its results")
    body = f"""
    <div class="chatbox">
     <div><div class="eyebrow">{ws.name} · ask the data</div>
      <h1 style="font-size:24px">Chat with the <em>validated</em> dataset</h1>
      <div class="hint" style="margin-top:6px">{banner}. To change a value, just say so — I'll draft an override
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
     function render(role,text){{
       const div=document.createElement('div');div.className='msg '+(role==='user'?'user':'ai');
       const m=text.match(/```override\\n([\\s\\S]*?)```/);
       let bodyTxt=text.replace(/```override\\n[\\s\\S]*?```/,'').trim();
       div.innerHTML=esc(bodyTxt);
       if(m){{const ov=document.createElement('div');ov.className='ov';ov.textContent=m[1].trim();
         const b=document.createElement('button');b.className='primary';b.style.marginTop='8px';
         b.textContent='Apply override & re-run';b.onclick=()=>applyOv(m[1].trim(),b);
         div.appendChild(ov);div.appendChild(b);}}
       msgs.appendChild(div);div.scrollIntoView({{behavior:'smooth',block:'end'}});
     }}
     async function send(){{
       const q=document.getElementById('q');const text=q.value.trim();if(!text)return;q.value='';
       render('user',text);hist.push({{role:'user',content:text}});
       const keyEl=document.getElementById('key');
       const r=await fetch('/w/{ws.name}/chat/send',{{method:'POST',headers:{{'Content-Type':'application/json'}},
         body:JSON.stringify({{messages:hist,model:document.getElementById('model').value,
                              key:keyEl?keyEl.value:null}})}});
       const j=await r.json();
       if(j.error){{render('ai','⚠ '+j.error);return}}
       render('ai',j.text);hist.push({{role:'assistant',content:j.text}});
     }}
     async function applyOv(block,btn){{
       btn.disabled=true;btn.textContent='Applying & re-running…';
       const r=await fetch('/w/{ws.name}/override',{{method:'POST',headers:{{'Content-Type':'application/json'}},
         body:JSON.stringify({{block}})}});
       const j=await r.json();
       btn.textContent=j.ok?'Applied ✓ — open the new report':'Failed: '+j.error;
       if(j.ok){{btn.onclick=()=>location.href='/w/{ws.name}/report/'+j.run;btn.disabled=false}}
     }}
    </script>"""
    return page(f"Chat — {ws.name}", body, f"/ {ws.name} / chat")


@app.post("/w/<ws_name>/chat/send")
def chat_send(ws_name):
    ws = ws_dir(ws_name)
    data = request.get_json(force=True)
    if data.get("key"):
        sk()["value"] = data["key"].strip()
        sk()["provider"] = detect_provider(sk()["value"])
    if not sk()["value"]:
        return jsonify({"error": "No API key set. Paste an Anthropic, OpenAI or Gemini key next to the message box."})
    provider = sk().get("provider")
    if not provider:
        return jsonify({"error": "Key format not recognised. Expected sk-ant-… (Anthropic), sk-… (OpenAI) or AIza… (Gemini)."})
    grounding, run_name = _grounding(ws)
    if not grounding:
        return jsonify({"error": "No completed run in this workspace yet."})
    models = PROVIDERS[provider]["models"]
    model = data.get("model") if data.get("model") in models else next(iter(models))
    try:
        msgs = [{"role": m["role"], "content": m["content"]}
                for m in data.get("messages", []) if m.get("role") in ("user", "assistant")][-20:]
        text = _chat_call(provider, sk()["value"], model, SYSTEM + grounding, msgs)
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
    return redirect(request.referrer or "/")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
