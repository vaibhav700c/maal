import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import * as XLSX from "xlsx";
import { OUTPUT_DIR, PROJECT_ROOT, parseCsv } from "./artifacts";
import type { SidecarField } from "./artifacts";

export const JOBS_DIR = path.join(OUTPUT_DIR, "jobs");
const PYTHON = path.join(PROJECT_ROOT, ".venv", "bin", "python");

export type JobStatus = "QUEUED" | "RUNNING" | "DONE" | "FAILED" | "CANCELLED";

export type JobMeta = {
  id: string;
  name: string;
  status: JobStatus;
  kind: "single" | "file";
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  pid?: number | null;
  inputRows: number;
  processed: number;
  lastLog: string;
  error?: string;
};

const COLUMN_ALIASES: Record<string, string[]> = {
  Mfg_Part_Num: ["mfg_part_num", "mpn", "part number", "part_no", "partno",
    "manufacturer part number", "sku", "part"],
  Part_Desc: ["part_desc", "description", "desc", "product description",
    "item description", "product name", "title"],
  E1_Brand: ["e1_brand", "brand", "brand name"],
  Unilog_Brand: ["unilog_brand", "unilog brand"],
  DIB_Brand: ["dib_brand", "dib brand"],
  Part_Manuf: ["part_manuf", "manufacturer", "mfr", "supplier", "vendor",
    "manufacturer name"],
};

function canonicalHeaders(raw: string[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const header of raw) {
    const norm = header.trim().toLowerCase();
    for (const [canonical, aliases] of Object.entries(COLUMN_ALIASES)) {
      if (norm === canonical.toLowerCase() || aliases.includes(norm)) {
        map[header] = canonical;
        break;
      }
    }
  }
  return map;
}

/** Normalize any tabular upload into the pipeline's 6-column CSV. */
export function normalizeToInputCsv(
  headers: string[],
  rows: string[][]
): { csv: string; mapped: string[]; missing: string[] } {
  const mapping = canonicalHeaders(headers);
  const missing = Object.keys(COLUMN_ALIASES).filter(
    (c) => !Object.values(mapping).includes(c) && (c === "Mfg_Part_Num" || c === "Part_Desc")
  );
  if (missing.length) {
    return { csv: "", mapped: Object.keys(mapping), missing };
  }
  const out: string[][] = [
    ["Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"],
  ];
  const idx: Record<string, number> = {};
  for (const [rawHeader, canonical] of Object.entries(mapping)) {
    idx[canonical] = headers.indexOf(rawHeader);
  }
  for (const row of rows) {
    const cell = (i: number) => (i >= 0 ? (row[i] ?? "").trim() : "");
    const mpn = cell(idx["Mfg_Part_Num"]);
    const desc = cell(idx["Part_Desc"]);
    if (!mpn && !desc) continue;
    out.push([
      mpn || desc.slice(0, 24),
      desc,
      cell(idx["E1_Brand"]) || "-- Unbranded --",
      cell(idx["Unilog_Brand"]) || "-- No Unilog Brand --",
      cell(idx["DIB_Brand"]) || "-- No DIB Brand --",
      cell(idx["Part_Manuf"]) || "-",
    ]);
  }
  const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  return { csv: out.map((r) => r.map(esc).join(",")).join("\n") + "\n", mapped: Object.keys(mapping), missing };
}

export function parseUploadedFile(filename: string, buffer: Buffer): {
  csv: string; mapped: string[]; missing: string[];
} {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) {
    const wb = XLSX.read(buffer, { type: "buffer" });
    const sheet = wb.Sheets[wb.SheetNames[0]];
    const matrix = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, raw: false, defval: "" });
    if (!matrix.length) return { csv: "", mapped: [], missing: ["empty spreadsheet"] };
    const headers = (matrix[0] as string[]).map(String);
    const rows = (matrix.slice(1) as string[][]).map((r) => r.map((c) => String(c ?? "")));
    return normalizeToInputCsv(headers, rows);
  }
  // default: treat as CSV/text
  const text = buffer.toString("utf8");
  const parsed = parseCsv(text);
  if (parsed.length < 2) return { csv: "", mapped: [], missing: ["file has no data rows"] };
  return normalizeToInputCsv(parsed[0], parsed.slice(1));
}

export function jobDir(id: string): string {
  return path.join(JOBS_DIR, id);
}

function readMeta(id: string): JobMeta | null {
  try {
    return JSON.parse(fs.readFileSync(path.join(jobDir(id), "meta.json"), "utf8")) as JobMeta;
  } catch {
    return null;
  }
}

function writeMeta(meta: JobMeta): void {
  fs.mkdirSync(jobDir(meta.id), { recursive: true });
  fs.writeFileSync(path.join(jobDir(meta.id), "meta.json"), JSON.stringify(meta, null, 2));
}

