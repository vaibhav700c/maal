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

export async function GET(
  _request: Request,
  context: { params: Promise<{ file: string }> }
) {
  const { file } = await context.params;
  const contentType = ALLOWLIST[file];
  if (!contentType) {
    return NextResponse.json({ error: "Unknown artifact" }, { status: 404 });
  }
  const filePath = path.join(OUTPUT_DIR, path.basename(file));
  if (!fs.existsSync(filePath)) {
    return NextResponse.json({ error: "Artifact not generated yet" }, { status: 404 });
  }
  return new NextResponse(fs.readFileSync(filePath), {
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": `attachment; filename="${file}"`,
    },
  });
}
