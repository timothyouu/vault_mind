"use client";

import { useEffect, useState, useCallback } from "react";
import type { NodeChangedEvent } from "../../types";
import type { VaultNode } from "./api/nodes/route";

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function SunIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

function MergeIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none">
      <path d="M6 3v12M18 9a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 15a9 9 0 0 0 9-9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Type badge colors
// ---------------------------------------------------------------------------

const TYPE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  decision:   { bg: "rgba(56,139,253,0.12)",  text: "#388bfd", border: "rgba(56,139,253,0.3)" },
  constraint: { bg: "rgba(248,81,73,0.1)",    text: "#f85149", border: "rgba(248,81,73,0.3)" },
  goal:       { bg: "rgba(63,185,80,0.12)",   text: "#3fb950", border: "rgba(63,185,80,0.3)" },
  question:   { bg: "rgba(163,113,247,0.12)", text: "#a371f7", border: "rgba(163,113,247,0.3)" },
  scope:      { bg: "rgba(210,153,34,0.15)",  text: "#d29922", border: "rgba(210,153,34,0.3)" },
};

const EVENT_COLORS: Record<string, string> = {
  created:        "#3fb950",
  linked:         "#388bfd",
  updated:        "#d29922",
  deleted:        "#f85149",
  "secret-detected": "#f85149",
  "intent-updated":  "#a371f7",
  "session-event":   "#7d8590",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return iso; }
}

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function shortId(id: string) {
  const parts = id.split("-");
  return parts.length >= 3 ? parts.slice(2, 4).join("-").slice(0, 8) : id.slice(0, 8);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusPill({ connected }: { connected: boolean }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "2px 8px", borderRadius: 9999,
      fontSize: 11, fontFamily: "var(--font-jetbrains-mono, monospace)",
      background: connected ? "rgba(63,185,80,0.12)" : "rgba(248,81,73,0.1)",
      color: connected ? "#3fb950" : "#f85149",
      border: `1px solid ${connected ? "rgba(63,185,80,0.3)" : "rgba(248,81,73,0.25)"}`,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: "50%",
        background: connected ? "#3fb950" : "#f85149",
        boxShadow: connected ? "0 0 0 2px rgba(63,185,80,0.3)" : "none",
      }} />
      {connected ? "live" : "disconnected"}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  const c = TYPE_COLORS[type] ?? { bg: "rgba(125,133,144,0.12)", text: "#7d8590", border: "rgba(125,133,144,0.25)" };
  return (
    <span style={{
      padding: "1px 7px", borderRadius: 4, fontSize: 10,
      fontFamily: "var(--font-jetbrains-mono, monospace)",
      fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em",
      background: c.bg, color: c.text, border: `1px solid ${c.border}`,
    }}>{type}</span>
  );
}

interface EventFeedEntry {
  id: string;
  event: string;
  ts: string;
  raw: string;
}

interface NodeCardProps {
  node: VaultNode;
  highlighted: boolean;
}

