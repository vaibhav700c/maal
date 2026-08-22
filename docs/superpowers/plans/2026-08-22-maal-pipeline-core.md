# Maal Enrichment Pipeline Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Batch pipeline turning 1,000 messy catalog rows into all-252-column Delivery Format records with evidence-backed, physics-verified, deterministically formatted values + provenance sidecar.

**Architecture:** Python CLI pipeline (cleanse → classify → retrieve → extract → adversarial verify → Z3 → deterministic formatters → triage/emit) writing XLSX/CSV + JSONL sidecar; provider-agnostic Gemini adapter; checkpoint/resume batch runner. Next.js review UI ships in a separate plan.

**Tech Stack:** Python 3.11+, pydantic v2, google-genai, pandas/openpyxl, z3-solver, httpx, ddgs, pytest/pytest-asyncio.

## Global Constraints
- Output headers: read verbatim at runtime from `input/Unihack_ Expected Output - Delivery Format.csv` header row (252 columns). Never hardcode/rename.
- Placeholders filtered exactly: `-- Unbranded --`, `-- No Unilog Brand --`, `-- No DIB Brand --` → null.
- UOM rule: approved abbreviation + mandatory space between number and unit (`24 in`) everywhere EXCEPT `INVOICE_DESC` which is compact CAPS ≤40 chars (ground-truth style `50-1/4IN`).
- Fractions: nearest n/64 reduced by gcd; mixed form `50-1/4`; decimal↔fraction equivalence enforced.
- Sourcing: manufacturer-owned domains only (tier 1.0 page, 0.9 PDF); marketplace hosts blocked+flagged; missing data → blank + flag, never invented.
- LLM budget ~2 calls/row + amortized batched classification (~20 rows/call). Rate limit RPM from env, backoff on 429, checkpoint/resume.
- `.env` holds GEMINI_API_KEY (gitignored). Never log the key.

---

### Task 1: Scaffold + config + LLM adapter
Files: `pyproject.toml`, `.env.example`, `src/pipeline/__init__.py`, `src/pipeline/config.py`, `src/pipeline/llm.py`, `tests/test_llm.py`.
Produces: `Settings.from_env()`, `RateLimiter(rpm)` token bucket, `LLMClient.generate(prompt) -> str`, `generate_json(prompt) -> dict` (fence-strip, one repair retry), `GeminiBackend` / `StubBackend` injection, `retry_429`.
Test: stub backend returns canned text; rate limiter spacing; generate_json parses fenced JSON and repairs trailing-comma case.

### Task 2: Shared models
Files: `src/pipeline/models.py`, `tests/test_models.py`.
Types (consumed everywhere): `MfrInfo{name,code}`, `CleanRow{mfg_part_num,part_desc,e1_brand,unilog_brand,dib_brand,mfr_name,mfr_code}`, `Evidence{quote,url,tier}`, `Attribute{label,value,uom,evidence,verdict,confidence,review_reason}`, `Classification{dept,klass,fine,classpath,unspsc}`, `Extraction{item_type,series,attributes,features,certifications,application,includes}`, `RetrievalResult{domain,mfr_url,ref_urls,snippets,flags}`, `PhysicsCheck{name,status,fields,reason}`, `PhysicsReport{family,checks,ok}`, `RowResult{mfg_part_num,clean,classification,retrieval,extraction,physics,output_row,triage_score,flags}`.

### Task 3: Cleanse
Files: `src/pipeline/cleanse.py`, `data/abbreviations.json` seed, `tests/test_cleanse.py`.
`PLACEHOLDERS = {"-- Unbranded --","-- No Unilog Brand --","-- No DIB Brand --"}`; `clean_brand(v)->str|None`; `parse_manuf("Freud Inc (2435)")->MfrInfo("Freud Inc","2435")` (no parens → name only); `expand_abbrev(text, table)` word-boundary replace (Milw→Milwaukee); table persisted via `load_abbrev/save_abbrev`.
Test: each placeholder nulled; parens parse; missing-code case; expansion boundary ("Milw" inside word untouched).

### Task 4: UOM module
Files: `src/pipeline/format/uom.py`, `src/pipeline/format/__init__.py`, `tests/test_uom.py`.
`APPROVED_UOM` map (~45 forms→approved); `normalize_uom(s)`; `decimal_to_fraction(x, denom=64, tol=1e-4)->str` reduced gcd; `format_measure(50.25)->"50-1/4"` (ints plain); `normalize_measurement_text('14"x7/64"x1"'->"14 in x 7/64 in x 1 in"; "24in"→"24 in")`.
Test: inches/IN./"/inch→in; 0.5→1/2; 0.984375→63/64; 50.25→"50-1/4"; non-fractionable stays decimal; spacing fixes.

### Task 5: Description builders
Files: `src/pipeline/format/descriptions.py`, `tests/test_descriptions.py`.
Input view dataclass `DescInput{brand_display,manuf_name,mpn,item_type,series,feature,attributes:list[Attribute],additional}`.
- `build_invoice_desc` CAPS ≤40: `{TYPE} {compact attrs}` truncating on word boundary.
- `build_mobile_desc` exact pattern `{manuf} {brand}, {type}, {series}, {mpn}` (60–80 target).
- `build_short_desc`: `{brand} {series} {mpn} {type} With {feature}, {attr...}`.
- `build_long_desc`: `{brand} {type} With {feature}, {series}, {label value uom,...}, Additional Information: {additional}`.
- `build_retail_desc`: `{series}, {attr2-3}` short form.
Fixtures from dishwasher ground truth: mobile equality check; invoice length/caps; short starts `FRIGIDAIRE® Professional Series PDSH4816AF Dishwasher`.

