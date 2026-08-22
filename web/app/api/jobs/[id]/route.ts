import { NextResponse } from "next/server";
import { cancelJob, getJob, jobArtifacts } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const meta = getJob(id);
  if (!meta) {
    return NextResponse.json({ error: "Job not found." }, { status: 404 });
  }
  const artifacts = jobArtifacts(id);
  const done = meta.status === "DONE" && artifacts.resultCsv !== null;
  return NextResponse.json({ ...meta, artifactsReady: done });
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const ok = cancelJob(id);
  return NextResponse.json({ ok }, { status: ok ? 200 : 409 });
}
