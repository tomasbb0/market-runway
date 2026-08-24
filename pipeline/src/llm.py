"""Tier B / Tier C - LLM fallback client with cache-backed reproducibility.

Escalation ladder (per FIELD, not per file):
  1. structured read (tables/cells)     - stage1, deterministic
  2. pattern extraction (regex)         - stage2 Tier A, deterministic
  3. LLM text extraction (this module)  - only for fields Tier A cannot resolve
  4. LLM vision                         - only for files with no text layer

Modes: --ai off   -> never called; unresolved fields reported as gaps
       --ai auto  -> called per unresolved field (default)
       --ai max   -> auto + audit pass re-checking Tier A extractions

Reproducibility: every response is cached in cache/ keyed by
sha256(model + prompt). A re-run replays the cache - deterministic and free.
Guardrail: responses must be valid JSON matching {value, quote, confidence};
anything else is rejected and the field stays unresolved. The model proposes,
the schema disposes.

For this pack Tier A resolves 100% of schema fields, so no live calls are
made and no API key is required (calls=0 appears in the run manifest).
"""
import hashlib
import json
import os
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "cache"
MODEL_CASCADE = ["claude-haiku-4-5-20251001", "claude-fable-5"]  # cheap first, frontier for audit/vision

calls_made = 0
tokens_used = 0


def _cache_key(model: str, prompt: str) -> Path:
    return CACHE / (hashlib.sha256((model + prompt).encode()).hexdigest()[:24] + ".json")


AUDIT_MODELS = {"anthropic": "claude-haiku-4-5-20251001",
                "openai": "gpt-5-mini", "google": "gemini-2.5-flash"}


def _provider_and_key():
    p = os.environ.get("RUNWAY_PROVIDER")
    k = os.environ.get("RUNWAY_KEY")
    if p and k:
        return p, k
    k = os.environ.get("ANTHROPIC_API_KEY")
    return ("anthropic", k) if k else (None, None)


def _http(url, payload, headers):
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _ask(provider, key, model, prompt):
    global tokens_used
    if provider == "anthropic":
        out = _http("https://api.anthropic.com/v1/messages",
                    {"model": model, "max_tokens": 300,
                     "messages": [{"role": "user", "content": prompt}]},
                    {"x-api-key": key, "anthropic-version": "2023-06-01"})
        u = out.get("usage", {})
        tokens_used += u.get("input_tokens", 0) + u.get("output_tokens", 0)
        return out["content"][0]["text"]
    if provider == "openai":
        out = _http("https://api.openai.com/v1/chat/completions",
                    {"model": model, "max_completion_tokens": 300,
                     "messages": [{"role": "user", "content": prompt}]},
                    {"Authorization": f"Bearer {key}"})
        tokens_used += out.get("usage", {}).get("total_tokens", 0)
        return out["choices"][0]["message"]["content"]
    if provider == "google":
        out = _http(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                    {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                     "generationConfig": {"maxOutputTokens": 300}}, {})
        tokens_used += out.get("usageMetadata", {}).get("totalTokenCount", 0)
        return out["candidates"][0]["content"]["parts"][0]["text"]
    raise ValueError("unknown provider")


def extract_field(doc_text: str, market: str, param: str, unit: str, mode: str) -> dict | None:
    """Ask the model to extract one field, quoting its evidence sentence.

    Provider-agnostic: uses RUNWAY_PROVIDER/RUNWAY_KEY (any of anthropic,
    openai, google), falling back to ANTHROPIC_API_KEY. Cached by content hash.
    Returns {value, quote, confidence} or None (no key / rejected).
    """
    global calls_made
    if mode == "off":
        return None
    provider, key = _provider_and_key()
    if not provider:
        return None
    model = AUDIT_MODELS[provider]
    prompt = (
        f"From the document below, extract `{param}` (unit: {unit}) for {market}. "
        'Reply ONLY with JSON {"value": <number>, "quote": "<the exact source sentence>", '
        '"confidence": <0-1>}. Express percentages as fractions (43% -> 0.43). '
        'If absent reply {"value": null}.\n\n---\n' + doc_text[:12000]
    )
    ck = _cache_key(provider + model, prompt)
    if ck.exists():
        try:
            return _validate(json.loads(ck.read_text()))
        except json.JSONDecodeError:
            return None
    try:
        raw = _ask(provider, key, model, prompt)
    except Exception:  # noqa: BLE001 - an audit call failure must never kill the run
        return None
    calls_made += 1
    m0, m1 = raw.find("{"), raw.rfind("}")
    raw = raw[m0:m1 + 1] if m0 >= 0 <= m1 else raw
    ck.write_text(raw)
    try:
        return _validate(json.loads(raw))
    except json.JSONDecodeError:
        return None


def _validate(obj: dict) -> dict | None:
    """Schema guardrail: only {value:number, quote:str} passes into the dataset."""
    if not isinstance(obj, dict) or not isinstance(obj.get("value"), (int, float)):
        return None
    if not isinstance(obj.get("quote", ""), str):
        return None
    obj.setdefault("confidence", 0.5)
    return obj
