import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;
export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL;
const MAX_ROWS = 3;

export async function POST(request: Request) {
  if (!BACKEND) {
    return NextResponse.json(
      { error: "BACKEND_URL is not configured — point it at the Render enrichment service." },
      { status: 503 }
    );
  }

  const contentType = request.headers.get("content-type") ?? "";
  const isFile = contentType.includes("multipart/form-data");
  const endpoint = isFile ? "/enrich/batch" : "/enrich/single";

  try {
    const upstream = await fetch(`${BACKEND.replace(/\/$/, "")}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": contentType },
      body: await request.arrayBuffer(),
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
