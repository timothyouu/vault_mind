"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

// ---------------------------------------------------------------------------
// Shared nav
// ---------------------------------------------------------------------------

function VaultNav({ theme, onToggle }: { theme: "dark" | "light"; onToggle: () => void }) {
  const path = usePathname();
  const links = [
    { href: "/setup", label: "Setup" },
    { href: "/graph", label: "Graph" },
    { href: "/intent", label: "Intent log" },
    { href: "/merge", label: "Merge" },
  ];
  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 20,
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
      height: 56, padding: "0 20px",
      background: "color-mix(in srgb, var(--bg) 88%, transparent)",
      backdropFilter: "saturate(160%) blur(8px)",
      borderBottom: "1px solid var(--border)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 26, height: 26, borderRadius: 7,
            background: "linear-gradient(135deg, var(--accent), #7d5bed)",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "inset 0 0 0 1px rgba(255,255,255,.12)",
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
              <path d="M12 2l8 4.5v9L12 22l-8-6.5v-9L12 2z" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
              <circle cx="12" cy="11" r="2.4" fill="#fff" />
            </svg>
          </div>
          <span style={{ fontWeight: 600, fontSize: 15, letterSpacing: "-0.2px" }}>VaultMind</span>
          <span style={{
            padding: "2px 7px", border: "1px solid var(--border)", borderRadius: 9999,
            fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-jetbrains-mono, monospace)",
          }}>v0.4.2</span>
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
    </header>
  );
}

// ---------------------------------------------------------------------------
// Step definitions
// ---------------------------------------------------------------------------

interface StepDef {
  id: string;
  title: string;
  desc: string;
  filename?: string;
  fileKind?: "file" | "term";
  code?: string;
  tag?: string;
  tagKind?: "amber";
  noteKind?: "amber" | "info";
  noteKicker?: string;
  note?: string;
  link?: string;
}

const STEPS: StepDef[] = [
  {
    id: "claude",
    title: "Add the Claude Code hook",
    desc: "Registers Stop + SessionEnd hooks so VaultMind commits and hands off automatically.",
    filename: ".claude/settings.json",
    fileKind: "file",
    code: `{
  "hooks": {
    "Stop": [
      { "command": "node .vaultmind/hooks/commit.js" }
    ],
    "SessionEnd": [
      { "command": "node .vaultmind/hooks/handoff.js" }
    ]
  }
}`,
  },
  {
    id: "codex",
    title: "Add the Codex hook",
    desc: "Codex fires Stop only — VaultMind still commits on every turn.",
    filename: ".codex/hooks.json",
    fileKind: "file",
    tag: "Stop only",
    tagKind: "amber",
    code: `{
  "Stop": [
    { "command": "node .vaultmind/hooks/commit.js" }
  ]
}`,
    noteKind: "amber",
    noteKicker: "Heads up — ",
    note: "Codex has no SessionEnd equivalent; async hooks aren't supported, so handoff runs on next app open instead.",
  },
  {
    id: "deps",
    title: "Install dependencies",
    desc: "Clone the CLI into your repo and pull Node + Python deps.",
    filename: "terminal",
    fileKind: "term",
    code: `git clone https://github.com/<org>/vaultmind-cli.git .vaultmind
cd .vaultmind && npm install \\
  && pip install -r requirements.txt --break-system-packages`,
  },
  {
    id: "start",
    title: "Start background services",
    desc: "Spins up both the file watcher and the web app in one process.",
    filename: "terminal",
    fileKind: "term",
    code: "npm run vaultmind:start",
    noteKind: "info",
    note: "Runs the watcher and the web server together — leave it running in a spare tab.",
  },
  {
    id: "open",
    title: "Open the web app",
    desc: "The graph and trust interface render immediately, even with zero nodes.",
    link: "http://localhost:3000",
  },
];

