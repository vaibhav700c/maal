import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL;

export async function POST(request: Request) {
  if (!BACKEND) {
    return NextResponse.json({ error: "BACKEND_URL not configured." }, { status: 503 });
  }
  try {
    const upstream = await fetch(`${BACKEND.replace(/\/$/, "")}/enrich/async`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.arrayBuffer(),
    });
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json(
      { error: "Enrichment service unreachable. It may be waking up — retry shortly." },
      { status: 502 }
    );
  }
}
