# Maal Repo Audit — 2026-08-23

## 1. Environment

**Python:** 3.12.4
**Installation:** All requested packages installed successfully.

### Installed Packages
- google-genai 2.19.0 ✓
- pydantic 2.13.4 ✓
- pandas (pre-existing) ✓
- openpyxl (pre-existing) ✓
- z3-solver (pre-existing) ✓
- httpx 0.28.1 ✓
- ddgs 9.15.0 ✓
- pytest (pre-existing) ✓
- pytest-asyncio (pre-existing) ✓

**Note:** Existing environment has version conflicts with downstream packages (langflow-base, langfuse, mcp, etc.), but all audit packages installed without errors. No clean venv exists in repo.

## 2. Test Results

```
55 passed, 17 skipped, 17 warnings in 1.16s
Total: 72 tests
```

**Skipped tests:** All async tests skipped due to `asyncio_default_fixture_loop_scope` misconfiguration (pytest-asyncio warning). Set explicit scope in pyproject.toml or pytest.ini to enable async test execution.

**Passing modules:** test_classify_extract, test_cleanse, test_confidence, test_descriptions, test_emit, test_llm, test_physics, test_retrieve, test_run_batch, test_score, test_uom, test_verify.

**Note:** test_failover has 3 warnings; tests are passing but async setup is incomplete.

## 3. Offline Pipeline Behavior

**Command:** `python -m pipeline.run_batch --limit 2 --no-resume` with no GEMINI_API_KEY set.

**Result:** Fails immediately with:
```
Exit code 1
GEMINI_API_KEY missing; add it to .env
```

**Finding:** The pipeline requires API key at startup and does not support true offline mode. Even `--no-resume` and `--limit` do not bypass this check. No dry-run or schema-validation-only mode exists.

## 4. Artifact Bootstrap Result

**Output directory:** Does not exist in repo (no `/output` folder).

**Offline paths checked:**
- `output/state.jsonl` — required by `eval/rescore.py` — absent
- `output/result.csv` — absent
- `output/sidecar.jsonl` — absent
- Test fixtures in `tests/` — no fixture CSVs or JSONL files present

**Finding:** Web UI will display empty states (no catalog rows, no past jobs) until at least one full pipeline run completes with API. No bootstrap data or demo dataset provided. `eval/rescore.py` is read-only and requires prior pipeline output.

## 5. Web Build Result

**npm install:** Succeeded. 45 packages added, **3 high severity vulnerabilities** present. Running `npm audit fix --force` recommended.

**npm run build:** **FAILED**

```
Error: Module not found: Can't resolve 'xlsx'
  at app/page.tsx (imported by lib/jobs.ts)
```

**Root cause:** `lib/jobs.ts` imports `import * as XLSX from "xlsx"` (line 5) for parsing Excel uploads, but `xlsx` is missing from `web/package.json` dependencies.

**Impact:** Build cannot complete; web app cannot be deployed or previewed.

## 6. Route Inventory

| Route | File | Purpose | Data Source |
|---|---|---|---|
| `/` | `app/page.tsx` | Dashboard; lists recent jobs | `listJobs()` from `lib/jobs.ts` |
| `/about` | `app/about/page.tsx` | Product overview and methodology | Static content |
| `/enrich` | `app/enrich/page.tsx` | Single product or file upload form | Static form + file upload handler |
| `/catalog` | `app/catalog/page.tsx` | Browse all enriched rows (filtered/sorted) | `listRows()` from `lib/artifacts.ts` reads `output/result.csv` + `output/sidecar.jsonl` |
| `/jobs/[id]` | `app/jobs/[id]/page.tsx` | View job status, logs, and row results | `getJob(id)`, `jobResults(id)` from `lib/jobs.ts` reads `output/jobs/[id]/result.csv` + `output/jobs/[id]/sidecar.jsonl` |
| `/row/[mpn]` | `app/row/[mpn]/page.tsx` | Detailed view of single enriched product | `getSidecarRecord(mpn)` from `lib/artifacts.ts` reads `output/sidecar.jsonl` |
| `/compare` | `app/compare/page.tsx` | Compare original vs. enriched CSV (QA/audit view) | `listRows()`, `originalRows()` from `lib/artifacts.ts` reads `output/result.csv` + uploaded file |