function pidAlive(pid?: number | null): boolean {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function countLines(file: string): number {
  try {
    return fs.readFileSync(file, "utf8").split("\n").filter(Boolean).length;
  } catch {
    return 0;
  }
}

function refreshMeta(meta: JobMeta): JobMeta {
  if (meta.status !== "RUNNING") return meta;
  if (!pidAlive(meta.pid)) {
    meta.status = "DONE";
    meta.finishedAt = new Date().toISOString();
    meta.processed = meta.inputRows;
    meta.lastLog = tail(path.join(jobDir(meta.id), "run.log"));
    writeMeta(meta);
  } else {
    meta.processed = Math.min(
      countLines(path.join(jobDir(meta.id), "state.jsonl")),
      meta.inputRows
    );
    meta.lastLog = tail(path.join(jobDir(meta.id), "run.log"));
  }
  return meta;
}

function tail(file: string, bytes = 300): string {
  try {
    const stat = fs.statSync(file);
    const start = Math.max(0, stat.size - bytes);
    const fd = fs.openSync(file, "r");
    const buf = Buffer.alloc(stat.size - start);
    fs.readSync(fd, buf, 0, buf.length, start);
    fs.closeSync(fd);
    return buf.toString("utf8").trim().split("\n").pop() ?? "";
  } catch {
    return "";
  }
}

export function anyJobRunning(): JobMeta | null {
  for (const job of listJobs()) {
    if (job.status === "RUNNING") return job;
  }
  return null;
}

export function listJobs(): JobMeta[] {
  fs.mkdirSync(JOBS_DIR, { recursive: true });
  return fs
    .readdirSync(JOBS_DIR)
    .map((id) => readMeta(id))
    .filter((m): m is JobMeta => m !== null)
    .map(refreshMeta)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export function getJob(id: string): JobMeta | null {
  const meta = readMeta(id);
  return meta ? refreshMeta(meta) : null;
}

export function createSingleProductJob(input: {
  mpn: string;
  description: string;
  brand?: string;
  supplier?: string;
}): JobMeta {
  const id = crypto.randomBytes(5).toString("hex");
  const dir = jobDir(id);
  fs.mkdirSync(dir, { recursive: true });
  const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const csv = [
    "Mfg_Part_Num,Part_Desc,E1_Brand,Unilog_Brand,DIB_Brand,Part_Manuf",
    [
      esc(input.mpn),
      esc(input.description),
      esc(input.brand || "-- Unbranded --"),
      "-- No Unilog Brand --",
      "-- No DIB Brand --",
      esc(input.supplier || "-"),
    ].join(","),
  ].join("\n");
  fs.writeFileSync(path.join(dir, "input.csv"), csv + "\n");
  const meta: JobMeta = {
    id,
    name: `${input.mpn} — ${input.description.slice(0, 40)}`,
    status: "RUNNING",
    kind: "single",
    createdAt: new Date().toISOString(),
    startedAt: new Date().toISOString(),
    pid: null,
    inputRows: 1,
    processed: 0,
    lastLog: "",
  };
  launchPipeline(meta);
  return meta;
}

export function createFileJob(
  filename: string,
  buffer: Buffer
): { meta: JobMeta; error?: string } {
  const parsed = parseUploadedFile(filename, buffer);
  if (parsed.missing.length || !parsed.csv.trim()) {
    return {
      meta: null as unknown as JobMeta,
      error: `Could not find required columns (${parsed.missing.join(", ")}) in "${filename}". The file needs a part-number and a description column.`,
    };
  }
  const id = crypto.randomBytes(5).toString("hex");
  const dir = jobDir(id);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "input.csv"), parsed.csv);
  fs.writeFileSync(path.join(dir, "uploaded." + (filename.split(".").pop() ?? "csv")), buffer);
  const rowCount = parsed.csv.trim().split("\n").length - 1;
  const meta: JobMeta = {
    id,
    name: filename,
    status: "RUNNING",
    kind: "file",
    createdAt: new Date().toISOString(),
    startedAt: new Date().toISOString(),
    pid: null,
    inputRows: rowCount,
    processed: 0,
    lastLog: "",
  };
  launchPipeline(meta);
  return { meta };
}

function launchPipeline(meta: JobMeta): void {
  const dir = jobDir(meta.id);
  const logFd = fs.openSync(path.join(dir, "run.log"), "a");
  const child = spawn(PYTHON, [
    "-m", "pipeline.run_batch",
    "--input", path.join(dir, "input.csv"),
    "--state", path.join(dir, "state.jsonl"),
    "--out-dir", dir,
    "--no-resume",
  ], {
    cwd: PROJECT_ROOT,
    env: { ...process.env, PYTHONPATH: path.join(PROJECT_ROOT, "src") },
    detached: true,
    stdio: ["ignore", logFd, logFd],
  });
  child.unref();
  fs.closeSync(logFd);
  meta.pid = child.pid ?? null;
  writeMeta(meta);
}

export function cancelJob(id: string): boolean {
  const meta = getJob(id);
  if (!meta || meta.status !== "RUNNING") return false;
  try {
    if (meta.pid) process.kill(-meta.pid, "SIGTERM");
  } catch {
    /* already gone */
  }
  meta.status = "CANCELLED";
  meta.finishedAt = new Date().toISOString();
  writeMeta(meta);
  return true;
}

