import { NextRequest, NextResponse } from "next/server";
import { getConflictedNode } from "../../../../lib/conflicts";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const node = getConflictedNode(id);
  if (!node) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json(node);
}
