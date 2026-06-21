/**
 * webapp/src/app/api/agent/route.ts
 *
 * Server-side proxy for the Fetch.ai / Agentverse agent.
 * Keeps AGENTVERSE_API_KEY off the client entirely.
 *
 * The target agent address:
 *   agent1qvlz2wl73xpgz4hxhrq03ptt7px6utjm7pjkhm3exazfk3ljvmam5vnkyy8
 *
 * Communication flow:
 *   Browser → POST /api/agent  →  Agentverse mailbox REST API
 *                              ←  async response polled here
 *                         ←  JSON { reply: string }
 *
 * Fetch.ai ACP (Agent Chat Protocol) message shape:
 * {
 *   msg_id:   uuid-v4          — unique per message
 *   timestamp: ISO-8601
 *   content: [{ type: "text", text: "..." }]
 * }
 *
 * Agentverse send endpoint (REST bridge):
 *   POST https://agentverse.ai/v1/agent/messages
 *   Authorization: Bearer <AGENTVERSE_API_KEY>
 *   { target: "<agent_address>", message: <ChatMessage> }
 *
 * The agent replies asynchronously back to our "sender" address (the key's
 * associated agent). We poll the mailbox inbox to retrieve it.
 */

import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const AGENT_ADDRESS =
  "agent1qvlz2wl73xpgz4hxhrq03ptt7px6utjm7pjkhm3exazfk3ljvmam5vnkyy8";

const AGENTVERSE_BASE = "https://agentverse.ai/v1";

// How long to wait for the async reply (ms) and poll interval
const REPLY_TIMEOUT_MS = 30_000;
const POLL_INTERVAL_MS = 1_500;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function agentverseHeaders() {
  const key = process.env.AGENTVERSE_API_KEY;
  if (!key) throw new Error("AGENTVERSE_API_KEY env var is not set");
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${key}`,
  };
}

/** Validate the agent address format (agent1q…, 65 chars, bech32-like). */
function isValidAgentAddress(addr: string): boolean {
  return /^agent1[a-z0-9]{58,}$/.test(addr);
}

/** Build a Fetch.ai ACP ChatMessage payload. */
function buildChatMessage(text: string) {
  return {
    msg_id: randomUUID(),
    timestamp: new Date().toISOString(),
    content: [{ type: "text", text }],
  };
}

/**
 * Send a message to the target agent via Agentverse REST bridge.
 * Returns the msg_id so we can match the reply.
 */
async function sendToAgent(text: string): Promise<string> {
  const message = buildChatMessage(text);

  const res = await fetch(`${AGENTVERSE_BASE}/agent/messages`, {
    method: "POST",
    headers: agentverseHeaders(),
    body: JSON.stringify({
      target: AGENT_ADDRESS,
      message,
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Agentverse send failed [${res.status}]: ${body}`);
  }

  return message.msg_id;
}

/**
 * Poll the Agentverse inbox for a reply to our msg_id.
 * Agentverse delivers replies to the API key's associated sender agent.
 */
async function pollForReply(sentMsgId: string): Promise<string> {
  const deadline = Date.now() + REPLY_TIMEOUT_MS;

  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));

    const res = await fetch(`${AGENTVERSE_BASE}/agent/messages/inbox`, {
      headers: agentverseHeaders(),
    });

    if (!res.ok) continue; // transient error — keep polling

    const data = (await res.json()) as {
      messages?: Array<{
        msg_id: string;
        in_reply_to?: string;
        content?: Array<{ type: string; text?: string }>;
      }>;
    };

    const reply = (data.messages ?? []).find(
      (m) => m.in_reply_to === sentMsgId
    );

    if (reply) {
      // Extract text content from the ACP reply envelope
      const text = (reply.content ?? [])
        .filter((c) => c.type === "text")
        .map((c) => c.text ?? "")
        .join("\n")
        .trim();

      return text || "(agent returned an empty response)";
    }
  }

  throw new Error("Agent did not reply within the timeout period.");
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function POST(req: NextRequest) {
  // 1. Validate env
  if (!process.env.AGENTVERSE_API_KEY) {
    return NextResponse.json(
      { error: "Server misconfiguration: AGENTVERSE_API_KEY not set." },
      { status: 500 }
    );
  }

  // 2. Parse body
  let body: { message?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const userMessage = (body.message ?? "").trim();
  if (!userMessage) {
    return NextResponse.json(
      { error: "Field 'message' is required and must be non-empty." },
      { status: 400 }
    );
  }

  // 3. Sanity-check the hardcoded target address
  if (!isValidAgentAddress(AGENT_ADDRESS)) {
    return NextResponse.json(
      { error: "Invalid agent address format." },
      { status: 500 }
    );
  }

  // 4. Send → poll → respond
  try {
    const msgId = await sendToAgent(userMessage);
    const reply = await pollForReply(msgId);
    return NextResponse.json({ reply });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("[/api/agent]", message);
    return NextResponse.json({ error: message }, { status: 502 });
  }
}