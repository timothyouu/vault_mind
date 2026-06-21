import { NextRequest, NextResponse } from "next/server";
import { listConflictedNodes } from "../../../lib/conflicts";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(_req: NextRequest) {
  const files = listConflictedNodes();
  return NextResponse.json({ files });
}
