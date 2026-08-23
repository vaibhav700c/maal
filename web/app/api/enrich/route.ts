import { NextResponse } from "next/server";
import { enrichMany, type CloudInput } from "@/lib/cloud-enrich";
import { parseCsv } from "@/lib/artifacts";
import { cleanBrand, parseManuf, PLACEHOLDERS } from "@/lib/cloud-enrich";

export const runtime = "nodejs";
export const maxDuration = 60;
export const dynamic = "force-dynamic";

const MAX_ROWS = 5;

function rowToInput(r: Record<string, string>): CloudInput {
  return {
    mpn: (r["Mfg_Part_Num"] ?? "").trim(),
    description: (r["Part_Desc"] ?? "").trim(),
    brand: PLACEHOLDERS.has((r["E1_Brand"] ?? "").trim()) ? undefined : (r["E1_Brand"] ?? "").trim() || undefined,
    supplier: (r["Part_Manuf"] ?? "").trim() || undefined,
  };
}

export async function POST(request: Request) {
  if (!process.env.GEMINI_API_KEY) {
    return NextResponse.json(
      { error: "GEMINI_API_KEY is not configured on this deployment." },
      { status: 500 }
    );
  }
  const contentType = request.headers.get("content-type") ?? "";
  let inputs: CloudInput[] = [];

  try {
    if (contentType.includes("multipart/form-data")) {
      const form = await request.formData();
      const file = form.get("file");
      if (!(file instanceof File)) {
        return NextResponse.json({ error: "No file uploaded." }, { status: 400 });
      }
      const text = await file.text();
      const parsed = parseCsv(text);
      if (parsed.length < 2) {
        return NextResponse.json({ error: "File has no data rows." }, { status: 400 });
      }
      const headers = parsed[0].map((h) => h.trim().toLowerCase());
      const idx = {
        mpn: headers.findIndex((h) => ["mfg_part_num", "mpn", "part number", "sku", "manufacturer part number", "part"].includes(h)),
        desc: headers.findIndex((h) => ["part_desc", "description", "desc", "product description", "item description", "title"].includes(h)),
        brand: headers.findIndex((h) => ["e1_brand", "brand", "brand name"].includes(h)),
        supplier: headers.findIndex((h) => ["part_manuf", "manufacturer", "supplier", "vendor"].includes(h)),
      };
      if (idx.mpn === -1 || idx.desc === -1) {
        return NextResponse.json(
          { error: 'Need a part-number column and a description column (any common naming).' },
          { status: 422 }
        );
      }
      for (const cells of parsed.slice(1)) {
        inputs.push({
          mpn: (cells[idx.mpn] ?? "").trim(),
          description: (cells[idx.desc] ?? "").trim(),
          brand: idx.brand >= 0 ? cleanBrand(cells[idx.brand]) ?? undefined : undefined,
          supplier: idx.supplier >= 0 ? (cells[idx.supplier] ?? "").trim() : undefined,
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

    inputs = inputs.filter((i) => i.mpn || i.description).slice(0, MAX_ROWS);
    inputs = inputs.map((i) =>
      i.mpn && i.description
        ? i
        : { ...i, mpn: i.mpn || i.description.slice(0, 24), description: i.description }
    );
    if (!inputs.length) {
      return NextResponse.json(
        { error: "Provide a part number and description (or a file with those columns)." },
        { status: 400 }
      );
    }

    void parseManuf; // supplier parsing happens inside the engine
    const rows = await enrichMany(inputs);
    return NextResponse.json({ ok: true, count: rows.length, rows });
  } catch (e: any) {
    return NextResponse.json(
      { error: `Enrichment failed: ${e?.message?.slice(0, 200) ?? "unknown"}` },
      { status: 500 }
    );
  }
}
