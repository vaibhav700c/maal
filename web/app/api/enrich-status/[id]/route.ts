import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  if (!BACKEND) {
    return NextResponse.json({ error: "BACKEND_URL not configured." }, { status: 503 });
  }
  const { id } = await params;
  try {
    const upstream = await fetch(
      `${BACKEND.replace(/\/$/, "")}/enrich/status/${encodeURIComponent(id)}`,
      { cache: "no-store" }
    );
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json({ status: "unreachable" }, { status: 502 });
  }
}
