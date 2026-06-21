import { NextRequest, NextResponse } from "next/server";
import { resolveNode } from "../../../../../lib/conflicts";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await req.json() as { resolutions: Record<string, "ours" | "theirs" | "both"> };

  // Keys come in as strings from JSON; coerce to numbers
  const resolutions: Record<number, "ours" | "theirs" | "both"> = {};
  for (const [k, v] of Object.entries(body.resolutions)) {
    resolutions[Number(k)] = v;
  }

  const result = resolveNode(id, resolutions);
  return NextResponse.json(result, { status: result.ok ? 200 : 422 });
}
