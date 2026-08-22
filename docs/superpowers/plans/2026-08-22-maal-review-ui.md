# Maal Review UI (Plan 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Next.js review UI over pipeline artifacts: risk-ranked queue, per-field provenance/Z3 detail, human corrections loop, artifact downloads.

**Architecture:** Next.js 15 App Router + TS + Tailwind v4 inside `web/`. Server components read `output/sidecar.jsonl` + `output/result.csv` directly from disk (`MAAL_OUTPUT_DIR`, default `../output`). Route handlers: `POST /api/corrections` (append JSONL + revalidate), `GET /api/download/[file]` (stream artifacts). No DB.

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind CSS v4, zod-free manual validation.

## Global Constraints
- Visual direction per spec: near-monochrome slate palette, ONE accent; color reserved exclusively for verification states (green=CONFIRMED/SAT, amber=UNVERIFIED/UNSUPPORTED, red=REFUTED/UNSAT); tabular numerals; mono face for MPNs/values/codes; no gradients, no emoji, no filler copy. Dense tool-like PIM density.
- Read-only over artifacts except `corrections.jsonl`.
- Never render API keys; `.env` stays out of web bundle.

---

### Task 1: Scaffold
Files: `web/package.json`, `web/tsconfig.json`, `web/next.config.ts`, `web/postcss.config.mjs`, `web/app/layout.tsx`, `web/app/globals.css`.
- [ ] npm install; `next build` green on placeholder page; commit.

### Task 2: Artifact readers
Files: `web/lib/artifacts.ts`, `tests` none (verified via build+walkthrough).
Produces: `listRows()` -> Array<{mpn, flags, triage, meanConfidence, physicsOk, classpath}> sorted -triage; `getRow(mpn)` -> {record, csvRow}; `HEADERS` passthrough count; `appendCorrection(rec)`.
- [ ] Types mirror pipeline models; tolerant parsing (missing fields -> defaults); commit.

### Task 3: Queue view
Files: `web/app/page.tsx`, components `StatusChip`, `ConfBar`.
- [ ] Table: MPN (mono), Classpath, Physics SAT/UNSAT chip, flag chips, confidence bar, triage score; filter chips via searchParams (needs-review / physics / duplicates); sorted by triage desc; commit.

### Task 4: Row detail
Files: `web/app/row/[mpn]/page.tsx`, `CorrectionsForm` client component.
- [ ] Sections: identity/classification, descriptions (5), attributes table (label/value/uom/verdict/confidence/source link/evidence quote expandable), Z3 panel (per-check SAT/UNSAT + plain reason), corrections form posting to API; commit.

### Task 5: API routes
Files: `web/app/api/corrections/route.ts`, `web/app/api/download/[file]/route.ts`.
- [ ] corrections: validate {mfg_part_num, attributes?, output_row?}; append JSONL; revalidatePath. download: allowlist result.csv/result.xlsx/sidecar.jsonl; correct content-types; commit.

### Task 6: Verify + finish
- [ ] `next build` green; walkthrough against real smoke artifacts; screenshot-level sanity of visual direction; final commit + merge to master.
