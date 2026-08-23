# Runway — a market-entry copilot

A case-study build: given a messy pack of market documents (PDF / XLSX / HTML /
CSV), a seven-stage pipeline produces a validated dataset, an evidence report,
a ranked market recommendation, a live five-year Excel model and a deck —
deterministic first, AI only at the edges, provenance on every number.

**Showcase (static):** the `docs/` site — landing page, web deck, evidence
report, and a grounded chat that answers only from the validated dataset.

**The product (local app):** workspaces — one folder per market assessment.
Drop documents in, roles are auto-detected (anything unrecognised is flagged,
never silently ignored), run the pipeline, browse per-run reports, chat with
the results, apply audited overrides.

## Run it anywhere

```bash
git clone <this repo> && cd <repo>
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt
cd pipeline && ../.venv/bin/python app.py     # → http://127.0.0.1:8765
```

Create a workspace, drop your documents, run. An Anthropic API key (optional,
session-only) enables the AI fallback tiers and the chat.

The source documents of the original case are deliberately not in this repo;
drop your own pack into a workspace. See `pipeline/README.md` for the
architecture, the dedup rule, the AI escalation ladder, and the eval harness.
