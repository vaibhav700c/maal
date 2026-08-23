import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;
export const dynamic = "force-dynamic";

/**
 * Thin proxy: the real enrichment runs on the Render FastAPI service
 * (full Python pipeline incl. Z3 + Jina retrieval).
 */
const BACKEND = process.env.BACKEND_URL;

export async function POST(request: Request) {
  if (!BACKEND) {
    return NextResponse.json(
      { error: "BACKEND_URL is not configured — point it at the Render enrichment service." },
      { status: 503 }
    );
  }
  try {
    // pass through both single-product JSON and CSV multipart untouched
    const res = await fetch(`${BACKEND.replace(/\/$/, "")}/enrich/single`, {
      method: "POST",
      headers: { "Content-Type": request.headers.get("content-type") ?? "application/json" },
      body: await request.text(),
    });
    return new NextResponse(res.body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json(
      { error: "Enrichment service unreachable. It may be waking up — retry shortly." },
      { status: 502 }
    );
  }
}
