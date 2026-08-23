import { spawn, execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { OUTPUT_DIR, PROJECT_ROOT, isCloud, resolvePython } from "@/lib/artifacts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const RUN_META = path.join(OUTPUT_DIR, "run.json");
const RUN_LOG = path.join(OUTPUT_DIR, "batch-ui.log");
const PYTHON = resolvePython();

type RunMeta = {
  pid: number | null;
  running: boolean;
  startedAt: string | null;
  finishedAt: string | null;
  args: { limit: number; resume: boolean; input?: string };
  stateStartLines?: number;
};

function readMeta(): RunMeta {
  try {
    return JSON.parse(fs.readFileSync(RUN_META, "utf8")) as RunMeta;
  } catch {
    return {
      pid: null,
      running: false,
      startedAt: null,
      finishedAt: null,
      args: { limit: 10, resume: false },
    };
  }
}

function writeMeta(meta: RunMeta): void {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  fs.writeFileSync(RUN_META, JSON.stringify(meta, null, 2));
}

function pidAlive(pid: number | null): boolean {
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

function tail(file: string, bytes = 400): string {
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

function totalInputRows(): number {
  const file = path.join(PROJECT_ROOT, "input", "Unihack_ Sample Dataset - Input.csv");
  return Math.max(0, countLines(file) - 1);
}

export async function GET() {
  let meta = readMeta();
  if (meta.running && !pidAlive(meta.pid)) {
    meta = { ...meta, running: false, finishedAt: new Date().toISOString() };
    writeMeta(meta);
  }
  const stateLines = countLines(path.join(OUTPUT_DIR, "state.jsonl"));
  const total = meta.args.limit || totalInputRows();
  const baseline = meta.stateStartLines ?? 0;
  const processed = Math.max(0, stateLines - baseline);
  return NextResponse.json({
    ...meta,
    processed: Math.min(processed, total),
    total,
    lastLog: tail(RUN_LOG),
  });
}

export async function POST(request: Request) {
  if (isCloud()) {
    return NextResponse.json(
      { error: "Pipeline execution runs locally. This deployment serves precomputed results." },
      { status: 501 }
    );
  }
  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }
  const b = (body ?? {}) as { limit?: unknown; resume?: unknown };
  let limit = Number(b.limit);
  if (!Number.isFinite(limit) || limit < 1 || limit > 10000) limit = 10;
  const resume = b.resume === true;

  const meta = readMeta();
  if (meta.running && pidAlive(meta.pid)) {
    return NextResponse.json(
      { error: `A run is already in progress (pid ${meta.pid}).` },
      { status: 409 }
    );
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const stateStartLines = countLines(path.join(OUTPUT_DIR, "state.jsonl"));
  const logFd = fs.openSync(RUN_LOG, "a");
  const child = spawn(PYTHON, ["-m", "pipeline.run_batch",
    "--limit", String(limit),
    ...(resume ? [] : ["--no-resume"]),
    "--state", path.join(OUTPUT_DIR, "state.jsonl"),
  ], {
    cwd: PROJECT_ROOT,
    env: { ...process.env, PYTHONPATH: path.join(PROJECT_ROOT, "src") },
    detached: true,
    stdio: ["ignore", logFd, logFd],
  });
  child.unref();
  fs.closeSync(logFd);

  const newMeta: RunMeta = {
    pid: child.pid ?? null,
    running: true,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    args: { limit, resume },
    stateStartLines,
  };
  writeMeta(newMeta);
  return NextResponse.json({ ok: true, ...newMeta });
}

export async function DELETE() {
  const meta = readMeta();
  if (meta.running && meta.pid && pidAlive(meta.pid)) {
    try {
      process.kill(-meta.pid, "SIGTERM"); // kill the detached group
    } catch {
      /* already gone */
    }
  }
  writeMeta({ ...readMeta(), running: false, pid: null, finishedAt: new Date().toISOString() });
  void execFile;
  return NextResponse.json({ ok: true });
}
