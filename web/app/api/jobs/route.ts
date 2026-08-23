import { NextResponse } from "next/server";
import {
  anyJobRunning,
  createFileJob,
  createSingleProductJob,
  isCloud,
  listJobs,
} from "@/lib/jobs";
import { enrichMany } from "@/lib/cloud-enrich";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({
    jobs: listJobs(),
    busy: anyJobRunning()?.id ?? null,
  });
}

export async function POST(request: Request) {
  // On Vercel we run the live TypeScript enrichment engine (up to 5 rows).
  if (isCloud()) {
    const { enrichMany } = await import("@/lib/cloud-enrich");
    const contentType0 = request.headers.get("content-type") ?? "";
    let inputs: Array<{ mpn: string; description: string; brand?: string; supplier?: string }> = [];
    if (contentType0.includes("multipart/form-data")) {
      const form = await request.formData();
      const file = form.get("file");
      if (!(file instanceof File)) {
        return NextResponse.json({ error: "No file uploaded." }, { status: 400 });
      }
      const text = await file.text();
      const lines = text.split(/\r?\n/).filter(Boolean);
      if (lines.length < 2) {
        return NextResponse.json({ error: "File has no data rows." }, { status: 400 });
      }
      const parseLine = (line: string): string[] => {
        const cells: string[] = [];
        let cur = "", q = false;
        for (const ch of line) {
          if (ch === '"') q = !q;
          else if (ch === "," && !q) { cells.push(cur); cur = ""; }
          else cur += ch;
        }
        cells.push(cur);
        return cells;
      };
      const headers = parseLine(lines[0]).map((h) => h.trim().toLowerCase());
      const iMpn = headers.findIndex((h) => ["mfg_part_num","mpn","part number","sku"].includes(h));
      const iDesc = headers.findIndex((h) => ["part_desc","description","desc","product description","title"].includes(h));
      const iSup = headers.findIndex((h) => ["part_manuf","manufacturer","supplier","vendor"].includes(h));
      if (iMpn === -1 || iDesc === -1) {
        return NextResponse.json(
          { error: "Need a part-number column and a description column." },
          { status: 422 }
        );
      }
      for (const line of lines.slice(1)) {
        const c = parseLine(line);
        inputs.push({
          mpn: (c[iMpn] ?? "").trim(),
          description: (c[iDesc] ?? "").trim(),
          supplier: iSup >= 0 ? (c[iSup] ?? "").trim() : undefined,
        });
      }
    } else {
      const body = await request.json().catch(() => ({}));
      inputs = [{
        mpn: String(body?.mpn ?? "").trim(),
        description: String(body?.description ?? "").trim(),
        brand: body?.brand ? String(body.brand).trim() : undefined,
        supplier: body?.supplier ? String(body.supplier).trim() : undefined,
      }];
    }
    inputs = inputs.filter((i) => i.mpn || i.description).slice(0, 5);
    if (!inputs.length) {
      return NextResponse.json({ error: "Nothing to enrich." }, { status: 400 });
    }
    try {
      const rows = await enrichMany(inputs);
      const echoes = inputs.map((i) => ({
        mpn: i.mpn,
        description: i.description,
        brandRaw: i.brand ?? "",
        supplierRaw: i.supplier ?? "",
      }));
      return NextResponse.json({ ok: true, rows, count: rows.length, echoes });
    } catch (e: any) {
      return NextResponse.json(
        { error: `Enrichment failed: ${e?.message?.slice(0, 160) ?? "unknown"}` },
        { status: 500 }
      );
    }
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