### Task 6: Emit writer
Files: `src/pipeline/format/emit.py`, `tests/test_emit.py`.
`load_headers(path)->list[str]` from expected CSV row 1; `PASSTHROUGH = {"Mfg_Part_Num":..., "Part_Desc":..., "E1_Brand","Unilog_Brand","DIB_Brand","Part_Manuf"}`; `write_outputs(rows: list[RowResult], outdir)` → result.csv, result.xlsx, sidecar.jsonl (per-field provenance incl. blank-field review flags).
Test: header list equals source header exactly (252); csv/xlsx roundtrip; sidecar rows count == input rows.

### Task 7: Physics oracle (Z3)
Files: `src/pipeline/physics.py`, `tests/test_physics.py`.
Value parser `parse_qty("120 V")->(120.0,"V")`. Families: power balance watts≈V×A ±10%; disc diameter>arbor; ID<OD; unit-range sanity (dBA 30–80, V≤1000, A≤400, W≤20000, psi≤10000); fraction-decimal consistency. z3 Reals + unsat core → plain-language reasons naming fields. `run_physics(extraction, family_hint)->PhysicsReport`.
Tests: SAT pass case; each family's UNSAT triggers with correct fields named; SKIPPED when inputs missing.

### Task 8: Classify stage
Files: `src/pipeline/classify.py`, `tests/test_classify.py`.
`classify_rows(llm, clean_rows, batch=20)->dict[mpn->Classification]`; few-shot prompt w/ dishwasher classpath example; strict JSON array output aligned to input order.
Mocked test: batching windows, order preservation, schema validation, malformed element skipped w/ default.

### Task 9: Retrieve stage
Files: `src/pipeline/retrieve.py`, `tests/test_retrieve.py`.
`domain_candidates(mfr_name)` slug variants; `probe_domain(http, cand)->str|None` HEAD 200; `search_mpn(ddgs_fn, http, domain, mpn)` site: query + fallback `/search?q=` HTML href regex; trust tier assignment (host match 1.0, .pdf 0.9); `MARKETPLACE_BLOCKLIST = ("amazon.","ebay.","homedepot.","lowes.","grainger.")` drop+flag; snippet windows ±300 chars around MPN; disk cache `output/cache/retrieval.json`.
Mocked test (httpx MockTransport, fake ddgs): domain picked on 200; blocklisted hit flagged not used; snippet extraction; cache hit skips network.

### Task 10: Extract stage
Files: `src/pipeline/extract.py`, `tests/test_extract.py`.
Regex pre-extract from Part_Desc: dims `(\d+(?:\.\d+)?(?:-\d+/\d+)?)"`, voltage `(\d+)V\b`, amps `(\d+(?:\.\d+)?)A\b`, watts `(\d+)W\b`, grit `\bP(\d+)\b` → input-tier attributes. `extract(llm,row,classif,retrieval)->Extraction`; prompt requires verbatim quote per attribute; attach Evidence url/tier by matching quote→snippets.
Mocked test: pre-extract patterns; evidence URL attached when quote matches snippet; no-quote attr gets UNSUPPORTED verdict later (verifier).

### Task 11: Adversarial verifier
Files: `src/pipeline/verify_adversarial.py`, `tests/test_verify.py`.
STAKE_LABELS numeric/high-stakes selection; `verify(llm, extraction, retrieval)->Extraction` mutating verdicts per policy CONFIRMED keep / REFUTED drop(value kept? NO—value cleared, reason recorded) / UNSUPPORTED keep+flag.
Mocked test: policy application for all three verdicts.

### Task 12: Confidence + triage + dedup
Files: `src/pipeline/confidence.py`, `tests/test_confidence.py`.
TIER_BASE={0:0.35,0.9:0.75,1.0:1.0}; VERDICT_MULT={CONFIRMED:1.0,UNVERIFIED:0.6,UNSUPPORTED:0.45}; physics violation −0.3 clamp[0,1]. `triage_score(row)` = 0.4×missing_core_frac + 0.3×flag weight + 0.3×(1−mean_conf). `dedup_flags(rows)` SequenceMatcher≥0.92 same mfr_code → DUPLICATE_SUSPECT both.
Tests: matrix boundaries; known Milwaukee disc pair groups; distinct sizes stay separate.

### Task 13: Orchestration runner
Files: `src/pipeline/run_batch.py`, `tests/test_run_batch.py`.
Async main `python -m src.pipeline.run_batch --input ... --limit N --resume`; semaphore(4); stage-wise checkpoint `output/state.jsonl` keyed mpn; corrections.jsonl overrides applied post-extract; builds output_row via builders+emit mapping every stage completion; writes artifacts every 25 rows + end.
Integration test: StubBackend scripted responses + fake retrieval over 3 fixture rows → csv exists, headers==252, sidecar lines==3.

### Task 14: Eval compliance scorer
Files: `eval/score.py`, `tests/test_score.py`.
Checks: header fidelity vs source; INVOICE_DESC ≤40 & CAPS; MOBILE_DESC 60–80 when present; UOM spacing violations regex r'\d[a-zA-Z]{2,}' outside INVOICE_DESC; fraction form validity r'^\d+-\d+/\d+$|^\d+/\d+$'; replay diff vs example rows matching MPN PDSH4816AF/WDTS7024RZ (field-level %). CLI prints report.
Tests: synthetic bad row fails each check; good row passes; replay detects seeded error.

### Task 15: Live smoke run (manual gate)
10-row live run: `python -m src.pipeline.run_batch --limit 10`; acceptance: ≥8/10 rows have non-empty SHORT_DESC+LONG_DESC1, zero fabricated-value flags (all values either input-derived or evidence-backed), compliance report ≥90% format checks. Then full 1,000-row run.
