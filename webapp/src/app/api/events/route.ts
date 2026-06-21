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
      await client.connect();

      // Keep-alive every 15s
      const keepAlive = setInterval(() => {
        controller.enqueue(encoder.encode(": keep-alive\n\n"));
      }, 15000);

      await client.subscribe("vaultmind:events", (message) => {
        controller.enqueue(encoder.encode(`data: ${message}\n\n`));
      });

      // Cleanup on close (best effort)
      _req.signal.addEventListener("abort", async () => {
        clearInterval(keepAlive);
        await client.unsubscribe("vaultmind:events");
        await client.disconnect();
        controller.close();
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
