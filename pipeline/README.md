# Helix Optics — market-entry data pipeline

Turns the raw case pack (13 files, 4 formats) into a validated dataset, a
ranked market recommendation, an interactive run report, and the inputs of the
Excel model — in under one second, with zero manual retyping.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py            # full run  →  data/out/  (report.html, csvs, manifest)
.venv/bin/python run.py --eval     # score the extractor against the golden set (28/28)
.venv/bin/python -m src.excel      # rebuild the Excel model from the dataset
.venv/bin/python -m src.deck       # rebuild the deck from the dataset
.venv/bin/python app.py            # web front-door → http://127.0.0.1:8765
                                   # upload documents, pick AI mode, run, read the report
```

## Design: deterministic core, AI at the edges, evidence everywhere

Every number in the dataset carries provenance: value, source file, extraction
method (`DET` / `LLM` / `MANUAL` / `DERIVED`), and the pattern or quote that
produced it. AI involvement is not a setting someone picked — it is a
per-field decision the pipeline makes, and every escalation is logged.

The escalation ladder (per FIELD, not per file):

1. **Structured read** — CSV/XLSX cells, HTML tables. AI never touches these.
2. **Pattern extraction** — regexes over normalised document text for numbers
   that live in prose ("a reimbursed price in the order of EUR 215…").
3. **LLM text fallback** (`--ai auto`, default) — fires only for fields 1–2
   cannot resolve; temperature 0, must quote its evidence sentence, response
   validated against the schema before it may enter the dataset
   ("the model proposes, the schema disposes"). Responses are cached by
   content hash, so re-runs are deterministic and free.
4. **LLM vision fallback** — only for files with no text layer at all.

For THIS pack, Tier A resolves 100% of schema fields → the manifest records
`llm_calls: 0, cost €0.00`. `--ai off` proves it: same output, gaps listed
explicitly. `--ai max` adds an audit pass in which the model re-checks the
deterministic extractions.

## The seven stages (mapping the brief 1:1)

| Brief stage | Module | What it does |
|---|---|---|
| 1 Read natively | `src/stage1_read.py` | pdfplumber / openpyxl / BeautifulSoup / csv readers; per-file status board |
| 2 Extract | `src/stage2_extract.py` | patterns in `config/schema.yaml` + the AI ladder above |
| 3 One schema | `src/stage3_schema.py` | precedence (national report → landscape), canonical dataset, derived fields, `overrides.yaml` |
| 4 Facilities | `src/stage4_facilities.py` | dedup rule below — 3,236 raw records → 228 real units |
| 5 Compare sources | `src/stage5_reconcile.py` | agreement matrix, AGREE/DISAGREE per parameter |
| 6 Arithmetic checks | `src/stage6_validate.py` | checks-as-data (`config/checks.yaml`) — catches the impossible competitor claim |
| 7 Conclusion | `src/stage7_conclude.py` | 5-year engine over all four markets → ranking + evidence gaps |

## The deduplication rule (stage 4, stated)

1. Repair unambiguous column-shifted rows (6 in the Poland CSV), else exclude and report.
2. Normalise: diacritics stripped; Germany's 126 **monthly** capacities ×12;
   `ENDO`/`PATH`/"Endoscopy Unit" → one label.
3. Entity = **(country, canonical institution, unit nº)** — register IDs are
   untrusted (the same unit appears under 10+ different ids).
4. Master-registry names → national canonical names via a curated alias map
   (`config/aliases.yaml`), fuzzy-seeded (rapidfuzz), human-reviewed;
   unresolved names fall back to token_set_ratio ≥ 90.
5. National register is authoritative; master rows corroborate or are added as
   `master-only`.
6. Type by majority vote (208/228 units appear under both labels); capacity as
   the **median with min–max spread reported**. Disagreements are surfaced,
   never silently resolved.

## Quality harness

- **Golden evals** — `config/golden.yaml`, 28 hand-verified values; `--eval`
  scores the extractor (currently 28/28). Never edit a golden value to make a
  test pass; fix the extractor.
- **Run manifest** — `data/out/manifest.json`: input SHA-256s, stage timings,
  AI calls/tokens/cost, extraction mix.
- **Overrides, not edits** — humans correct values in `overrides.yaml`
  (value + reason + author); applied last, badged `MANUAL` everywhere,
  survive every re-run. Output files are regenerated and never hand-edited.
- **Closed-world stance** — the pack is the source of truth; no external data
  is mixed in. The report's evidence-gap cards carry the research plans a
  production sourcing workflow would run — the button is deliberately
  disabled here, and even in production found documents would land in
  quarantine until a human approves them.

## Running it on market #5 (…#14)

Add an entry to `config/markets.yaml` (files + formats + column names for the
facility register) and drop the files in `data/raw/`. If the new country's
documents phrase a parameter differently, either add a regex to
`config/schema.yaml` or let the Tier-B fallback absorb the new layout. Checks
and the model need no changes. Nothing else.

## How this was built (AI-native, on purpose)

Built with Claude (Claude Code) as the pair: the AI drafted readers, patterns
and templates; the human owned the decisions — the dedup rule, the modelling
assumptions, the checks, and the recommendation. The same division of labour
the pipeline itself enforces: AI does the messy reading, deterministic code
does the arithmetic, humans own the judgment.
