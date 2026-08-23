import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;
export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL;

type Row = { mpn: string; description: string; supplier?: string };

export async function POST(request: Request) {
  if (!BACKEND) {
    return NextResponse.json(
      { error: "BACKEND_URL not configured." },
      { status: 503 }
    );
  }
  let body: { rows?: Array<{ mpn: string; description: string; supplier?: string }> };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const products = (body.rows ?? []).slice(0, 10);
  if (!products.length) {
    return NextResponse.json({ error: "No rows provided." }, { status: 400 });
  }

  // Call the Render backend for each row sequentially (free tier RPM limits)
  const results: any[] = [];
  for (const p of products) {
    try {
      const res = await fetch(`${BACKEND.replace(/\/$/, "")}/enrich/single`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(p),
      });
      const d = await res.json().catch(() => null);
      if (d?.rows?.[0]) results.push(d.rows[0]);
    } catch {
      /* skip failed row */
    }
  }
  return NextResponse.json({ ok: true, count: results.length, rows: results });
}
