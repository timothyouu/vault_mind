// webapp/src/app/api/agent/route.ts
import { NextRequest, NextResponse } from "next/server";

const BRIDGE_URL = process.env.AGENT_BRIDGE_URL ?? "http://localhost:5002";
const POLL_INTERVAL_MS = 1500;
const REPLY_TIMEOUT_MS = 30_000;

export async function POST(req: NextRequest) {
  let body: { message?: string };
  try { body = await req.json(); }
  catch { return NextResponse.json({ error: "Invalid JSON" }, { status: 400 }); }

  const message = (body.message ?? "").trim();
  if (!message) return NextResponse.json({ error: "message is required" }, { status: 400 });

  // Send to bridge
  const sendRes = await fetch(`${BRIDGE_URL}/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  }).catch(() => null);

  if (!sendRes?.ok) {
    return NextResponse.json({ error: "Could not reach agent bridge. Is agent_bridge.py running?" }, { status: 502 });
  }

  // Poll bridge for reply
  const deadline = Date.now() + REPLY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
    const pollRes = await fetch(`${BRIDGE_URL}/response`).catch(() => null);
    if (!pollRes?.ok) continue;
    const data = await pollRes.json() as { reply: string | null };
    if (data.reply) return NextResponse.json({ reply: data.reply });
  }

  return NextResponse.json({ error: "Agent did not reply within 30 seconds." }, { status: 504 });
}