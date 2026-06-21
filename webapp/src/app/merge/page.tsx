"use client";

import { useEffect, useState, useCallback } from "react";
import type { ConflictFile, ConflictSummary } from "../../lib/conflicts";

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function SunIcon({ size = 15, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="4" stroke={color} strokeWidth="2" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function MoonIcon({ size = 15, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" stroke={color} strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

function CheckIcon({ size = 13, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M5 12l5 5L20 6" stroke={color} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DotIcon({ size = 13, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="5" stroke={color} strokeWidth="2" />
    </svg>
  );
}

function AlertIcon({ size = 13, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function InfoIcon({ size = 13, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.8" />
      <path d="M12 11v5M12 8h.01" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function ArrowUpIcon({ size = 12, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M12 5v14M5 12l7-7 7 7" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ArrowDownIcon({ size = 12, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M12 19V5M5 12l7 7 7-7" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function LockIcon({ size = 15, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="4" y="10" width="16" height="11" rx="2" stroke={color} strokeWidth="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke={color} strokeWidth="2" />
    </svg>
  );
}

function VaultIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
      <path d="M12 2l8 4.5v9L12 22l-8-6.5v-9L12 2z" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
      <circle cx="12" cy="11" r="2.4" fill="#fff" />
    </svg>
  );
}

function GraphIcon({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="6" cy="6" r="2.4" stroke={color} strokeWidth="2" />
      <circle cx="6" cy="18" r="2.4" stroke={color} strokeWidth="2" />
      <circle cx="18" cy="12" r="2.4" stroke={color} strokeWidth="2" />
      <path d="M6 8.4v7.2M8.2 6h4a3.6 3.6 0 0 1 3.6 3.6V12" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Types derived from server shapes — `import type` above is erased at build time,
// safe to use in client components.
// ---------------------------------------------------------------------------

type HunkLine = { no: number; text: string };
type ConflictHunkData = {
  index: number;
  title: string;
  ours: string[];
  theirs: string[];
  oursLabel: string;
  theirsLabel: string;
  anchor: string;
};
type Segment =
  | { type: "context"; lines: HunkLine[] }
  | { type: "conflict"; hunk: ConflictHunkData };

type FileData = Omit<ConflictFile, "segments"> & { segments: Segment[] };
type Summary = ConflictSummary;

type Choice = "ours" | "theirs" | "both";
type Resolutions = Record<number, Choice>;

interface ScanState {
  blocked: true;
  message: string;
  snippet: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MergePage() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [summaries, setSummaries] = useState<Summary[] | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [fileData, setFileData] = useState<FileData | null>(null);
  const [resolutions, setResolutions] = useState<Resolutions>({});
  const [scan, setScan] = useState<ScanState | null>(null);
  const [toast, setToast] = useState<{ msg: string; kind: "ok" | "bad" | "info" } | null>(null);
  const [loading, setLoading] = useState(true);

  // Persist theme
  useEffect(() => {
    try {
      const stored = localStorage.getItem("vm-theme") as "dark" | "light" | null;
      if (stored === "light" || stored === "dark") {
        setTheme(stored);
        document.documentElement.setAttribute("data-vmtheme", stored);
      } else {
        document.documentElement.setAttribute("data-vmtheme", "dark");
      }
    } catch {
      document.documentElement.setAttribute("data-vmtheme", "dark");
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-vmtheme", next);
    try { localStorage.setItem("vm-theme", next); } catch {}
  };

  // Toast auto-dismiss
  const showToast = useCallback((msg: string, kind: "ok" | "bad" | "info") => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 2800);
  }, []);

  // Load conflict list
  const loadSummaries = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const res = await fetch("/api/conflicts");
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json() as { files: Summary[] };
      setSummaries(data.files);
      if (data.files.length > 0 && !activeId) {
        setActiveId(data.files[0].id);
      } else if (data.files.length === 0) {
        setActiveId(null);
        setFileData(null);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Could not reach server";
      setFetchError(`Could not load conflicts — ${msg}`);
      setSummaries([]);
    } finally {
      setLoading(false);
    }
  }, [activeId]);

  useEffect(() => { loadSummaries(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load file detail when activeId changes
  useEffect(() => {
    if (!activeId) return;
    setFileData(null);
    setResolutions({});
    setScan(null);
    fetch(`/api/conflicts/${encodeURIComponent(activeId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: FileData) => setFileData(d))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "unknown error";
        showToast(`Could not load node "${activeId}": ${msg}`, "bad");
      });
  }, [activeId]);

  const hunks = fileData
    ? fileData.segments.filter((s): s is { type: "conflict"; hunk: ConflictHunkData } => s.type === "conflict").map((s) => s.hunk)
    : [];

  const resolvedCount = hunks.filter((h) => resolutions[h.index] != null).length;
  const totalHunks = hunks.length;
  const allResolved = totalHunks > 0 && resolvedCount === totalHunks;
  const resolvedPct = totalHunks > 0 ? `${Math.round((resolvedCount / totalHunks) * 100)}%` : "0%";

  const handleResolveAll = async () => {
    if (!fileData || !allResolved) return;
    try {
      const res = await fetch(`/api/conflicts/${encodeURIComponent(fileData.id)}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolutions }),
      });
      // 200 (ok) and 422 (blocked) both return JSON; anything else is a server error
      if (!res.ok && res.status !== 422) throw new Error(`Server error ${res.status}`);
      const data = await res.json() as { ok: boolean; secretBlocked?: string; scanSnippet?: string };
      if (data.ok) {
        showToast("merged → committed 1 node to disk", "ok");
        setScan(null);
        // Reload conflict list — this file should now be resolved
        await loadSummaries();
      } else if (data.secretBlocked) {
        setScan({ blocked: true, message: data.secretBlocked, snippet: data.scanSnippet ?? "" });
        showToast("blocked — " + data.secretBlocked, "bad");
      } else {
        showToast("failed to write node", "bad");
      }
    } catch {
      showToast("network error", "bad");
    }
  };

  const handleApplySuggestion = () => {
    const suggested: Resolutions = {};
    hunks.forEach((h) => { suggested[h.index] = "theirs"; });
    setResolutions(suggested);
    showToast("Applied: accepted all incoming changes", "info");
  };

  const hasConflicts = summaries !== null && summaries.length > 0;
  const noConflicts = summaries !== null && summaries.length === 0;

  // ---------------------------------------------------------------------------
  // CSS variable helpers (read at render time)
  // ---------------------------------------------------------------------------
  const v = (name: string) => `var(${name})`;

  const toastColor = toast?.kind === "bad" ? v("--red") : toast?.kind === "info" ? v("--accent") : v("--green");
  const toastBorder = toast?.kind === "bad"
    ? "color-mix(in srgb, var(--red) 45%, var(--border))"
    : toast?.kind === "info"
    ? v("--border")
    : "color-mix(in srgb, var(--green) 45%, var(--border))";

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: v("--bg"), color: v("--text"), fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif", fontSize: 14, lineHeight: 1.5, WebkitFontSmoothing: "antialiased" }}>

      {/* HEADER */}
      <header style={{ flex: "none", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, height: 56, padding: "0 20px", background: v("--bg"), borderBottom: `1px solid ${v("--border")}`, position: "sticky", top: 0, zIndex: 30 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 26, height: 26, borderRadius: 7, background: "linear-gradient(135deg, var(--accent), #7d5bed)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "inset 0 0 0 1px rgba(255,255,255,.12)" }}>
              <VaultIcon />
            </div>
            <span style={{ fontWeight: 600, fontSize: 15, letterSpacing: "-.2px" }}>VaultMind</span>
          </div>
          <nav style={{ display: "flex", alignItems: "center", gap: 2, marginLeft: 6 }}>
            {(["Setup", "Graph", "Intent log"] as const).map((label) => (
              <a key={label} href={`/${label.toLowerCase().replace(" ", "-")}`} style={{ padding: "6px 11px", borderRadius: 7, fontSize: 13, color: v("--muted"), textDecoration: "none" }}>
                {label}
              </a>
            ))}
            <span style={{ padding: "6px 11px", borderRadius: 7, fontSize: 13, color: v("--text"), fontWeight: 500, background: v("--surface"), border: `1px solid ${v("--border")}` }}>
              Merge
            </span>
          </nav>
        </div>
        <button onClick={toggleTheme} title="Toggle theme" style={{ width: 34, height: 34, display: "flex", alignItems: "center", justifyContent: "center", background: v("--surface"), border: `1px solid ${v("--border")}`, borderRadius: 8, color: v("--muted"), cursor: "pointer" }}>
          {theme === "dark" ? <MoonIcon color="var(--muted)" /> : <SunIcon color="var(--muted)" />}
        </button>
      </header>

      {/* LOADING */}
      {loading && (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: v("--muted"), fontSize: 13 }}>
          Loading…
        </div>
      )}

      {/* HAS CONFLICTS */}
      {!loading && hasConflicts && fileData && (
        <>
          {/* CONFLICT BAR */}
          <div style={{ flex: "none", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap", padding: "16px 24px", borderBottom: `1px solid ${v("--border")}`, background: v("--surface-2") }}>
            <div style={{ display: "flex", alignItems: "center", gap: 13, minWidth: 0 }}>
              <div style={{ width: 34, height: 34, borderRadius: 9, background: v("--amber-dim"), display: "flex", alignItems: "center", justifyContent: "center", flex: "none" }}>
                <GraphIcon size={17} color="var(--amber)" />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
                  <h1 style={{ margin: 0, fontSize: 17, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace", letterSpacing: "-.2px" }}>{fileData.displayName}</h1>
                  <span style={{ padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600, background: v("--amber-dim"), color: v("--amber"), border: "1px solid color-mix(in srgb, var(--amber) 40%, transparent)" }}>
                    conflicting edits
                  </span>
                </div>
                <div style={{ fontSize: 12, color: v("--muted"), marginTop: 1 }}>Two sessions independently modified this node. Pick one approach per hunk.</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              {/* File navigator when multiple conflicted nodes */}
              {(summaries?.length ?? 0) > 1 && (
                <select
                  value={activeId ?? ""}
                  onChange={(e) => setActiveId(e.target.value)}
                  style={{ padding: "6px 10px", background: v("--surface"), border: `1px solid ${v("--border")}`, borderRadius: 7, color: v("--text"), fontSize: 12, cursor: "pointer" }}
                >
                  {summaries!.map((s) => (
                    <option key={s.id} value={s.id}>{s.displayName}</option>
                  ))}
                </select>
              )}
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 12, color: v("--muted") }}>{resolvedCount} of {totalHunks} resolved</div>
                <div style={{ marginTop: 5, width: 150, height: 6, borderRadius: 999, background: v("--inset"), overflow: "hidden" }}>
                  <div style={{ height: "100%", width: resolvedPct, background: "linear-gradient(90deg, var(--green), #56d364)", borderRadius: 999, transition: "width .35s" }} />
                </div>
              </div>
              <button
                onClick={handleResolveAll}
                disabled={!allResolved}
                style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "9px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                  cursor: allResolved ? "pointer" : "not-allowed",
                  background: allResolved ? "var(--accent-btn)" : "var(--surface)",
                  color: allResolved ? "#fff" : "var(--faint)",
                  border: allResolved ? "1px solid color-mix(in srgb, #fff 14%, var(--accent-btn))" : `1px solid ${v("--border")}`,
                  opacity: allResolved ? 1 : 0.7,
                  transition: "all .2s",
                }}
              >
                <CheckIcon size={14} color="currentColor" />
                Mark resolved &amp; commit
              </button>
            </div>
          </div>

          {/* LEGEND */}
          <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 18, padding: "10px 24px", borderBottom: `1px solid ${v("--border")}`, background: v("--bg"), fontSize: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, color: v("--muted") }}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: "var(--blue-line)", border: "1px solid color-mix(in srgb, var(--accent) 50%, transparent)", display: "inline-block" }} />
              Current — this session
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 7, color: v("--muted") }}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: "var(--purple-line)", border: "1px solid color-mix(in srgb, var(--purple) 55%, transparent)", display: "inline-block" }} />
              Incoming — {fileData.sessionLabel} (disk)
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 7, color: v("--muted"), marginLeft: "auto", fontFamily: "'JetBrains Mono', monospace" }}>
              base {fileData.baseRef} · HEAD {fileData.headRef}
            </div>
          </div>

          {/* BODY */}
          <main style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 300px", minHeight: 0 }}>

            {/* DIFF */}
            <section style={{ minWidth: 0, overflowY: "auto", background: v("--inset") }}>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5, lineHeight: 1.7 }}>
                {fileData.segments.map((seg, si) => {
                  if (seg.type === "context") {
                    return (
                      <div key={si}>
                        {seg.lines.map((ln) => (
                          <div key={ln.no} style={{ display: "flex" }}>
                            <span style={{ flex: "none", width: 48, textAlign: "right", padding: "1px 12px 1px 0", color: v("--faint"), userSelect: "none", background: v("--surface-2"), borderRight: `1px solid ${v("--border-muted")}` }}>{ln.no}</span>
                            <span style={{ padding: "1px 16px", color: v("--text"), whiteSpace: "pre" }}>{ln.text}</span>
                          </div>
                        ))}
                      </div>
                    );
                  }

                  const { hunk } = seg;
                  const choice = resolutions[hunk.index];
                  const resolved = choice != null;

                  const resultLines: Array<{ no: number; text: string }> = (() => {
                    if (!resolved) return [];
                    const baseNo = 1;
                    const src = choice === "ours" ? hunk.ours : choice === "theirs" ? hunk.theirs : [...hunk.ours, ...hunk.theirs];
                    return src.map((t, i) => ({ no: baseNo + i, text: t }));
                  })();

                  const tookLabel = choice === "ours" ? "current change" : choice === "theirs" ? "incoming change" : "both changes";

                  return (
                    <div key={si} id={hunk.anchor} style={{ borderTop: `1px solid ${v("--border")}`, borderBottom: `1px solid ${v("--border")}`, margin: 0, animation: "vm-fade .35s both" }}>

                      {/* Hunk header */}
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "7px 16px", background: v("--surface"), borderBottom: `1px solid ${v("--border-muted")}` }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                          <span style={{ display: "inline-flex", color: resolved ? "var(--green)" : "var(--amber)" }}>
                            {resolved ? <CheckIcon color="var(--green)" /> : <DotIcon color="var(--amber)" />}
                          </span>
                          <span style={{ fontSize: 12, fontWeight: 600, color: v("--text"), fontFamily: "-apple-system, sans-serif" }}>{hunk.title}</span>
                        </div>
                        <span style={{ fontSize: 11, color: v("--muted"), fontFamily: "-apple-system, sans-serif" }}>
                          {resolved ? (choice === "ours" ? "kept current" : choice === "theirs" ? "kept incoming" : "kept both") : "unresolved"}
                        </span>
                      </div>

                      {/* Resolved view */}
                      {resolved && (
                        <>
                          <div style={{ background: "var(--green-line)" }}>
                            {resultLines.map((ln) => (
                              <div key={ln.no} style={{ display: "flex" }}>
                                <span style={{ flex: "none", width: 48, textAlign: "right", padding: "1px 12px 1px 0", color: v("--faint"), userSelect: "none", background: v("--surface-2"), borderRight: `1px solid ${v("--border-muted")}` }}>{ln.no}</span>
                                <span style={{ flex: "none", width: 20, textAlign: "center", color: "var(--green)", userSelect: "none" }}>✓</span>
                                <span style={{ padding: "1px 12px 1px 0", color: v("--text"), whiteSpace: "pre" }}>{ln.text}</span>
                              </div>
                            ))}
                          </div>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 16px", background: v("--surface"), borderTop: `1px solid ${v("--border-muted")}` }}>
                            <span style={{ fontSize: 11.5, color: "var(--green)", fontFamily: "-apple-system, sans-serif", display: "flex", alignItems: "center", gap: 6 }}>
                              Took <b style={{ fontWeight: 600 }}>{tookLabel}</b>
                            </span>
                            <button onClick={() => setResolutions((r) => { const n = { ...r }; delete n[hunk.index]; return n; })} style={{ background: "transparent", border: "none", color: v("--muted"), fontSize: 11.5, cursor: "pointer", fontFamily: "-apple-system, sans-serif", textDecoration: "underline", textUnderlineOffset: 2 }}>
                              Re-resolve
                            </button>
                          </div>
                        </>
                      )}

                      {/* Unresolved: ours / theirs */}
                      {!resolved && (
                        <div>
                          {/* Ours */}
                          <div style={{ background: "var(--blue-line)" }}>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 16px", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}>
                              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--accent)", fontFamily: "-apple-system, sans-serif", display: "flex", alignItems: "center", gap: 6 }}>
                                <ArrowUpIcon color="var(--accent)" />
                                Current change · this session
                              </span>
                              <button onClick={() => setResolutions((r) => ({ ...r, [hunk.index]: "ours" }))} style={{ padding: "3px 10px", background: "var(--accent-btn)", border: "1px solid color-mix(in srgb, #fff 14%, var(--accent-btn))", borderRadius: 6, color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: "-apple-system, sans-serif" }}>
                                Accept current
                              </button>
                            </div>
                            {hunk.ours.map((text, i) => (
                              <div key={i} style={{ display: "flex" }}>
                                <span style={{ flex: "none", width: 48, textAlign: "right", padding: "1px 12px 1px 0", color: v("--faint"), userSelect: "none", background: v("--surface-2"), borderRight: `1px solid ${v("--border-muted")}` }}>{i + 1}</span>
                                <span style={{ flex: "none", width: 20, textAlign: "center", color: "var(--accent)", userSelect: "none" }}>+</span>
                                <span style={{ padding: "1px 12px 1px 0", color: v("--text"), whiteSpace: "pre" }}>{text}</span>
                              </div>
                            ))}
                          </div>

                          {/* Theirs */}
                          <div style={{ background: "var(--purple-line)", borderTop: `1px solid ${v("--border-muted")}` }}>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 16px", background: "color-mix(in srgb, var(--purple) 13%, transparent)" }}>
                              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--purple)", fontFamily: "-apple-system, sans-serif", display: "flex", alignItems: "center", gap: 6 }}>
                                <ArrowDownIcon color="var(--purple)" />
                                Incoming change · {hunk.theirsLabel}
                              </span>
                              <button onClick={() => setResolutions((r) => ({ ...r, [hunk.index]: "theirs" }))} style={{ padding: "3px 10px", background: "var(--purple)", border: "1px solid color-mix(in srgb, #fff 14%, var(--purple))", borderRadius: 6, color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: "-apple-system, sans-serif" }}>
                                Accept incoming
                              </button>
                            </div>
                            {hunk.theirs.map((text, i) => (
                              <div key={i} style={{ display: "flex" }}>
                                <span style={{ flex: "none", width: 48, textAlign: "right", padding: "1px 12px 1px 0", color: v("--faint"), userSelect: "none", background: v("--surface-2"), borderRight: `1px solid ${v("--border-muted")}` }}>{i + 1}</span>
                                <span style={{ flex: "none", width: 20, textAlign: "center", color: "var(--purple)", userSelect: "none" }}>+</span>
                                <span style={{ padding: "1px 12px 1px 0", color: v("--text"), whiteSpace: "pre" }}>{text}</span>
                              </div>
                            ))}
                          </div>

                          {/* Keep both */}
                          <div style={{ display: "flex", justifyContent: "center", padding: 7, background: v("--surface"), borderTop: `1px solid ${v("--border-muted")}` }}>
                            <button onClick={() => setResolutions((r) => ({ ...r, [hunk.index]: "both" }))} style={{ padding: "4px 14px", background: "transparent", border: `1px solid ${v("--border")}`, borderRadius: 6, color: v("--muted"), fontSize: 11.5, fontWeight: 500, cursor: "pointer", fontFamily: "-apple-system, sans-serif" }}>
                              Keep both changes
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>

            {/* RIGHT RAIL */}
            <aside style={{ borderLeft: `1px solid ${v("--border")}`, background: v("--surface-2"), overflowY: "auto", padding: "18px 18px 28px" }}>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: v("--faint"), marginBottom: 11 }}>Conflicts</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 22 }}>
                {hunks.map((h) => {
                  const choice = resolutions[h.index];
                  const resolved = choice != null;
                  const color = resolved ? "var(--green)" : "var(--amber)";
                  const border = resolved
                    ? "color-mix(in srgb, var(--green) 35%, var(--border))"
                    : "var(--border)";
                  return (
                    <a key={h.index} href={`#${h.anchor}`} style={{ display: "flex", alignItems: "flex-start", gap: 9, padding: "10px 11px", background: v("--surface"), border: `1px solid ${border}`, borderRadius: 9, textDecoration: "none" }}>
                      <span style={{ flex: "none", marginTop: 1, display: "inline-flex", color }}>
                        {resolved ? <CheckIcon color={color} /> : <DotIcon color={color} />}
                      </span>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 12.5, color: v("--text"), fontWeight: 500 }}>{h.title}</div>
                        <div style={{ fontSize: 11, color, marginTop: 1 }}>
                          {resolved ? (choice === "ours" ? "kept current" : choice === "theirs" ? "kept incoming" : "kept both") : "needs a choice"}
                        </div>
                      </div>
                    </a>
                  );
                })}
              </div>

              {/* Scan blocked */}
              {scan?.blocked && (
                <div style={{ background: "var(--red-dim)", border: "1px solid color-mix(in srgb, var(--red) 45%, transparent)", borderRadius: 10, padding: 13, marginBottom: 18 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--red)", fontWeight: 600, fontSize: 12.5, marginBottom: 6 }}>
                    <LockIcon color="var(--red)" />
                    Commit blocked by scanner
                  </div>
                  <div style={{ fontSize: 12, color: v("--text"), lineHeight: 1.55 }}>{scan.message}</div>
                  {scan.snippet && (
                    <div style={{ marginTop: 8, fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: "var(--red)", background: v("--inset"), border: "1px solid color-mix(in srgb, var(--red) 30%, transparent)", borderRadius: 6, padding: "7px 9px" }}>
                      {scan.snippet}
                    </div>
                  )}
                </div>
              )}

              {/* VaultMind suggests */}
              <div style={{ background: v("--surface"), border: `1px solid ${v("--border")}`, borderRadius: 10, padding: 13 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, fontWeight: 600, marginBottom: 6 }}>
                  <InfoIcon color="var(--accent)" />
                  VaultMind suggests
                </div>
                <div style={{ fontSize: 12, color: v("--muted"), lineHeight: 1.6 }}>
                  Prefer the <b style={{ color: v("--text") }}>incoming</b> changes — they reflect the most recent session and avoid losing context captured after this branch diverged.
                </div>
                <button
                  onClick={handleApplySuggestion}
                  style={{ width: "100%", marginTop: 11, padding: 8, background: v("--surface-2"), border: `1px solid ${v("--border")}`, borderRadius: 7, color: v("--text"), fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                >
                  Apply suggestion
                </button>
              </div>
            </aside>
          </main>
        </>
      )}

      {/* FETCH ERROR */}
      {!loading && fetchError && (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--red)", fontSize: 13, padding: "40px 24px", textAlign: "center" }}>
          {fetchError}
        </div>
      )}

      {/* NO CONFLICTS */}
      {!loading && !fetchError && noConflicts && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "80px 24px", textAlign: "center" }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: "var(--green-dim)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 20, flex: "none" }}>
            <CheckIcon size={26} color="var(--green)" />
          </div>
          <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: "-.3px", marginBottom: 8, color: v("--text") }}>No conflicts</div>
          <div style={{ fontSize: 13.5, color: v("--muted"), maxWidth: "38ch", lineHeight: 1.6, margin: "0 auto" }}>
            All sessions are in sync. VaultMind will surface conflicts here as soon as it detects divergent edits.
          </div>
          <div style={{ marginTop: 28, display: "inline-flex", alignItems: "center", gap: 10, padding: "10px 16px", background: v("--surface"), border: `1px solid ${v("--border")}`, borderRadius: 10, fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: v("--muted") }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 0 3px var(--green-dim)", flex: "none", display: "inline-block" }} />
            monitoring · vault/nodes/ · no conflicts
          </div>
        </div>
      )}

      {/* Loading but has active ID — file detail loading */}
      {!loading && hasConflicts && !fileData && (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: v("--muted"), fontSize: 13 }}>
          Loading node…
        </div>
      )}

      {/* TOAST */}
      {toast && (
        <div style={{ position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)", zIndex: 60, display: "flex", alignItems: "center", gap: 9, background: "rgba(13,17,23,.97)", border: `1px solid ${toastBorder}`, borderRadius: 10, padding: "11px 15px", boxShadow: "0 10px 30px rgba(1,4,9,.6)", animation: "vm-toast .25s both" }}>
          <span style={{ display: "inline-flex", color: toastColor }}>
            {toast.kind === "bad" ? <AlertIcon color={toastColor} /> : toast.kind === "info" ? <InfoIcon color={toastColor} /> : <CheckIcon color={toastColor} />}
          </span>
          <span style={{ fontSize: 13, color: "#e6edf3", fontFamily: "'JetBrains Mono', monospace" }}>{toast.msg}</span>
        </div>
      )}
    </div>
  );
}
