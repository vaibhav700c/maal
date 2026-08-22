# Maal — AI-Powered Product Intelligence for Industrial Commerce

**Date**: 2026-08-22
**Status**: Approved
**Context**: Unihack challenge (Unilog). Transform messy industrial catalog rows into complete, standardized, commerce-ready product records.

## 1. Goal

Given 1,000 raw catalog rows (6 columns: `Mfg_Part_Num`, `Part_Desc`, `E1_Brand`, `Unilog_Brand`, `DIB_Brand`, `Part_Manuf`), produce the required 252-column Delivery Format output where every populated value is evidenced from a source, verified by an adversarial pass and physics constraints, and formatted deterministically to house style. A Next.js review UI exposes per-field provenance, verification verdicts, and Z3 proofs, with a human-correction loop that improves future runs.

## 2. Locked decisions

| Decision | Choice |
|---|---|
| Reference files (LOV, UOM standards, mfr list) | Not available; only the 2 provided CSVs. Canonical conventions encoded from ground-truth patterns + LLM knowledge. |
| LLM provider | Free Gemini API key (`google-genai` SDK) behind a provider-agnostic adapter. |
| Field scope | Core commerce fields deep (identity, classification, descriptions, attributes, features, UOM normalization) + web-sourced MFR URL / ref URLs / doc & image discovery. Remaining columns best-effort or blank-with-flag. |
| Deliverable surface | Batch pipeline emitting XLSX/CSV + provenance sidecar, plus Next.js review UI with download endpoints and corrections loop. |
| Sourcing hierarchy | Manufacturer-owned domains only (site = trust 1.0, manufacturer-hosted PDF docs = 0.9). Marketplaces/distributors excluded and flagged. Missing data → blank + review reason, never invented. |
| UI framework | Next.js 15 App Router, TypeScript, Tailwind. No separate backend service. |

## 3. Architecture

```
maal/
├── input/                      # provided CSVs (input + expected-output headers/examples)
├── src/pipeline/
│   ├── cleanse.py              # placeholder filter, "Name (CODE)" parser, abbreviation expansion
│   ├── classify.py             # Dept/Class/Fine, Classpath, UNSPSC (batched constrained LLM)
│   ├── retrieve.py             # domain discovery → site-scoped MPN search → trust tiers
│   ├── extract.py              # JSON-schema attribute extraction + verbatim evidence quotes
│   ├── verify_adversarial.py   # second-pass refutation of numeric/high-stakes fields
│   ├── physics.py              # Z3 constraint library; unsat-core → plain-language reasons
│   ├── format/
│   │   ├── uom.py              # approved UOM forms, number-unit spacing, fraction table
│   │   ├── descriptions.py     # deterministic builders for all 5 description types
│   │   └── emit.py             # exact 252-header XLSX/CSV writer
│   ├── confidence.py           # per-field scoring, risk-ranked triage, dedup flags
│   └── run_batch.py            # rate-limited checkpointed runner (resume-safe)
├── web/                        # Next.js review UI (reads output artifacts)
│   ├── app/page.tsx            # queue view: confidence heat, filter chips
│   ├── app/row/[id]/page.tsx   # detail: evidence quotes, verdicts, Z3 panel
│   ├── app/api/corrections/route.ts
│   └── app/api/download/route.ts
├── eval/score.py               # format-compliance %, replay diff, consistency stats
├── tests/                      # pytest unit + mocked integration
└── output/
    ├── result.xlsx | result.csv
    ├── sidecar.jsonl           # per-field provenance/verdicts/confidence
    └── corrections.jsonl       # human fixes consulted on rerun
```

### Data flow

```
row → cleanse → classify → retrieve → extract(claims+evidence)
                                            │
                     ┌──────────────────────┴─────────────┐
                     ▼                                    ▼
          adversarial verifier                         Z3 oracle
          (refute vs evidence)                  (physics/unit constraints;
                     │                          unsat-core on failure)
                     └──────────────┬─────────────────────┘
                                    ▼
                    verified attribute dict + flags
                                    ▼
              deterministic formatters (UOM rules, char limits,
              caps, title/desc formulas from ground-truth patterns)
                                    ▼
        252-col row + sidecar{source URL, quote, confidence,
        verdict, review_reason} → XLSX/CSV + JSONL → review UI
```

## 4. Pipeline stages

### 4.1 Cleanse
- Filter placeholder values exactly: `-- Unbranded --`, `-- No Unilog Brand --`, `-- No DIB Brand --` → null.
- Parse `Part_Manuf` "Freud Inc (2435)" → `{name, code}`.
- Abbreviation expansion via a growing normalization table (Milw→Milwaukee); table persists across runs (self-improving).

### 4.2 Classify (LLM, batched)
- Constrained two-stage: coarse family → Dept/Class/Fine leaf + full Classpath string + UNSPSC code.
- Batched ~20 rows/call with structured array output to conserve quota.

### 4.3 Retrieve
1. Manufacturer domain resolution (LLM proposes candidates; HTTPS probe validates).
2. Site-scoped MPN search (`site:mfr-domain MPN` via ddgs; fallback: probe common site-search URLs).
3. Collect MFR URL + up to 5 ref URLs (spec sheets, manuals). Trust tiers enforced; non-manufacturer hits excluded and logged as flags.
4. Cache keyed `(domain, mpn)`; shared across duplicate manufacturers.

