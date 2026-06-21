/**
 * webapp/src/lib/useAgent.ts
 *
 * React hook — wraps the /api/agent proxy endpoint.
 *
 * Usage:
 *   const { send, reply, loading, error, reset } = useAgent();
 *   await send("Summarise the latest vault decisions");
 */

"use client";

import { useState, useCallback } from "react";

export interface AgentState {
  reply: string | null;
  loading: boolean;
  error: string | null;
}

export interface UseAgentReturn extends AgentState {
  send: (message: string) => Promise<void>;
  reset: () => void;
}

export function useAgent(): UseAgentReturn {
  const [reply, setReply] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setReply(null);
    setError(null);
    setLoading(false);
  }, []);

  const send = useCallback(async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    setReply(null);

    try {
      const res = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
      });

      const data = (await res.json()) as { reply?: string; error?: string };

      if (!res.ok || data.error) {
        throw new Error(data.error ?? `HTTP ${res.status}`);
      }

      setReply(data.reply ?? "(no reply)");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Network error";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  return { send, reply, loading, error, reset };
}