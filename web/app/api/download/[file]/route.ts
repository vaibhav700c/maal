import fs from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { OUTPUT_DIR } from "@/lib/artifacts";

export const runtime = "nodejs";

const ALLOWLIST: Record<string, string> = {
  "result.csv": "text/csv; charset=utf-8",
  "result.xlsx":
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "sidecar.jsonl": "application/x-ndjson; charset=utf-8",
};

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const jobId = searchParams.get("job");
  const file = searchParams.get("file") ?? "result.csv";
  const contentType = ALLOWLIST[file];
  if (!contentType) {
    return NextResponse.json({ error: "Unknown artifact" }, { status: 404 });
  }
  const baseDir = jobId ? path.join(OUTPUT_DIR, "jobs", jobId) : OUTPUT_DIR;
  const filePath = path.join(baseDir, path.basename(file));
  if (!fs.existsSync(filePath)) {
    return NextResponse.json({ error: "Artifact not generated yet" }, { status: 404 });
  }
  const name = jobId ? `${jobId}-${file}` : file;
  return new NextResponse(fs.readFileSync(filePath), {
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": `attachment; filename="${name}"`,
    },
  });
}