export function jobArtifacts(id: string): {
  resultCsv: string | null;
  resultXlsx: string | null;
  sidecar: string | null;
} {
  const dir = jobDir(id);
  const has = (f: string) => fs.existsSync(path.join(dir, f));
  return {
    resultCsv: has("result.csv") ? path.join(dir, "result.csv") : null,
    resultXlsx: has("result.xlsx") ? path.join(dir, "result.xlsx") : null,
    sidecar: has("sidecar.jsonl") ? path.join(dir, "sidecar.jsonl") : null,
  };
}

export type JobResultRow = {
  mpn: string;
  shortDesc: string;
  longDesc: string;
  classpath: string;
  unspsc: string;
  brand: string;
  manufacturer: string;
  invoiceDesc: string;
  mobileDesc: string;
  retailDesc: string;
  flags: string[];
  triage: number;
  physics: Array<{ name: string; status: string; reason: string | null }> | null;
  retrieval: {
    mfrUrl: string | null;
    productUrl: string | null;
    refUrls: string[];
    flags: string[];
  } | null;
  assets: Record<string, string>;
  attributes: Array<{
    label: string;
    value: string;
    uom: string | null;
    verdict?: string;
    confidence?: number;
    quote?: string | null;
    url?: string | null;
    reviewReason?: string | null;
  }>;
};

/** Fully enriched rows for the job results page — everything needed to
 * inspect a record in-app without downloading anything. */
export function jobResults(id: string): JobResultRow[] {
  const sidecarFile = path.join(jobDir(id), "sidecar.jsonl");
  const csvFile = path.join(jobDir(id), "result.csv");
  if (!fs.existsSync(sidecarFile)) return [];
  const records = fs.readFileSync(sidecarFile, "utf8")
    .split("\n").filter(Boolean)
    .map((line) => JSON.parse(line));
  let csvRows: Record<string, string>[] = [];
  if (fs.existsSync(csvFile)) {
    const parsed = parseCsv(fs.readFileSync(csvFile, "utf8"));
    const headers = parsed[0] ?? [];
    csvRows = parsed.slice(1).map((cells) => {
      const obj: Record<string, string> = {};
      headers.forEach((h, i) => (obj[h] = cells[i] ?? ""));
      return obj;
    });
  }
  const ASSET_KEYS = [
    "MFR URL",
    "Product Image",
    "Alternate Image 1",
    "Alternate Image 2",
    "Specification Sheet",
    "Actual Image (Yes/No)",
    "Ref URL 1",
    "Ref URL 2",
    "Ref URL 3",
    "Ref URL 4",
    "Ref URL 5",
  ];
  return records.map((rec: Record<string, any>) => {
    const csvRow: Record<string, string> =
      csvRows.find(
        (r) =>
          r["MANUFACTURER_PART_NUMBER"] === rec.mfg_part_num ||
          r["Mfg_Part_Num"] === rec.mfg_part_num
      ) ?? {};
    const assets: Record<string, string> = {};
    for (const key of ASSET_KEYS) {
      if (csvRow[key]) assets[key] = csvRow[key];
    }
    return {
      mpn: rec.mfg_part_num,
      shortDesc: csvRow["SHORT_DESC"] ?? "",
      longDesc: (csvRow["LONG_DESC1"] ?? "").slice(0, 600),
      classpath: rec.classification?.classpath ?? "",
      unspsc: csvRow["UNSPSC"] ?? rec.classification?.unspsc ?? "",
      brand: csvRow["BRAND_NAME"] ?? "",
      manufacturer: csvRow["MANUFACTURER_NAME"] ?? "",
      invoiceDesc: csvRow["INVOICE_DESC"] ?? "",
      mobileDesc: csvRow["MOBILE_DESC"] ?? "",
      retailDesc: csvRow["RETAIL_DESC"] ?? "",
      flags: rec.flags ?? [],
      triage: rec.triage_score ?? 0,
      physics: rec.physics
        ? rec.physics.checks.map((c: any) => ({
            name: c.name,
            status: c.status,
            reason: c.reason ?? null,
          }))
        : null,
      retrieval: rec.retrieval
        ? {
            mfrUrl: rec.retrieval.mfr_url ?? null,
            productUrl: rec.retrieval.product_url ?? null,
            refUrls: rec.retrieval.ref_urls ?? [],
            flags: rec.retrieval.flags ?? [],
          }
        : null,
      assets,
      attributes: Object.entries(
        (rec.fields ?? {}) as Record<string, SidecarField>
      ).map(([label, f]) => ({
        label,
        value: String(f.value ?? ""),
        uom: f.uom ?? null,
        verdict: f.verdict,
        confidence: f.confidence,
        quote: f.quote ?? null,
        url: f.source_url ?? null,
        reviewReason: f.review_reason ?? null,
      })),
    };
  });
}
