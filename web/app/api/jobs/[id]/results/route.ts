import { NextResponse } from "next/server";
import { jobResults } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  return NextResponse.json(jobResults(id));
}
