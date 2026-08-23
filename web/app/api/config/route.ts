import { NextResponse } from "next/server";
import { isCloud } from "@/lib/artifacts";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ cloud: isCloud(), canRun: !isCloud() });
}
