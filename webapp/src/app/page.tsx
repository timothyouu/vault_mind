"use client";

import { useEffect, useState } from "react";
import type { NodeChangedEvent } from "../../types";

interface EventEntry {
  id: string;
  event: string;
  ts: string;
}

export default function VaultPage() {
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource("/api/events");
    setConnected(true);

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as NodeChangedEvent;
        setEvents((prev) => [
          { id: data.id, event: data.event, ts: data.ts },
          ...prev,
        ]);
      } catch {
        // keep-alive or malformed — ignore
      }
    };

    es.onerror = () => setConnected(false);

    return () => es.close();
  }, []);

  return (
    <main className="p-8 font-mono">
      <h1 className="text-2xl font-bold mb-4">VaultMind — Walking Skeleton</h1>
      <p className="mb-4 text-sm">
        SSE: <span className={connected ? "text-green-600" : "text-red-600"}>
          {connected ? "connected" : "disconnected"}
        </span>
      </p>
      <ul className="space-y-1">
        {events.map((e, i) => (
          <li key={i} className="text-sm border-l-2 border-blue-400 pl-2">
            <span className="text-blue-600">[{e.event}]</span>{" "}
            <span className="font-semibold">{e.id}</span>{" "}
            <span className="text-gray-400">{e.ts}</span>
          </li>
        ))}
        {events.length === 0 && (
          <li className="text-gray-400 text-sm">Waiting for vault events…</li>
        )}
      </ul>
    </main>
  );
}
