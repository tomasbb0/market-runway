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


def extract_field(doc_text: str, market: str, param: str, unit: str, mode: str) -> dict | None:
    """Ask the model to extract one field, quoting its evidence sentence.

    Returns {value, quote, confidence} or None (unavailable / rejected).
    """
    global calls_made, tokens_used
    if mode == "off":
        return None
    model = MODEL_CASCADE[0]
    prompt = (
        f"From the document below, extract `{param}` (unit: {unit}) for {market}. "
        'Reply ONLY with JSON {"value": <number>, "quote": "<the exact source sentence>", '
        '"confidence": <0-1>}. If absent reply {"value": null}.\n\n---\n' + doc_text[:12000]
    )
    ck = _cache_key(model, prompt)
    if ck.exists():
        return _validate(json.loads(ck.read_text()))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None  # no key in this environment - field stays unresolved
    import anthropic  # imported lazily; not needed for cached / Tier-A-complete runs

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model, max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    calls_made += 1
    tokens_used += resp.usage.input_tokens + resp.usage.output_tokens
    raw = resp.content[0].text
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
