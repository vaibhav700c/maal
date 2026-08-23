import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const OUTPUT_DIR =
  process.env.MAAL_OUTPUT_DIR ?? path.join(process.cwd(), "..", "output");

export const PROJECT_ROOT = process.env.MAAL_ROOT ?? path.join(process.cwd(), "..");

/** Hosted deployments ship a precomputed snapshot; local runs read live artifacts. */
export const DEMO_DATA_DIR = path.join(process.cwd(), "demo-data");

export function isCloud(): boolean {
  return process.env.VERCEL === "1";
}

function exists(file: string): boolean {
  try {
    return fs.existsSync(file);
  } catch {
    return false;
  }
}

/** Prefer live local artifacts; fall back to the bundled snapshot. */
export function artifactBase(): string {
  if (exists(path.join(OUTPUT_DIR, "result.csv"))) return OUTPUT_DIR;
  return DEMO_DATA_DIR;
}

/** Corrections need a writable location; serverless tmp is ephemeral but works. */
export function correctionsPath(): string {
  if (isCloud()) return path.join(os.tmpdir(), "maal-corrections.jsonl");
  return path.join(artifactBase(), "corrections.jsonl");
}

export type SidecarField = {
  value: string | null;
  uom?: string | null;
  source_url?: string | null;
  quote?: string | null;
  tier?: number | null;
  verdict?: string;
  confidence?: number;
  review_reason?: string | null;
};

export type PhysicsCheck = {
  name: string;
  status: string;
  fields: string[];
  reason: string | null;
};

export type SidecarRecord = {
  mfg_part_num: string;
  fields: Record<string, SidecarField>;
  physics: { family: string; checks: PhysicsCheck[] } | null;
  flags: string[];
  triage_score: number;
  retrieval?: {
    domain: string | null;
    mfr_url: string | null;
    ref_urls: string[];
    flags: string[];
  } | null;
  classification?: {
    dept: string;
    klass: string;
    fine: string;
    classpath: string;
    unspsc: string | null;
  } | null;
};

export type QueueRow = {
  mpn: string;
  triage: number;
  meanConfidence: number;
  physicsOk: boolean;
  classpath: string;
  flags: string[];
  attributeCount: number;
};

function readSidecar(): SidecarRecord[] {
  const file = path.join(artifactBase(), "sidecar.jsonl");
  if (!fs.existsSync(file)) return [];
  return fs
    .readFileSync(file, "utf8")
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => {
      try {
        return JSON.parse(line) as SidecarRecord;
      } catch {
        return null;
      }
    })
    .filter((r): r is SidecarRecord => r !== null);
}

const PHYSICS_UNCHECKED = ["SKIPPED"];

function meanConfidence(record: SidecarRecord): number {
  const values = Object.values(record.fields ?? {})
    .map((f) => f.confidence)
    .filter((c): c is number => typeof c === "number");
  if (!values.length) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export function listRows(): QueueRow[] {
  return readSidecar()
    .map((record) => ({
      mpn: record.mfg_part_num,
      triage: record.triage_score ?? 0,
      meanConfidence: meanConfidence(record),
      physicsOk:
        (record.physics?.checks ?? []).every(
          (c) => c.status !== "UNSAT"
        ) || (record.physics?.checks ?? []).length === 0,
      classpath: record.classification?.classpath ?? "",
      flags: record.flags ?? [],
      attributeCount: Object.keys(record.fields ?? {}).length,
    }))
    .sort((a, b) => b.triage - a.triage);
}

/** Minimal RFC4180 CSV parser (quotes, embedded commas/newlines). */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else inQuotes = false;
      } else cell += ch;
    } else if (ch === '"') inQuotes = true;
    else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (ch !== "\r") cell += ch;
  }
  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

export function getRow(mpn: string): {
  record: SidecarRecord;
  csvRow: Record<string, string>;
  headers: string[];
} | null {
  const record = readSidecar().find((r) => r.mfg_part_num === mpn);
  if (!record) return null;
  const csvFile = path.join(artifactBase(), "result.csv");
  let csvRow: Record<string, string> = {};
  let headers: string[] = [];
  if (fs.existsSync(csvFile)) {
    const parsed = parseCsv(fs.readFileSync(csvFile, "utf8"));
    headers = parsed[0] ?? [];
    for (const cells of parsed.slice(1)) {
      const candidate: Record<string, string> = {};
      headers.forEach((h, i) => (candidate[h] = cells[i] ?? ""));
      if (
        candidate["MANUFACTURER_PART_NUMBER"] === mpn ||
        candidate["Mfg_Part_Num"] === mpn
      ) {
        csvRow = candidate;
        break;
      }
    }
  }
  return { record, csvRow, headers };
}

export function appendCorrection(rec: {
  mfg_part_num: string;
  attributes?: Record<string, string>;
  output_row?: Record<string, string>;
}): void {
  const file = correctionsPath();
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.appendFileSync(file, JSON.stringify(rec) + "\n");
}

export function artifactPath(name: string): string | null {
  const allowlist: Record<string, string> = {
    "result.csv": "text/csv",
    "result.xlsx":
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "sidecar.jsonl": "application/x-ndjson",
  };
  if (!(name in allowlist)) return null;
  const file = path.join(OUTPUT_DIR, name);
  return fs.existsSync(file) ? `${allowlist[name]}\n${file}` : `missing\n${name}`;
}
