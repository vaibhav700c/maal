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

### Free-tier operation (current mode)
- Batched pipeline: ~8 rows share one extract call; audit calls only for
  rows with retrieved manufacturer evidence; classification batched 20/call.
- Observed throughput: ~40 rows/minute while quota holds -> a full 1,000-row
  catalog typically completes in under an hour when budgets allow.
- When every model in `GEMINI_MODEL_FALLBACKS` exhausts its daily budget the
  runner stops cleanly; completed rows stay checkpointed in `output/state.jsonl`.
- Auto-resume is installed via launchd (`deploy/com.maal.pipeline.plist`,
  loaded into `~/Library/LaunchAgents`): runs daily at 07:00 and picks up
  where it stopped until the catalog is complete.
- Manual controls:
    launchctl list | grep maal          # installed?
    launchctl kickstart -k gui/$UID/com.maal.pipeline   # run now
    launchctl unload ~/Library/LaunchAgents/com.maal.pipeline.plist  # disable

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
