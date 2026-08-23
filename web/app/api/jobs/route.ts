import { NextResponse } from "next/server";
import {
  anyJobRunning,
  createFileJob,
  createSingleProductJob,
  isCloud,
  listJobs,
} from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({
    jobs: listJobs(),
    busy: anyJobRunning()?.id ?? null,
  });
}

export async function POST(request: Request) {
  if (isCloud()) {
    return NextResponse.json(
      { error: "This hosted deployment serves precomputed results. Clone the repo and run locally to enrich new products." },
      { status: 501 }
    );
  }
  const contentType = request.headers.get("content-type") ?? "";

  if (anyJobRunning()) {
    return NextResponse.json(
      { error: "Another enrichment job is running. Wait for it to finish or cancel it." },
      { status: 409 }
    );
  }

  if (contentType.includes("multipart/form-data")) {
    const form = await request.formData();
    const file = form.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json({ error: "No file uploaded." }, { status: 400 });
    }
    const lower = file.name.toLowerCase();
    if (!/\.(csv|xlsx|xls|txt|tsv)$/.test(lower)) {
      return NextResponse.json(
        { error: "Upload a .csv, .xlsx, .xls, .tsv or .txt file." },
        { status: 400 }
      );
    }
    if (file.size > 15 * 1024 * 1024) {
      return NextResponse.json({ error: "File too large (max 15 MB)." }, { status: 400 });
    }
    const buffer = Buffer.from(await file.arrayBuffer());
    const { meta, error } = createFileJob(file.name, buffer);
    if (error || !meta) {
      return NextResponse.json({ error }, { status: 422 });
    }
    return NextResponse.json({ ok: true, id: meta.id, inputRows: meta.inputRows });
  }

  let body: Record<string, unknown> = {};
  try {
    body = await request.json();
  } catch {
    /* fallthrough */
  }
  const mpn = typeof body.mpn === "string" ? body.mpn.trim() : "";
  const description = typeof body.description === "string" ? body.description.trim() : "";
  const brand = typeof body.brand === "string" ? body.brand.trim() : "";
  const supplier = typeof body.supplier === "string" ? body.supplier.trim() : "";
  if (!mpn || !description) {
    return NextResponse.json(
      { error: "Both a part number and a description are required." },
      { status: 400 }
    );
  }
  const meta = createSingleProductJob({ mpn, description, brand, supplier });
  return NextResponse.json({ ok: true, id: meta.id });
}