function NodeCard({ node, highlighted }: NodeCardProps) {
  return (
    <div style={{
      background: "var(--surface)",
      border: `1px solid ${highlighted ? "var(--accent)" : "var(--border)"}`,
      borderRadius: 8,
      padding: "14px 16px",
      transition: "border-color 0.4s",
      animation: "vm-fade 0.25s ease",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 6 }}>
        <TypeBadge type={node.type} />
        {node.status === "approved" && (
          <span style={{
            padding: "1px 7px", borderRadius: 4, fontSize: 10,
            fontFamily: "var(--font-jetbrains-mono, monospace)",
            fontWeight: 600, textTransform: "uppercase",
            background: "rgba(63,185,80,0.1)", color: "#3fb950",
            border: "1px solid rgba(63,185,80,0.25)",
          }}>approved</span>
        )}
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>
          {fmtDate(node.created)}
        </span>
      </div>
      <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500, marginBottom: 6, lineHeight: 1.4 }}>
        {node.title}
      </div>
      {node.body && (
        <div style={{
          fontSize: 12, color: "var(--muted)", lineHeight: 1.5,
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}>
          {node.body}
        </div>
      )}
      <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: 11, color: "var(--faint)", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>
          {shortId(node.id)}
        </span>
        {node.source_tool && (
          <span style={{ fontSize: 11, color: "var(--faint)" }}>· {node.source_tool}</span>
        )}
        {node.related.length > 0 && (
          <span style={{ fontSize: 11, color: "var(--accent)" }}>
            · {node.related.length} link{node.related.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function VaultPage() {
  const [nodes, setNodes] = useState<VaultNode[]>([]);
  const [events, setEvents] = useState<EventFeedEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [highlighted, setHighlighted] = useState<Set<string>>(new Set());
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [filter, setFilter] = useState<string>("all");

  // Apply theme
  useEffect(() => {
    document.documentElement.setAttribute("data-vmtheme", theme === "light" ? "light" : "");
    document.documentElement.style.background = theme === "light" ? "#ffffff" : "#0d1117";
  }, [theme]);

  // Load nodes from disk
  const loadNodes = useCallback(async () => {
    try {
      const res = await fetch("/api/nodes");
      const data = await res.json();
      setNodes(data.nodes ?? []);
    } catch { /* silently ignore */ }
  }, []);

  useEffect(() => { loadNodes(); }, [loadNodes]);

  // SSE
  useEffect(() => {
    const es = new EventSource("/api/events");
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as NodeChangedEvent;
        setEvents((prev) => [
          { id: data.id, event: data.event, ts: data.ts, raw: e.data },
          ...prev.slice(0, 99),
        ]);
        // Highlight the node card briefly
        setHighlighted((prev) => new Set([...prev, data.id]));
        setTimeout(() => {
          setHighlighted((prev) => { const n = new Set(prev); n.delete(data.id); return n; });
        }, 2500);
        // Refresh nodes list
        loadNodes();
      } catch { /* keep-alive comment — ignore */ }
    };

    return () => es.close();
  }, [loadNodes]);

  const nodeTypes = ["all", ...Array.from(new Set(nodes.map((n) => n.type)))];
  const filtered = filter === "all" ? nodes : nodes.filter((n) => n.type === filter);

  const counts = nodes.reduce<Record<string, number>>((acc, n) => {
    acc[n.type] = (acc[n.type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg)",
      color: "var(--text)",
      fontFamily: "var(--font-geist-sans, system-ui, sans-serif)",
    }}>
      {/* Top bar */}
      <header style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "0 24px", height: 52,
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        position: "sticky", top: 0, zIndex: 10,
      }}>
        <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>
          VaultMind
        </span>
        <span style={{
          fontSize: 11, color: "var(--muted)",
          fontFamily: "var(--font-jetbrains-mono, monospace)",
          marginLeft: 2,
        }}>vault</span>

        <div style={{ flex: 1 }} />

        <StatusPill connected={connected} />

        <a
          href="/merge"
          style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            padding: "4px 10px", borderRadius: 6,
            fontSize: 12, color: "var(--muted)",
            background: "var(--inset)", border: "1px solid var(--border)",
            textDecoration: "none", cursor: "pointer",
          }}
        >
          <MergeIcon /> Resolve conflicts
        </a>

        <button
          onClick={() => setTheme((t) => t === "dark" ? "light" : "dark")}
          style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 30, height: 30, borderRadius: 6,
            background: "var(--inset)", border: "1px solid var(--border)",
            color: "var(--muted)", cursor: "pointer",
          }}
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
      </header>

      {/* Body: left = nodes, right = event feed */}
      <div style={{ display: "flex", height: "calc(100vh - 52px)" }}>

        {/* Left: vault nodes */}
        <main style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>

          {/* Stats row */}
          <div style={{ display: "flex", gap: 10, marginBottom: 18, flexWrap: "wrap" }}>
            {Object.entries(counts).map(([type, count]) => {
              const c = TYPE_COLORS[type] ?? { bg: "rgba(125,133,144,0.1)", text: "var(--muted)", border: "rgba(125,133,144,0.2)" };
              return (
                <div key={type} style={{
                  padding: "6px 12px", borderRadius: 6,
                  background: c.bg, border: `1px solid ${c.border}`,
                  display: "flex", alignItems: "center", gap: 6,
                }}>
                  <span style={{ fontSize: 18, fontWeight: 700, color: c.text, lineHeight: 1 }}>{count}</span>
                  <span style={{ fontSize: 11, color: c.text, textTransform: "uppercase", letterSpacing: "0.05em", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>{type}s</span>
                </div>
              );
            })}
            {nodes.length === 0 && (
              <span style={{ fontSize: 12, color: "var(--muted)" }}>No vault nodes yet</span>
            )}
          </div>

          {/* Filter tabs */}
          {nodeTypes.length > 1 && (
            <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
              {nodeTypes.map((t) => (
                <button
                  key={t}
                  onClick={() => setFilter(t)}
                  style={{
                    padding: "3px 10px", borderRadius: 6,
                    fontSize: 12, cursor: "pointer",
                    fontFamily: "var(--font-jetbrains-mono, monospace)",
                    background: filter === t ? "var(--accent-btn)" : "var(--inset)",
                    color: filter === t ? "#fff" : "var(--muted)",
                    border: `1px solid ${filter === t ? "var(--accent-btn)" : "var(--border)"}`,
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
          )}

          {/* Node cards */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {filtered.map((node) => (
              <NodeCard
                key={node.id}
                node={node}
                highlighted={highlighted.has(node.id)}
              />
            ))}
            {filtered.length === 0 && nodes.length > 0 && (
              <div style={{ fontSize: 13, color: "var(--muted)", padding: "20px 0" }}>
                No {filter} nodes.
              </div>
            )}
            {nodes.length === 0 && (
              <div style={{
                padding: "40px 24px", textAlign: "center",
                border: "1px dashed var(--border)", borderRadius: 8,
              }}>
                <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 6 }}>
                  No vault nodes found.
                </div>
                <div style={{ fontSize: 12, color: "var(--faint)", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>
                  Start the pipeline: <code style={{ color: "var(--accent)" }}>npm run vaultmind:start</code>
                </div>
              </div>
            )}
          </div>
        </main>

        {/* Right: live event feed */}
        <aside style={{
          width: 300, flexShrink: 0,
          borderLeft: "1px solid var(--border)",
          background: "var(--surface)",
          overflowY: "auto",
          display: "flex", flexDirection: "column",
        }}>
          <div style={{
            padding: "12px 16px",
            borderBottom: "1px solid var(--border-muted)",
            fontSize: 11, fontWeight: 600, textTransform: "uppercase",
            letterSpacing: "0.08em", color: "var(--muted)",
            fontFamily: "var(--font-jetbrains-mono, monospace)",
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <span>Event feed</span>
            <StatusPill connected={connected} />
          </div>

          <div style={{ flex: 1, padding: "8px 0" }}>
            {events.length === 0 ? (
              <div style={{ padding: "20px 16px", fontSize: 12, color: "var(--faint)", lineHeight: 1.6 }}>
                Waiting for vault events…
                <br /><br />
                <span style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 11 }}>
                  Run <code style={{ color: "var(--accent)" }}>npm run vaultmind:start</code> to start the pipeline.
                </span>
              </div>
            ) : (
              events.map((ev, i) => (
                <div
                  key={i}
                  style={{
                    padding: "8px 16px",
                    borderBottom: "1px solid var(--border-muted)",
                    animation: i === 0 ? "vm-fade 0.2s ease" : undefined,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                    <span style={{
                      fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      color: EVENT_COLORS[ev.event] ?? "var(--muted)",
                      fontFamily: "var(--font-jetbrains-mono, monospace)",
                    }}>{ev.event}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text)", fontFamily: "var(--font-jetbrains-mono, monospace)", marginBottom: 2 }}>
                    {shortId(ev.id)}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--faint)" }}>{fmtTime(ev.ts)}</div>
                </div>
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
