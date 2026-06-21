"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

// ---------------------------------------------------------------------------
// Shared nav
// ---------------------------------------------------------------------------

function VaultNav({ theme, onToggle, liveLabel, liveDot }: {
  theme: "dark" | "light";
  onToggle: () => void;
  liveLabel: string;
  liveDot: string;
}) {
  const path = usePathname();
  const links = [
    { href: "/setup", label: "Setup" },
    { href: "/graph", label: "Graph" },
    { href: "/intent", label: "Intent log" },
    { href: "/merge", label: "Merge" },
  ];
  return (
    <header style={{
      flexShrink: 0,
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
      height: 56, padding: "0 20px",
      background: "var(--bg)", borderBottom: "1px solid var(--border)",
      position: "sticky", top: 0, zIndex: 30,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 26, height: 26, borderRadius: 7,
            background: "linear-gradient(135deg, var(--accent), var(--accent-btn))",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "inset 0 0 0 1px rgba(255,255,255,.12)",
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
              <path d="M12 2l8 4.5v9L12 22l-8-6.5v-9L12 2z" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
              <circle cx="12" cy="11" r="2.4" fill="#fff" />
            </svg>
          </div>
          <span style={{ fontWeight: 600, fontSize: 15, letterSpacing: "-0.2px" }}>VaultMind</span>
        </div>
        <nav style={{ display: "flex", alignItems: "center", gap: 2, marginLeft: 4 }}>
          {links.map(({ href, label }) => {
            const active = path === href;
            return (
              <Link key={href} href={href} style={{
                padding: "6px 11px", borderRadius: 7, fontSize: 13, textDecoration: "none",
                color: active ? "var(--text)" : "var(--muted)",
                fontWeight: active ? 500 : 400,
                background: active ? "var(--surface)" : "transparent",
                border: active ? "1px solid var(--border)" : "1px solid transparent",
              }}>{label}</Link>
            );
          })}
        </nav>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 7, padding: "5px 11px",
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 9999,
          fontSize: 12, color: "var(--muted)",
        }}>
          <span style={{
            width: 7, height: 7, borderRadius: "50%", background: liveDot,
            animation: "vm-livedot 1.6s ease-in-out infinite",
          }} />
          {liveLabel}
        </div>
        <button onClick={onToggle} title="Toggle theme" style={{
          width: 34, height: 34, display: "flex", alignItems: "center", justifyContent: "center",
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
          color: "var(--muted)", cursor: "pointer",
        }}>
          {theme === "dark"
            ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /></svg>
            : <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
          }
        </button>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function CheckIcon({ color = "currentColor", size = 13 }: { color?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M5 12l5 5L20 6" stroke={color} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ClockIcon({ color = "currentColor" }: { color?: string }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="2" />
      <path d="M12 7v5l3 2" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function CopyIcon({ color = "currentColor" }: { color?: string }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
      <rect x="9" y="9" width="11" height="11" rx="2" stroke={color} strokeWidth="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h8" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function BoltIcon({ color = "currentColor" }: { color?: string }) {
  return <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" fill={color} /></svg>;
}

function EyeIcon({ color = "currentColor" }: { color?: string }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" stroke={color} strokeWidth="2" />
      <circle cx="12" cy="12" r="3" stroke={color} strokeWidth="2" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Entry data
// ---------------------------------------------------------------------------

interface EntryFile { name: string; color: string; }

interface Entry {
  id: string;
  baseStatus: "committed" | "pending";
  title: string;
  summary: string;
  time: string;
  hash: string;
  diff: string;
  files: EntryFile[];
  reasoning: string;
}

const ENTRIES: Entry[] = [
  {
    id: "e1", baseStatus: "committed",
    title: "Wire secret scanner into save path",
    summary: "Added scanForSecrets() guard before every node commit.",
    time: "just now", hash: "a1f93c2", diff: "+48 −6",
    files: [{ name: "scan-secrets.ts", color: "#46c98a" }, { name: "node-panel.tsx", color: "#e07ca6" }],
    reasoning: "User asked saves to be blocked when a credential is present. Hooked the scanner into editor save and the commit hook so both paths share one regex set; blocked nodes now surface a banner instead of silently committing.",
  },
  {
    id: "e2", baseStatus: "committed",
    title: "Cluster the force layout by path",
    summary: "Grouped nodes into path-based clusters with radial spokes from the intent hub.",
    time: "6m ago", hash: "7be0d14", diff: "+121 −33",
    files: [{ name: "force-layout.ts", color: "#46c98a" }],
    reasoning: "Flat Obsidian-style layout was unreadable past ~40 nodes. Anchored each top-level folder to a ring position and let leaves settle around their hub, keeping cross-folder wikilinks as faint links.",
  },
  {
    id: "e3", baseStatus: "pending",
    title: "Rotate AWS keys via Vault",
    summary: "Replace hardcoded key in rotate-keys.ts with a Vault fetch.",
    time: "14m ago", hash: "—", diff: "+9 −5",
    files: [{ name: "rotate-keys.ts", color: "#5b8cff" }],
    reasoning: "Scanner flagged a hardcoded AWS secret. Draft swaps it for refreshFromVault(); held back from auto-commit because it touches the auth boundary and wants a human glance.",
  },
  {
    id: "e4", baseStatus: "committed",
    title: "Parse wikilinks in frontmatter",
    summary: "Resolve [[links]] inside YAML values, not just body text.",
    time: "31m ago", hash: "3c81a07", diff: "+27 −2",
    files: [{ name: "wikilink-parser.ts", color: "#46c98a" }, { name: "frontmatter.ts", color: "#46c98a" }],
    reasoning: "Edges from frontmatter (e.g. intent_ref) were being dropped. Extended the parser to walk scalar YAML values so related-topic chips populate correctly.",
  },
  {
    id: "e5", baseStatus: "pending",
    title: "Draft handoff template",
    summary: "Generate next.md with open threads + pickup steps on SessionEnd.",
    time: "42m ago", hash: "—", diff: "+64 −0",
    files: [{ name: "handoff.js", color: "#46c98a" }],
    reasoning: "SessionEnd needs to leave the next session a usable brief. Drafted a template that pulls pending intents as open threads and the last committed goals as pickup steps.",
  },
  {
    id: "e6", baseStatus: "committed",
    title: "Initialise the watcher",
    summary: "Start chokidar on the vault and stream change events to the bus.",
    time: "1h ago", hash: "0d4a2e9", diff: "+88 −0",
    files: [{ name: "watcher.ts", color: "#46c98a" }, { name: "stream-bus.ts", color: "#46c98a" }],
    reasoning: "Foundation for live capture. Debounced filesystem events and pushed them onto an in-memory bus the graph subscribes to.",
  },
];

const THREADS = [
  { title: "rotate-keys.ts still holds a live secret", ref: "auth/rotate-keys.ts · blocked", kind: "red" },
  { title: "stripe-webhook.ts merge conflict unresolved", ref: "payments/stripe-webhook.ts · 2 hunks", kind: "amber" },
  { title: "Handoff template needs a review pass", ref: "graph-engine/handoff.js · pending", kind: "amber" },
];

const NEXT_STEPS = [
  "Resolve the Stripe webhook conflict — keep the disk signature, drop the agent retry loop.",
  "Swap the AWS key in rotate-keys.ts for refreshFromVault(), then re-scan.",
  "Approve the handoff template intent so SessionEnd stops queuing it.",
];

// ---------------------------------------------------------------------------
// IntentPage
// ---------------------------------------------------------------------------

export default function IntentPage() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [mode, setMode] = useState<"auto" | "review">("auto");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [statusOverride, setStatusOverride] = useState<Record<string, "committed" | "discarded">>({});
  const [copied, setCopied] = useState(false);
  const [handoffSealed, setHandoffSealed] = useState(false);

  useEffect(() => {
    try {
      const t = localStorage.getItem("vm-theme") as "dark" | "light" | null;
      if (t === "light" || t === "dark") setTheme(t);
      document.documentElement.setAttribute("data-vmtheme", t || "dark");
    } catch { document.documentElement.setAttribute("data-vmtheme", "dark"); }
  }, []);

  const toggleTheme = () => {
    const t = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-vmtheme", t);
    try { localStorage.setItem("vm-theme", t); } catch { /* ignore */ }
    setTheme(t);
  };

  const effStatus = useCallback((e: Entry) => statusOverride[e.id] ?? e.baseStatus, [statusOverride]);

  const committedCount = ENTRIES.filter(e => effStatus(e) === "committed").length;
  const pendingCount = ENTRIES.filter(e => effStatus(e) === "pending").length;

  const handoffSummary = `Shipped the clustered graph and wired the secret scanner into every save. ${committedCount} intents committed this session; ${pendingCount} still ${mode === "review" ? "awaiting review" : "pending"}.`;

  const copyHandoff = () => {
    const txt = `# Handoff — next.md\n\n## Where we left off\n${handoffSummary}\n\n## Open threads\n${THREADS.map(t => `- ${t.title} (${t.ref})`).join("\n")}\n\n## Pick up next\n${NEXT_STEPS.map((s, i) => `${i + 1}. ${s}`).join("\n")}`;
    const done = () => { setCopied(true); setTimeout(() => setCopied(false), 1600); };
    try { navigator.clipboard.writeText(txt).then(done, done); } catch { done(); }
  };

  const amberColor = theme === "dark" ? "#dba53f" : "#9a6a10";
  const greenColor = theme === "dark" ? "#46c98a" : "#0f8f63";
  const redColor = theme === "dark" ? "#f26d78" : "#d23b48";
  const purpleColor = "#3cc6cf";
  const accentColor = theme === "dark" ? "#5b8cff" : "#2f5fe0";

  const STAT = {
    committed: { label: "committed", tagBg: `rgba(${theme === "dark" ? "63,185,80,.15" : "26,127,55,.12"})`, tagColor: greenColor, dot: greenColor },
    pending: { label: mode === "review" ? "needs review" : "pending", tagBg: `rgba(${theme === "dark" ? "210,153,34,.15" : "154,103,0,.12"})`, tagColor: amberColor, dot: amberColor },
    discarded: { label: "discarded", tagBg: "transparent", tagColor: "var(--faint)", dot: "var(--faint)" },
  };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", flexDirection: "column",
      background: "var(--bg)", color: "var(--text)",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
      fontSize: 14, lineHeight: 1.5, WebkitFontSmoothing: "antialiased",
    }}>
      <style>{`
        @keyframes vm-livedot { 0%, 100% { opacity: .35; } 50% { opacity: 1; } }
        @keyframes vm-fade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>

      <VaultNav
        theme={theme}
        onToggle={toggleTheme}
        liveLabel={mode === "review" ? "Review mode — commits paused" : "Watching · auto-committing"}
        liveDot={mode === "review" ? amberColor : greenColor}
      />

      {/* Session bar */}
      <div style={{
        flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: 16, flexWrap: "wrap", padding: "14px 24px",
        borderBottom: "1px solid var(--border)", background: "var(--surface-2)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{
              width: 30, height: 30, borderRadius: 8,
              background: "var(--surface)", border: "1px solid var(--border)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9" stroke={accentColor} strokeWidth="2" />
                <path d="M12 7v5l3 2" stroke={accentColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, fontFamily: "var(--font-jetbrains-mono, monospace)" }}>session-7f3a91</div>
              <div style={{ fontSize: 11.5, color: "var(--muted)" }}>Claude Code · started 1h 12m ago</div>
            </div>
          </div>
          <div style={{ width: 1, height: 30, background: "var(--border)" }} />
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div>
              <div style={{ fontSize: 17, fontWeight: 600, fontFamily: "var(--font-jetbrains-mono, monospace)" }}>{committedCount}</div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>committed</div>
            </div>
            <div>
              <div style={{ fontSize: 17, fontWeight: 600, fontFamily: "var(--font-jetbrains-mono, monospace)", color: pendingCount > 0 ? amberColor : "var(--muted)" }}>{pendingCount}</div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>{mode === "review" ? "to review" : "pending"}</div>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>Capture mode</span>
            <div style={{
              display: "flex",
              background: "var(--inset)", border: "1px solid var(--border)", borderRadius: 9, padding: 3, gap: 2,
            }}>
              {([["auto", "Auto-commit"] as const, ["review", "Review first"] as const]).map(([id, label]) => (
                <button key={id} onClick={() => setMode(id)} style={{
                  display: "flex", alignItems: "center", gap: 7, padding: "6px 13px",
                  border: "none", borderRadius: 6, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                  background: mode === id ? "var(--accent-btn)" : "transparent",
                  color: mode === id ? "#fff" : "var(--muted)",
                  boxShadow: mode === id ? "0 1px 2px rgba(8,9,14,.3)" : "none",
                  transition: "all .18s",
                }}>
                  {id === "auto" ? <BoltIcon color={mode === "auto" ? "#fff" : "var(--muted)"} /> : <EyeIcon color={mode === "review" ? "#fff" : "var(--muted)"} />}
                  {label}
                </button>
              ))}
            </div>
          </div>
          <button onClick={() => setHandoffSealed(true)} style={{
            display: "flex", alignItems: "center", gap: 8, padding: "8px 15px",
            background: purpleColor, border: `1px solid color-mix(in srgb, #fff 14%, ${purpleColor})`,
            borderRadius: 8, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer",
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            End session &amp; hand off
          </button>
        </div>
      </div>

      {/* Body */}
      <main style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 408px", minHeight: 0 }}>

        {/* Intent log */}
        <section style={{ minWidth: 0, overflowY: "auto", padding: "24px 28px 60px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: "-.3px" }}>Intent log</h1>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              {mode === "review" ? "You approve each commit" : "Commits land automatically"}
            </div>
          </div>
          <p style={{ margin: "0 0 22px", fontSize: 13.5, color: "var(--muted)" }}>
            Every agent turn is captured as an intent, then committed to{" "}
            <span style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", color: "var(--text)" }}>.vaultmind/</span>.
          </p>

          <div style={{ position: "relative" }}>
            <div style={{ position: "absolute", left: 15, top: 6, bottom: 6, width: 2, background: "var(--border)" }} />
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {ENTRIES.map(e => {
                const eff = effStatus(e);
                const st = STAT[eff as keyof typeof STAT] ?? STAT.pending;
                const isExpanded = !!expanded[e.id];
                const needsReview = mode === "review" && eff === "pending";

                return (
                  <div key={e.id} style={{ position: "relative", paddingLeft: 44, animation: "vm-fade .4s both" }}>
                    <span style={{
                      position: "absolute", left: 7, top: 14,
                      width: 18, height: 18, borderRadius: "50%",
                      background: "var(--bg)", border: `2px solid ${st.dot}`,
                      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1,
                      color: st.dot,
                    }}>
                      {eff === "committed" ? <CheckIcon color={st.dot} /> : <ClockIcon color={st.dot} />}
                    </span>

                    <div
                      onClick={() => setExpanded(x => ({ ...x, [e.id]: !x[e.id] }))}
                      style={{
                        background: "var(--surface)",
                        border: `1px solid ${needsReview ? `color-mix(in srgb, ${amberColor} 38%, var(--border))` : "var(--border)"}`,
                        borderRadius: 11, padding: "14px 16px", cursor: "pointer",
                        transition: "border-color .2s",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap", marginBottom: 4 }}>
                            <span style={{
                              padding: "2px 8px", borderRadius: 9999,
                              fontSize: 10.5, fontWeight: 600, letterSpacing: ".04em", textTransform: "uppercase",
                              background: st.tagBg, color: st.tagColor,
                              border: `1px solid color-mix(in srgb, ${st.dot} 40%, transparent)`,
                            }}>{st.label}</span>
                            <span style={{ fontSize: 13.5, fontWeight: 600, letterSpacing: "-.1px" }}>{e.title}</span>
                          </div>
                          <div style={{ fontSize: 12.5, color: "var(--muted)" }}>{e.summary}</div>
                        </div>
                        <span style={{ flexShrink: 0, fontSize: 11.5, color: "var(--faint)", fontFamily: "var(--font-jetbrains-mono, monospace)", whiteSpace: "nowrap" }}>{e.time}</span>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 11.5, color: "var(--muted)" }}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" /><path d="M12 3v6M12 15v6" stroke="currentColor" strokeWidth="2" /></svg>
                          {e.hash}
                        </span>
                        {e.files.map(f => (
                          <span key={f.name} style={{
                            display: "inline-flex", alignItems: "center", gap: 5,
                            padding: "2px 8px", background: "var(--inset)",
                            border: "1px solid var(--border-muted)", borderRadius: 6,
                            fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 11, color: "var(--text)",
                          }}>
                            <span style={{ width: 7, height: 7, borderRadius: 2, background: f.color }} />
                            {f.name}
                          </span>
                        ))}
                        <span style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 11, color: greenColor }}>{e.diff}</span>
                      </div>

                      {needsReview && (
                        <div style={{ display: "flex", gap: 8, marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border-muted)" }}>
                          <button
                            onClick={ev => { ev.stopPropagation(); setStatusOverride(o => ({ ...o, [e.id]: "committed" })); }}
                            style={{
                              display: "flex", alignItems: "center", gap: 6, padding: "6px 13px",
                              background: `color-mix(in srgb, ${greenColor} 16%, transparent)`,
                              border: `1px solid color-mix(in srgb, ${greenColor} 45%, transparent)`,
                              borderRadius: 7, color: greenColor, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                            }}
                          >
                            <CheckIcon color={greenColor} /> Approve &amp; commit
                          </button>
                          <button
                            onClick={ev => { ev.stopPropagation(); setStatusOverride(o => ({ ...o, [e.id]: "discarded" })); }}
                            style={{
                              padding: "6px 13px", background: "transparent",
                              border: "1px solid var(--border)", borderRadius: 7,
                              color: "var(--muted)", fontSize: 12.5, fontWeight: 500, cursor: "pointer",
                            }}
                          >Discard</button>
                        </div>
                      )}

                      {isExpanded && (
                        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border-muted)" }}>
                          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--faint)", marginBottom: 7 }}>
                            Reasoning captured
                          </div>
                          <div style={{ fontSize: 12.5, color: "var(--text)", lineHeight: 1.65 }}>{e.reasoning}</div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Handoff panel */}
        <aside style={{
          borderLeft: "1px solid var(--border)", background: "var(--surface-2)",
          overflowY: "auto", display: "flex", flexDirection: "column",
        }}>
          <div style={{ flexShrink: 0, padding: "18px 20px 14px", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 8, background: purpleColor,
                  display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.92,
                }}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M4 7h16M4 12h16M4 17h10" stroke="#fff" strokeWidth="2" strokeLinecap="round" /></svg>
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>Handoff</div>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>fires on SessionEnd</div>
                </div>
              </div>
              <button onClick={copyHandoff} style={{
                display: "flex", alignItems: "center", gap: 6, padding: "6px 11px",
                background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 7,
                color: "var(--text)", fontSize: 12, fontWeight: 500, cursor: "pointer",
              }}>
                {copied ? <CheckIcon color="var(--green)" /> : <CopyIcon color="var(--muted)" />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>

          <div style={{ flex: 1, padding: "16px 20px 28px" }}>
            <div style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 11, color: "var(--faint)", marginBottom: 14 }}>
              .vaultmind/handoff/next.md
            </div>

            <div style={{ marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 9 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: accentColor }} />
                Where we left off
              </div>
              <p style={{ margin: 0, fontSize: 13, color: "var(--text)", lineHeight: 1.65 }}>{handoffSummary}</p>
            </div>

            <div style={{ marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 9 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: amberColor }} />
                Open threads
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {THREADS.map((t, i) => (
                  <div key={i} style={{
                    display: "flex", gap: 9, padding: "9px 11px",
                    background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 9,
                  }}>
                    <span style={{ flexShrink: 0, marginTop: 2, display: "inline-flex", color: t.kind === "red" ? redColor : amberColor }}>
                      {t.kind === "red"
                        ? <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><rect x="4" y="10" width="16" height="11" rx="2" stroke="currentColor" strokeWidth="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="2" /></svg>
                        : <ClockIcon color={amberColor} />
                      }
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, color: "var(--text)", fontWeight: 500 }}>{t.title}</div>
                      <div style={{ fontSize: 11.5, color: "var(--muted)", fontFamily: "var(--font-jetbrains-mono, monospace)", marginTop: 1 }}>{t.ref}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 9 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: greenColor }} />
                Pick up next
              </div>
              <ol style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 7 }}>
                {NEXT_STEPS.map((s, i) => (
                  <li key={i} style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.5 }}>{s}</li>
                ))}
              </ol>
            </div>

            <div style={{
              marginTop: 22, padding: "11px 13px",
              background: "var(--surface)", border: "1px dashed var(--border)", borderRadius: 9,
              display: "flex", alignItems: "center", gap: 9,
            }}>
              <span style={{ display: "inline-flex", color: greenColor }}>
                {handoffSealed ? <CheckIcon color={greenColor} /> : <ClockIcon color="var(--muted)" />}
              </span>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>
                {handoffSealed ? "Sealed — written to .vaultmind/handoff/next.md" : "Live preview — regenerates on every commit"}
              </span>
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
}