All routes use conditional rendering: if output files don't exist, pages display "no data" states instead of crashing.

## 7. Grep Audit Results

### Hardcoded Absolute Paths
**Finding:** None detected. All path construction uses environment variables with sensible fallbacks:
- `MAAL_OUTPUT_DIR` → defaults to `../output` (relative to web root)
- `MAAL_ROOT` → defaults to `..` (parent of web directory)
- `PROJECT_ROOT` used consistently in `lib/jobs.ts` for spawning Python child processes

### Output Directory References
**Finding:** No hardcoded absolute refs to `output/`. All paths constructed via `path.join()` and env vars.

### Em/En Dash Characters (U+2014 / U+2013)
**Finding:** **21 instances of em dashes (—)** in visible UI strings across:
- `app/about/page.tsx` — 3 occurrences
- `app/catalog/page.tsx` — 2 occurrences
- `app/compare/page.tsx` — 3 occurrences
- `app/enrich/page.tsx` — 1 occurrence
- `app/jobs/[id]/page.tsx` — 4 occurrences
- `app/layout.tsx` — 1 occurrence (page title: "Maal — Product Intelligence Console")
- `app/page.tsx` — 1 occurrence
- `app/row/[mpn]/page.tsx` — 3 occurrences
- `lib/jobs.ts` — 2 occurrences (in template strings)

**Impact:** Minimal if encoding is UTF-8 (expected for modern web). Potential issues if CSV exports or file operations assume ASCII or non-UTF8 encoding.

### .venv Hardcoding
**Location:** `lib/jobs.ts:10`
```javascript
const PYTHON = path.join(PROJECT_ROOT, ".venv", "bin", "python");
```
**Finding:** Pipeline expects exactly `.venv/bin/python` relative to project root. Will fail if venv is elsewhere or named differently (e.g., `venv/`, `.python-venv/`). No fallback to system `python`.

---

## Risks & Gaps (Ranked by Severity)

1. **[CRITICAL]** Missing `xlsx` dependency in `web/package.json`
   - Blocks all web app builds
   - Fix: Add `"xlsx": "^0.18.5"` to dependencies (used in lib/jobs.ts for Excel parsing)

2. **[HIGH]** No offline pipeline execution mode
   - `--no-resume` does not bypass GEMINI_API_KEY check
   - Limits testing, CI/CD, and demo capability without active API quotas
   - Fix: Make API key optional if inference is skipped (dry-run mode)

3. **[HIGH]** 3 npm security vulnerabilities (high severity)
   - `npm audit fix --force` needed
   - Recommend reviewing breaking changes before forcing upgrade

4. **[HIGH]** 17 async tests skipped due to pytest-asyncio config
   - Async test suite not running; coverage gap on async paths
   - Fix: Add `asyncio_mode = "auto"` to `pyproject.toml` or `pytest.ini`

5. **[MEDIUM]** Em dash characters (U+2014) in production UI strings
   - Not an error, but risks encoding issues if output CSVs are re-imported into non-UTF8 systems
   - Suggested: Add BOM to CSV exports, document UTF-8 requirement in README

6. **[MEDIUM]** No output/ directory or demo bootstrap data
   - Web UI shows empty states until first API run completes
   - Limits ability to demo/test without API key
   - Suggested: Check in a small fixtures/demo/state.jsonl for CI/preview

7. **[MEDIUM]** .venv path hardcoded in lib/jobs.ts
   - Will fail if venv directory is missing or named differently
   - Fix: Check for `PROJECT_ROOT/.venv/bin/python` OR fall back to `python` in PATH

8. **[LOW]** No visible CI/CD configuration (no .github/workflows, deploy/)
   - deploy/ folder exists but contents not audited
   - Recommend documenting build/test/deploy steps

9. **[LOW]** Duplicate COLUMN_ALIASES mapping (lib/jobs.ts:29-39) — no issue, but consider centralizing with Python side for maintainability

10. **[LOW]** No error logging or structured logging for web-spawned pipeline jobs
    - Tail of run.log captured, but full logs not persisted for audit trail

