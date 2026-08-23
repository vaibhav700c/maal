import { NextResponse } from "next/server";
import { isCloud, listJobs } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8100";

export async function GET() {
  return NextResponse.json({ jobs: listJobs(), busy: null });
}

/**
 * Live enrichment through the Render FastAPI service.
 * - JSON body        -> /enrich/single
 * - multipart file   -> /enrich/batch
 */
export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") ?? "";
  const isFile = contentType.includes("multipart/form-data");
  const target = `${BACKEND.replace(/\/$/, "")}${isFile ? "/enrich/batch" : "/enrich/single"}`;

  try {
    const upstream = await fetch(target, {
      method: "POST",
      headers: { "Content-Type": isFile ? contentType : "application/json" },
      body: isFile ? await request.arrayBuffer() : await request.text(),
    });
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json(
      { error: "Enrichment service unreachable. It may be waking up — retry shortly." },
      { status: 502 }
    );
  }
}

export async function DELETE() {
  void isCloud;
  return NextResponse.json({ ok: true });
}
