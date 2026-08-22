import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";
import { appendCorrection } from "@/lib/artifacts";

export const runtime = "nodejs";

type CorrectionBody = {
  mfg_part_num?: unknown;
  attributes?: unknown;
  output_row?: unknown;
};

function isStringRecord(value: unknown): value is Record<string, string> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.values(value).every((v) => typeof v === "string")
  );
}

export async function POST(request: Request) {
  let body: CorrectionBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const mpn = typeof body.mfg_part_num === "string" ? body.mfg_part_num.trim() : "";
  if (!mpn) {
    return NextResponse.json({ error: "mfg_part_num is required" }, { status: 400 });
  }
  const attributes = isStringRecord(body.attributes) ? body.attributes : {};
  const outputRow = isStringRecord(body.output_row) ? body.output_row : {};
  if (!Object.keys(attributes).length && !Object.keys(outputRow).length) {
    return NextResponse.json(
      { error: "Provide at least one attribute or output_row override" },
      { status: 400 }
    );
  }

  appendCorrection({ mfg_part_num: mpn, attributes, output_row: outputRow });
  revalidatePath("/");
  revalidatePath(`/row/${encodeURIComponent(mpn)}`);
  return NextResponse.json({ ok: true, queued: { mfg_part_num: mpn } });
}
