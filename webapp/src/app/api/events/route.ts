import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(_req: NextRequest) {
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      // Dynamic import so the module loads at request time (not build time)
      const redis = await import("redis");
      const client = redis.createClient({
        url: process.env.REDIS_URL ?? "redis://localhost:6379",
      });

      // MUST register error listener before connect() — redis v6 will crash the
      // Node.js process if an error event is emitted with no listener registered.
      let closed = false;
      client.on("error", (err) => {
        console.error("[SSE] Redis client error:", err);
        if (!closed) {
          closed = true;
          try { controller.error(err); } catch { /* already closed */ }
        }
      });

      await client.connect();

      // Keep-alive every 15s
      const keepAlive = setInterval(() => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(": keep-alive\n\n"));
        } catch { /* stream already closed */ }
      }, 15000);

      await client.subscribe("vaultmind:events", (message) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`data: ${message}\n\n`));
        } catch { /* stream already closed */ }
      });

      // Cleanup on close (best effort)
      _req.signal.addEventListener("abort", async () => {
        closed = true;
        clearInterval(keepAlive);
        try { await client.unsubscribe("vaultmind:events"); } catch { /* best effort */ }
        client.destroy();
        try { controller.close(); } catch { /* already closed */ }
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