const REQS = [
  { id: "cli", label: "Claude Code or Codex CLI", hint: "cli" },
  { id: "node", label: "Node.js", hint: "≥ 18" },
  { id: "py", label: "Python 3", hint: "≥ 3.10" },
  { id: "git", label: "Git", hint: "any" },
];

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function FileIcon({ color = "currentColor" }: { color?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9l-6-6z" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M13 3v6h6" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

function TermIcon({ color = "currentColor" }: { color?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M5 7l4 4-4 4" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 17h7" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function CheckIcon({ color = "currentColor", size = 14 }: { color?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M5 12l5 5L20 6" stroke={color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CopyIcon({ color = "currentColor" }: { color?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <rect x="9" y="9" width="11" height="11" rx="2" stroke={color} strokeWidth="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h8" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function RefreshIcon({ color = "currentColor" }: { color?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M4 12a8 8 0 0 1 13.7-5.6L20 8M20 4v4h-4M20 12a8 8 0 0 1-13.7 5.6L4 16M4 20v-4h4" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function InfoIcon({ color = "currentColor" }: { color?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.8" />
      <path d="M12 11v5M12 8h.01" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function BoltIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
      <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" fill="var(--accent)" />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// useCopy hook
// ---------------------------------------------------------------------------

function useCopy() {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const copy = useCallback((text: string, key: string) => {
    const done = () => {
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 1600);
    };
    try { navigator.clipboard.writeText(text).then(done, done); } catch { done(); }
  }, []);
  return { copiedKey, copy };
}

// ---------------------------------------------------------------------------
// SetupPage
// ---------------------------------------------------------------------------

export default function SetupPage() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [checking, setChecking] = useState(false);
  const [reqsMet, setReqsMet] = useState(false);
  const { copiedKey, copy } = useCopy();

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

  const toggleStep = (id: string) => setDone(d => ({ ...d, [id]: !d[id] }));

  const checkSetup = () => {
    if (checking) return;
    setChecking(true);
    setTimeout(() => { setChecking(false); setReqsMet(true); }, 1400);
  };

  const doneCount = STEPS.filter(s => done[s.id]).length;
  const allDone = doneCount === STEPS.length;

  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg)", color: "var(--text)",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
      fontSize: 14, lineHeight: 1.5, WebkitFontSmoothing: "antialiased",
    }}>
      <style>{`
        @keyframes vm-fade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes vm-spin { to { transform: rotate(360deg); } }
        @keyframes vm-pulse { 0%, 100% { opacity: .5; } 50% { opacity: 1; } }
      `}</style>

      <VaultNav theme={theme} onToggle={toggleTheme} />

      <main style={{
        maxWidth: 1140, margin: "0 auto", padding: "40px 24px 80px",
        display: "grid", gridTemplateColumns: "268px 1fr", gap: 36, alignItems: "start",
      }}>
        {/* LEFT RAIL */}
        <aside style={{ position: "sticky", top: 88, display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Progress */}
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>Progress</span>
              <span style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12, color: "var(--muted)" }}>
                {doneCount}/{STEPS.length}
              </span>
            </div>
            <div style={{ height: 6, borderRadius: 9999, background: "var(--inset)", overflow: "hidden", marginBottom: 16 }}>
              <div style={{
                height: "100%",
                width: `${Math.round((doneCount / STEPS.length) * 100)}%`,
                background: "linear-gradient(90deg, var(--green), #56d364)",
                borderRadius: 9999,
                transition: "width .45s cubic-bezier(.4,0,.2,1)",
              }} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {STEPS.map((s, i) => {
                const isDone = !!done[s.id];
                return (
                  <div key={s.id} onClick={() => toggleStep(s.id)} style={{
                    display: "flex", alignItems: "center", gap: 9,
                    padding: "7px 8px", borderRadius: 7, cursor: "pointer",
                  }}>
                    <span style={{
                      flexShrink: 0, width: 18, height: 18, borderRadius: "50%",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 11, fontFamily: "var(--font-jetbrains-mono, monospace)",
                      background: isDone ? "var(--green)" : "transparent",
                      border: `1.5px solid ${isDone ? "var(--green)" : "var(--faint)"}`,
                      color: isDone ? "#fff" : "var(--muted)",
                      transition: "all .2s",
                    }}>
                      {isDone ? "✓" : String(i + 1)}
                    </span>
                    <span style={{
                      fontSize: 12.5,
                      color: isDone ? "var(--muted)" : "var(--text)",
                      textDecoration: isDone ? "line-through" : "none",
                      textDecorationColor: "var(--faint)",
                    }}>{s.title}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Requirements */}
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>Requirements</span>
              <span style={{
                fontSize: 11,
                color: reqsMet ? "var(--green)" : "var(--faint)",
                fontFamily: "var(--font-jetbrains-mono, monospace)",
              }}>
                {reqsMet ? "all detected" : "not checked"}
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 14 }}>
              {REQS.map(r => (
                <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <span style={{ flexShrink: 0, width: 16, height: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {reqsMet
                      ? <CheckIcon color="var(--green)" size={13} />
                      : <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="var(--faint)" strokeWidth="1.8" /></svg>
                    }
                  </span>
                  <span style={{ fontSize: 12.5, color: "var(--text)", flex: 1 }}>{r.label}</span>
                  <span style={{ fontSize: 11, fontFamily: "var(--font-jetbrains-mono, monospace)", color: "var(--muted)" }}>{r.hint}</span>
                </div>
              ))}
            </div>
            <button onClick={checkSetup} style={{
              width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
              padding: 8, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8,
              color: "var(--text)", fontSize: 12.5, fontWeight: 500, cursor: "pointer",
            }}>
              <span style={{ display: "inline-flex", ...(checking ? { animation: "vm-spin .9s linear infinite" } : {}) }}>
                <RefreshIcon color="var(--muted)" />
              </span>
              {checking ? "Checking…" : reqsMet ? "Re-check setup" : "Check setup"}
            </button>
          </div>
        </aside>

        {/* MAIN COLUMN */}
        <section style={{ minWidth: 0 }}>
          <div style={{ marginBottom: 8, fontSize: 12, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--accent)" }}>
            Get started
          </div>
          <h1 style={{ margin: "0 0 10px", fontSize: 30, lineHeight: 1.2, fontWeight: 700, letterSpacing: "-.5px" }}>
            Wire VaultMind into your agent
          </h1>
          <p style={{ margin: "0 0 24px", fontSize: 15, color: "var(--muted)", maxWidth: "62ch" }}>
            Drop in a hook, start the watcher, open the graph. Copy-paste each block in order and you'll be capturing intent in under a minute.
          </p>

          {/* One-line installer */}
          <div style={{
            background: "linear-gradient(180deg, color-mix(in srgb, var(--accent) 10%, var(--surface)), var(--surface))",
            border: "1px solid color-mix(in srgb, var(--accent) 35%, var(--border))",
            borderRadius: 12, padding: "16px 18px", marginBottom: 28,
            display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
          }}>
            <div style={{ flex: 1, minWidth: 240 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <BoltIcon />
                <span style={{ fontWeight: 600, fontSize: 13.5 }}>One-line install</span>
                <span style={{ fontSize: 11, color: "var(--muted)" }}>— skip the steps below</span>
              </div>
              <div style={{
                display: "flex", alignItems: "center", gap: 10,
                background: "var(--inset)", border: "1px solid var(--border)", borderRadius: 8,
                padding: "9px 12px", fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12.5,
                color: "var(--text)", overflowX: "auto",
              }}>
                <span style={{ color: "var(--green)", userSelect: "none" }}>$</span>
                <span style={{ whiteSpace: "nowrap" }}>curl -sSL https://vaultmind.dev/install.sh | bash</span>
              </div>
            </div>
            <button
              onClick={() => copy("curl -sSL https://vaultmind.dev/install.sh | bash", "installer")}
              style={{
                flexShrink: 0, display: "flex", alignItems: "center", gap: 7, padding: "9px 16px",
                background: "var(--accent-btn)", border: "1px solid color-mix(in srgb, #fff 14%, var(--accent-btn))",
                borderRadius: 8, color: "var(--accent-fg)", fontSize: 13, fontWeight: 600, cursor: "pointer",
              }}
            >
              {copiedKey === "installer" ? <CheckIcon color="#fff" /> : <CopyIcon color="#fff" />}
              {copiedKey === "installer" ? "Copied" : "Copy"}
            </button>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 14, margin: "0 2px 24px" }}>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
            <span style={{ fontSize: 11.5, color: "var(--faint)", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>or step through it</span>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>

          {/* Step cards */}
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {STEPS.map((s, i) => {
              const isDone = !!done[s.id];
              const copyKey = `step-${s.id}`;
              const amberColor = theme === "dark" ? "#d29922" : "#9a6700";
              const accentColor = theme === "dark" ? "#388bfd" : "#0969da";
              const greenColor = theme === "dark" ? "#3fb950" : "#1a7f37";

              return (
                <div key={s.id} style={{
                  position: "relative",
                  background: "var(--surface)",
                  border: `1px solid ${isDone ? `color-mix(in srgb, ${greenColor} 45%, var(--border))` : "var(--border)"}`,
                  borderRadius: 12, padding: "20px 20px 20px 22px",
                  transition: "border-color .25s",
                  animation: "vm-fade .4s both",
                }}>
                  <div style={{
                    position: "absolute", left: 0, top: 18, bottom: 18,
                    width: 3, borderRadius: "0 3px 3px 0",
                    background: isDone ? greenColor : "transparent",
                    transition: "background .25s",
                  }} />

                  <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
                    <button onClick={() => toggleStep(s.id)} style={{
                      flexShrink: 0, width: 32, height: 32, borderRadius: 9,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontFamily: "var(--font-jetbrains-mono, monospace)", fontWeight: 600, fontSize: 14,
                      cursor: "pointer",
                      background: isDone ? greenColor : "var(--surface-2)",
                      border: `1.5px solid ${isDone ? greenColor : "var(--border)"}`,
                      color: isDone ? "#fff" : "var(--text)",
                      transition: "all .25s",
                    }}>
                      {isDone ? <CheckIcon color="#fff" /> : String(i + 1)}
                    </button>

                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 3 }}>
                        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, letterSpacing: "-.2px" }}>{s.title}</h3>
                        {s.tag && (
                          <span style={{
                            padding: "2px 8px", borderRadius: 9999,
                            fontSize: 11, fontFamily: "var(--font-jetbrains-mono, monospace)",
                            background: `rgba(${theme === "dark" ? "210,153,34,.15" : "154,103,0,.12"})`,
                            color: amberColor,
                            border: `1px solid color-mix(in srgb, ${amberColor} 40%, transparent)`,
                          }}>{s.tag}</span>
                        )}
                      </div>
                      <p style={{ margin: 0, fontSize: 13.5, color: "var(--muted)" }}>{s.desc}</p>

                      {s.code && (
                        <div style={{
                          marginTop: 14, background: "var(--inset)", border: "1px solid var(--border)",
                          borderRadius: 10, overflow: "hidden",
                        }}>
                          <div style={{
                            display: "flex", alignItems: "center", justifyContent: "space-between",
                            padding: "7px 10px 7px 12px",
                            borderBottom: "1px solid var(--border-muted)",
                            background: "var(--surface-2)",
                          }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
                              {s.fileKind === "term" ? <TermIcon color="var(--faint)" /> : <FileIcon color="var(--faint)" />}
                              <span style={{
                                fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12, color: "var(--muted)",
                                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                              }}>{s.filename}</span>
                            </div>
                            <button onClick={() => copy(s.code!, copyKey)} style={{
                              display: "flex", alignItems: "center", gap: 6, padding: "4px 10px",
                              background: "transparent", border: "1px solid var(--border)", borderRadius: 6,
                              color: copiedKey === copyKey ? "var(--green)" : "var(--muted)",
                              fontSize: 12, fontWeight: 500, cursor: "pointer",
                            }}>
                              {copiedKey === copyKey ? <CheckIcon color="var(--green)" size={12} /> : <CopyIcon color="var(--muted)" />}
                              {copiedKey === copyKey ? "Copied" : "Copy"}
                            </button>
                          </div>
                          <pre style={{
                            margin: 0, padding: "14px 16px", overflowX: "auto",
                            fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12.5, lineHeight: 1.7,
                            color: "var(--text)",
                          }}><code>{s.code}</code></pre>
                        </div>
                      )}

                      {s.link && (
                        <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                          <a href={s.link} target="_blank" rel="noreferrer" style={{
                            display: "inline-flex", alignItems: "center", gap: 9, padding: "10px 14px",
                            background: "var(--inset)", border: "1px solid var(--border)", borderRadius: 9,
                            textDecoration: "none", fontFamily: "var(--font-jetbrains-mono, monospace)",
                            fontSize: 13, color: accentColor, fontWeight: 500,
                          }}>
                            <span style={{
                              width: 7, height: 7, borderRadius: "50%",
                              background: greenColor,
                              boxShadow: `0 0 0 3px rgba(${theme === "dark" ? "63,185,80,.15" : "26,127,55,.12"})`,
                              animation: "vm-pulse 2s infinite",
                            }} />
                            {s.link}
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M7 17L17 7M17 7H9M17 7v8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
                          </a>
                          <span style={{ fontSize: 12.5, color: "var(--muted)" }}>localhost:3000</span>
                        </div>
                      )}

                      {s.note && (
                        <div style={{
                          marginTop: 12, display: "flex", alignItems: "flex-start", gap: 8,
                          padding: "9px 12px",
                          background: s.noteKind === "amber"
                            ? `rgba(${theme === "dark" ? "210,153,34,.15" : "154,103,0,.12"})`
                            : "var(--surface-2)",
                          border: `1px solid ${s.noteKind === "amber"
                            ? `color-mix(in srgb, ${amberColor} 35%, transparent)`
                            : "var(--border)"}`,
                          borderRadius: 8,
                        }}>
                          <span style={{ flexShrink: 0, marginTop: 1, color: s.noteKind === "amber" ? amberColor : accentColor }}>
                            <InfoIcon color={s.noteKind === "amber" ? amberColor : accentColor} />
                          </span>
                          <span style={{ fontSize: 12.5, color: "var(--text)" }}>
                            {s.noteKicker && <span style={{ color: s.noteKind === "amber" ? amberColor : accentColor, fontWeight: 600 }}>{s.noteKicker}</span>}
                            {s.note}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Success footer */}
          <div style={{
            marginTop: 26,
            background: allDone
              ? `color-mix(in srgb, var(--green) 7%, var(--surface))`
              : "var(--surface)",
            border: allDone
              ? `1px solid color-mix(in srgb, var(--green) 45%, var(--border))`
              : "1px dashed var(--border)",
            borderRadius: 12, padding: 20,
            display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
          }}>
            <div style={{
              flexShrink: 0, width: 40, height: 40, borderRadius: 11,
              background: "var(--green-dim)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <CheckIcon color="var(--green)" size={20} />
            </div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={{ fontWeight: 600, fontSize: 14.5 }}>
                {allDone ? "All set — VaultMind is live" : "Finish the steps to go live"}
              </div>
              <div style={{ fontSize: 13, color: "var(--muted)" }}>
                {allDone
                  ? "Your agent is now committing intent on every turn."
                  : `${doneCount} of ${STEPS.length} steps complete.`
                }
              </div>
            </div>
            <Link href="/graph" style={{
              flexShrink: 0, display: "flex", alignItems: "center", gap: 8, padding: "10px 18px",
              background: "var(--accent-btn)", border: "1px solid color-mix(in srgb, #fff 14%, var(--accent-btn))",
              borderRadius: 9, color: "var(--accent-fg)", fontSize: 13.5, fontWeight: 600, cursor: "pointer",
              textDecoration: "none",
            }}>
              Open the graph <ArrowRightIcon />
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}
