# Maal Pipeline — Operations Runbook

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install google-genai pydantic pandas openpyxl z3-solver httpx ddgs pytest pytest-asyncio
cp .env .env.local  # keep your key out of shells; edit .env directly if preferred
PYTHONPATH=src .venv/bin/python -m pipeline.run_batch --limit 10   # smoke
```

Outputs land in `output/`:
- `result.csv` / `result.xlsx` — all 252 Delivery Format columns
- `sidecar.jsonl` — per-field provenance: source URL, verbatim quote, trust tier, adversarial verdict, confidence, physics checks, triage score
- `state.jsonl` — checkpoint; delete or use `--no-resume` to restart clean
- `cache/retrieval.json` — manufacturer domain + MPN lookup cache

## Compliance scoring

```bash
PYTHONPATH=src:. .venv/bin/python eval/score.py output/result.csv
```

Reports header fidelity vs the 252 required headers, char limits, CAPS rule,
UOM spacing, fraction form, and a replay diff against the two labelled example rows.

## Full 1,000-row run

```bash
nohup env PYTHONPATH=src .venv/bin/python -m pipeline.run_batch > output/batch.log 2>&1 &
tail -f output/batch.log
```

The runner is checkpoint/resume-safe: interrupt anytime and rerun the same
command; completed rows are skipped.

### Quota reality (free tier)
- Free tier allows ~20 requests/day/model for flagship flash models.
- The client fails over across `GEMINI_MODEL_FALLBACKS` when a model's daily
  budget is exhausted (see `.env`). With N usable models you get roughly
  N x 20 requests/day -> ~10-15 rows/day per model chain on free tier.
- For a same-day full run, enable billing on the AI Studio key (~$0.30-0.60
  per 1M input tokens; full run costs roughly $2-5) and raise `RPM_LIMIT`.

## Human corrections loop

In the review queue, fix a field and POST it (or append manually):

```json
{"mfg_part_num": "DCB518ASTS06G",
 "attributes": {"Diameter": "1/2 in"},
 "output_row": {"SHORT_DESC": "Diablo DCB518ASTS06G Sanding Belt"}}
```

Rerun the batch; corrections are applied after extraction and marked
"verified by human" in provenance.

## Known limitations (by design)
- Rows whose supplier account (`Part_Manuf`) is a *distributor* (e.g. Jam
  Industrial Supply) yield no manufacturer-domain evidence; values stay
  input-tier and flagged NEEDS_REVIEW rather than fabricated.
- Belt-style dimensions (`1/2"x18"`) can mis-map to Diameter/Arbor in
  pre-extraction; the Z3 diameter>arbor check correctly flags these for
  review instead of letting them through silently.
- Descriptions are template-built from verified attributes only; marketing
  copy quality depends on extracted feature count.
