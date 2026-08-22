# Maal — AI-Powered Product Intelligence for Industrial Commerce

Turns messy industrial catalog rows into complete, commerce-ready product records.
Every value is extracted with verbatim evidence, audited by an adversarial LLM pass,
validated by a Z3 physics oracle, formatted deterministically to house style, and
exposed in a review console with per-field provenance.

Built for the Unilog challenge: 6-column input (`Mfg_Part_Num`, `Part_Desc`, brand
placeholders, supplier) → all 252 Delivery Format columns.

## How it works

```
row → cleanse → classify → retrieve(mfr sites only) → extract(+evidence quotes)
                                       │
                    ┌──────────────────┴─────────────┐
                    ▼                                ▼
          adversarial verifier                  Z3 physics oracle
          (refute vs evidence)            (P=V×I, ID<OD, unit ranges;
                    │                      unsat-core → plain reason)
                    └────────────┬─────────────────┘
                                 ▼
        deterministic formatters (UOM rules, char limits, CAPS,
        title/description templates — no free-form generation)
                                 ▼
   result.xlsx / result.csv (252 headers) + sidecar.jsonl provenance
                                 ▼
                     Next.js review console
```

## Setup

```bash
cd maal
python3 -m venv .venv
.venv/bin/pip install google-genai pydantic pandas openpyxl z3-solver httpx ddgs pytest pytest-asyncio
cp .env.example .env         # then edit .env with your Gemini API key
```

`.env` keys:

| Key | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio key (free tier works) |
| `GEMINI_MODEL` | Primary model (e.g. `gemini-3.1-flash-lite`) |
| `GEMINI_MODEL_FALLBACKS` | Comma list; client fails over when a model's daily quota runs out |
| `EXTRACT_BATCH` | Rows sharing one extraction call (default 8) |
| `RPM_LIMIT` | Requests-per-minute throttle (default 15) |

## Run the pipeline

```bash
# smoke: first 10 rows
PYTHONPATH=src .venv/bin/python -m pipeline.run_batch --limit 10 --no-resume

# full catalog from a given input file
PYTHONPATH=src .venv/bin/python -m pipeline.run_batch --input path/to/input.csv --no-resume --state /tmp/state.jsonl

# resume an interrupted run (same command, drop --no-resume)
PYTHONPATH=src .venv/bin/python -m pipeline.run_batch
```

Outputs land in `output/`:

| File | Contents |
|---|---|
| `result.csv` / `result.xlsx` | All 252 Delivery Format columns |
| `sidecar.jsonl` | Per-field source URL, verbatim quote, trust tier, adversarial verdict, confidence, Z3 checks, triage score |
| `state.jsonl` | Checkpoint; reruns skip completed rows |
| `corrections.jsonl` | Human fixes applied on the next run |

Free-tier behavior: batched calls (~8 rows/call), audit skipped where no
manufacturer evidence exists, multi-model failover, graceful stop when every
model's daily budget is spent — rerun later and it continues where it stopped.
A daily auto-resume job is available: `deploy/com.maal.pipeline.plist`
(copy to `~/Library/LaunchAgents/`, `launchctl load …`, runs 07:00 daily).

## Score the output

```bash
# format compliance: header fidelity, char limits, CAPS rule, UOM spacing,
# fraction forms, replay diff vs the two labelled example rows
PYTHONPATH=src:. .venv/bin/python eval/score.py output/result.csv

# recompute flags/triage/artifacts from checkpoints without any API calls
PYTHONPATH=src:. .venv/bin/python eval/rescore.py
```

## Review console

```bash
cd web
npm install
npm run build && npm start     # http://localhost:3000
# or hot-reload during development:
npm run dev
```

- **Queue** — risk-ranked rows, triage meters, filter chips (needs review / physics failed / duplicate suspects)
- **Row detail** — identity, five description formats, attribute ledger with QC stamps (`[MFR DOC · CONFIRMED · 0.75]`), expandable evidence quotes, Z3 dossier with plain-language unsat reasons
- **Corrections** — fix a value in the UI; it lands in `output/corrections.jsonl` and the next pipeline run marks it "verified by human"
- **Downloads** — `result.csv`, `result.xlsx`, `sidecar.jsonl`

## Tests

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/ -q
```

69 tests cover cleansing, UOM/fraction math, description builders, emit fidelity,
Z3 constraint families, classification/extraction parsing, adversarial policy,
confidence/triage/dedup, failover, and end-to-end orchestration with mocked LLMs.

## Repository layout

```
src/pipeline/       enrichment stages, formatters, runner
web/                Next.js review console
eval/               compliance scorer + offline rescore
input/              sample dataset + expected-output headers
deploy/             launchd plist for scheduled auto-resume
docs/ops.md         operations runbook (quotas, corrections, troubleshooting)
docs/superpowers/   design spec + implementation plans
```

## Sourcing policy

Product data comes only from manufacturer-owned domains (site = trust 1.0,
manufacturer-hosted PDFs = 0.9). Marketplaces and distributor sites are excluded
and flagged. When nothing can be verified, values stay input-derived and flagged —
never fabricated.