### 4.4 Extract
- One structured call per row over input desc + retrieved snippets.
- Output schema: attributes `{label, value, uom}`, features[], certifications, application, includes — each with verbatim source quote + URL.
- Descriptions are NOT generated here; only facts are extracted.

### 4.5 Adversarial verifier
- Second LLM pass receives extracted claims + their evidence quotes and attempts to refute each numeric/high-stakes field (dimensions, voltage/amperage/wattage, sound level, capacities).
- Verdicts: CONFIRMED / REFUTED / UNSUPPORTED. REFUTED drops the value; UNSUPPORTED keeps it flagged for review. No silent guessing.

### 4.6 Z3 oracle (`physics.py`)
Constraint families keyed by product family, evaluated with z3-solver:
- Electrical: watts ≈ volts × amps (±10% tolerance).
- Mechanical: disc diameter > arbor bore; bearing ID < OD.
- Dimensional monotonicity (e.g., depth ≤ depth-with-door-open).
- Decimal↔fraction equivalence (0.5 must map to 1/2).
- Unit-range sanity (dBA ≠ volts; plausible ranges per unit type).
On UNSAT: unsat-core names the conflicting fields → plain-language review reason routed to the queue.

### 4.7 Deterministic formatting
- **UOM**: embedded approved-abbreviation table ("inches"/"IN./"\"" → `in`); mandatory space between number and unit; decimal→fraction lookup 1/64–63/64 (e.g., 50.25 in → 50-1/4 in).
- **Descriptions** built by Python templates from verified attributes only:
  - `INVOICE_DESC`: ≤40 chars, CAPS.
  - `MOBILE_DESC`: 60–80 chars, "Mfr Brand, Type, Series, MPN" pattern.
  - `SHORT_DESC`: title formula Brand + Series + MPN + Item Type + key attributes ("With X").
  - `LONG_DESC1`: attribute enumeration + "Additional Information:" suffix.
  - `RETAIL_DESC` / `MARKETING_DESCRIPTION`: optional short generation, clearly marked lower-trust in sidecar.
- Patterns derived from the 2 ground-truth dishwasher rows; encoded as fixtures/tests.

### 4.8 Confidence & triage
- Per-field confidence = f(source tier, adversarial verdict, Z3 result).
- Review ranking = field impact × uncertainty; filters: Needs review / Z3 failed / Refuted / Unbranded / Duplicate suspect.
- Dedup: normalized text similarity flag (cheap, no embeddings infra).
- Corrections: UI edits append to `corrections.jsonl`; pipeline consults it before LLM stages on rerun (self-improving).

## 5. Review UI

Next.js 15 (App Router, TS, Tailwind). Server components read `output/sidecar.jsonl` directly; route handlers serve corrections POST and artifact downloads.

Visual direction — deliberate, tool-like PIM/PLM density:
- Near-monochrome slate palette + single accent; status colors reserved exclusively for verification states (green=SAT/confirmed, amber=unverified, red=UNSAT/refuted).
- Tabular numerals; mono face for MPNs/values/codes; no gradient banners, no emoji, no filler copy.
- frontend-design skill loaded before any UI code to lock type scale, spacing, components.

Views:
- Queue: sortable rows, confidence heat, filter chips, triage ordering.
- Row detail: every field → value, source URL, verbatim quote, verdict badge; Z3 panel listing constraints with SAT/UNSAT and unsat-core explanation; correction editing.

## 6. Evaluation strategy

No large ground truth exists; credibility via:
1. **Format compliance** (`eval/score.py`): char limits, CAPS rule, number-unit spacing, fraction form, header fidelity vs 252 required columns — % across all 1,000 rows.
2. **Replay test**: run the 2 labelled dishwasher rows; field-level diff vs expected values.
3. **Consistency**: every description claim must exist in verified attributes; value-reuse stats.
4. **Spot-check harness**: sampled rows rendered input/output/evidence side-by-side in UI.

## 7. Testing

- Unit (pytest): UOM normalization, fraction table, description builders, Z3 families — pure functions with deterministic fixtures.
- Integration: pipeline wiring with mocked LLM + retrieval.
- Smoke: 10-row live free-tier run before full batch.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Free-tier quotas/RPM | Classification batching (~2 LLM calls/row total), adaptive backoff on 429, checkpoint/resume so runs span sessions; paid fallback costs a few dollars if needed. |
| Retrieval flakiness/blocks | Timeouts, graceful blank + review flag, cache, multiple search strategies. |
| No reference vocabularies | Conventions encoded from ground truth; canonical-name post-processing (® symbols, Inc/LLC suffixes); consistency checks. |
| Hallucinated values | Evidence-quote requirement + adversarial refutation + Z3 + blank-over-invent policy. |

## 9. Implementation phases

1. **Foundation**: repo scaffold, deps, config, provider adapter (rate limit/backoff/checkpoint-resume). Verify: unit tests green + adapter smoke test.
2. **Rules engine (no LLM)**: cleanse, UOM, description builders, emit. Verify: pytest suites + dishwasher replay compliance.
3. **Intelligence stages**: classify, retrieve, extract, verify_adversarial, physics. Verify: mocked integration + 10-row smoke.
4. **Triage & outputs**: confidence/triage/dedup, XLSX+sidecar emit, eval scorer. Verify: compliance report over 1,000 rows (sampled first).
5. **Review UI**: Next.js views + corrections/download routes. Verify: walkthrough against real sidecar.
6. **Full run & evaluation**: overnight batch, eval report, spot checks.
