import { NextRequest, NextResponse } from "next/server";
import { resolveNode } from "../../../../../lib/conflicts";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  // Parse and validate the request body before casting — req.json() returns
  // `unknown` in strict mode, and an unguarded cast would throw a TypeError
  // at runtime if `resolutions` is missing or null.
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  if (
    typeof raw !== "object" ||
    raw === null ||
    !("resolutions" in raw) ||
    typeof (raw as Record<string, unknown>).resolutions !== "object" ||
    (raw as Record<string, unknown>).resolutions === null
  ) {
    return NextResponse.json({ error: "Missing or invalid resolutions" }, { status: 400 });
  }

  const rawResolutions = (raw as { resolutions: Record<string, unknown> }).resolutions;

  // Keys come in as strings from JSON; coerce to numbers. Skip unknown values.
  const resolutions: Record<number, "ours" | "theirs" | "both"> = {};
  for (const [k, v] of Object.entries(rawResolutions)) {
    if (v === "ours" || v === "theirs" || v === "both") {
      resolutions[Number(k)] = v;
    }
  }

  const result = resolveNode(id, resolutions);
  return NextResponse.json(result, { status: result.ok ? 200 : 422 });
}
