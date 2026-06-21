"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

// ---------------------------------------------------------------------------
// Shared nav
// ---------------------------------------------------------------------------

function VaultNav({ theme, onToggle, liveCount }: {
  theme: "dark" | "light";
  onToggle: () => void;
  liveCount: number;
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
      background: "var(--bg)", borderBottom: "1px solid var(--border)", zIndex: 30,
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
            width: 7, height: 7, borderRadius: "50%", background: "var(--green)",
            animation: "vm-livedot 1.6s ease-in-out infinite",
          }} />
          Watching · <span style={{ color: "var(--text)", fontWeight: 500, marginLeft: 3 }}>+{liveCount} today</span>
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
// Graph data
// ---------------------------------------------------------------------------

interface GNode {
  id: string; label: string; group: string; groupColor: string;
  status: "clean" | "pending" | "blocked";
  cx: number; cy: number; r: number;
  isCenter?: boolean; isHub?: boolean; orphan?: boolean;
  type: string; created: string; intentRef: string; deg: number;
  content?: string;
}

interface GEdge { a: string; b: string; spoke?: boolean; cross?: boolean; faint?: boolean; }

interface GGroup { id: string; label: string; color: string; desc: string; }

function rng(seed: number) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6D2B79F5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function buildGraph() {
  const rand = rng(20260620);
  const groups: GGroup[] = [
    { id: "auth",   label: "auth/",         color: "#5b8cff", desc: "Identity, sessions and key rotation." },
    { id: "pay",    label: "payments/",     color: "#dba53f", desc: "Billing, ledger and payouts." },
    { id: "engine", label: "graph-engine/", color: "#46c98a", desc: "Indexing, diffing and the secret scanner." },
    { id: "ui",     label: "ui/",           color: "#e07ca6", desc: "Canvas, panels and the editor surface." },
    { id: "docs",   label: "docs/",         color: "#8a9099", desc: "Specs, ADRs and onboarding." },
    { id: "tests",  label: "tests/",        color: "#3cc6cf", desc: "Unit and end-to-end coverage." },
  ];
  const pools: Record<string, string[]> = {
    auth:   ["oauth-callback.ts","session-store.ts","rotate-keys.ts","jwt-verify.ts","login-flow.md","sso-saml.ts","mfa-totp.ts","token-cache.ts","rbac-policy.ts","password-reset.ts","device-trust.ts"],
    pay:    ["stripe-webhook.ts","invoice-pdf.ts","refund-queue.ts","tax-calc.ts","ledger.ts","payout-cron.ts","dunning.md","currency-fx.ts","checkout-intent.ts","receipt-mail.ts"],
    engine: ["force-layout.ts","wikilink-parser.ts","graph-index.ts","diff-merge.ts","scan-secrets.ts","commit-hook.ts","watcher.ts","frontmatter.ts","node-store.ts","edge-resolver.ts","stream-bus.ts"],
    ui:     ["graph-canvas.tsx","node-panel.tsx","intent-log.tsx","handoff-screen.tsx","toolbar.tsx","toast.tsx","filter-rail.tsx","editor.tsx","status-pill.tsx"],
    docs:   ["architecture.md","threat-model.md","onboarding.md","hooks-spec.md","glossary.md","adr-001.md","readme.md"],
    tests:  ["scan-secrets.test.ts","merge.test.ts","layout.test.ts","e2e-handoff.spec.ts","parser.test.ts"],
  };
  const blocked: Record<string, boolean> = { "rotate-keys.ts": true, "stripe-webhook.ts": true };
  const pending: Record<string, boolean> = { "scan-secrets.ts": true, "node-panel.tsx": true, "ledger.ts": true, "jwt-verify.ts": true, "graph-index.ts": true, "threat-model.md": true, "checkout-intent.ts": true, "editor.tsx": true, "diff-merge.ts": true };
  const created = ["just now","2m ago","9m ago","26m ago","1h ago","3h ago","5h ago","yesterday","2d ago"];

  const cx0 = 500, cy0 = 380, RX = 300, RY = 235;
  const nodes: GNode[] = [];
  const edges: GEdge[] = [];
  const byId: Record<string, GNode> = {};

  const add = (n: GNode) => { nodes.push(n); byId[n.id] = n; return n; };

  add({ id: "center", label: "trust-graph-v1", group: "intent", groupColor: "#9aa0a8",
    status: "pending", cx: cx0, cy: cy0, r: 24, isCenter: true, isHub: true,
    type: "intent", created: "session start", intentRef: "—", orphan: false, deg: 0 });

  groups.forEach((grp, gi) => {
    const ang = (gi / groups.length) * Math.PI * 2 - Math.PI / 2;
    const hx = cx0 + Math.cos(ang) * RX;
    const hy = cy0 + Math.sin(ang) * RY;
    const pool = pools[grp.id];
    pool.forEach((name, idx) => {
      const isHub = idx === 0;
      let x: number, y: number;
      if (isHub) { x = hx; y = hy; }
      else {
        const a = rand() * Math.PI * 2;
        const d = 36 + rand() * 108;
        x = hx + Math.cos(a) * d;
        y = hy + Math.sin(a) * d * 0.82;
      }
      x = Math.max(46, Math.min(954, x));
      y = Math.max(48, Math.min(712, y));
      const status = blocked[name] ? "blocked" : (pending[name] ? "pending" : "clean");
      const node = add({
        id: grp.id + ":" + name, label: name, group: grp.id, groupColor: grp.color,
        status: status as "clean" | "pending" | "blocked",
        cx: x, cy: y, r: 0, isHub,
        type: name.endsWith(".md") ? "note" : "file",
        created: created[(gi * 3 + idx) % created.length],
        intentRef: "trust-graph-v1", orphan: false, deg: 0,
      });
      if (isHub) {
        edges.push({ a: "center", b: node.id, spoke: true });
      } else {
        if (rand() < 0.62) edges.push({ a: grp.id + ":" + pool[0], b: node.id });
        else { const j = 1 + Math.floor(rand() * idx); edges.push({ a: grp.id + ":" + pool[j < pool.length ? j : 0], b: node.id }); }
        if (rand() < 0.22 && idx > 2) edges.push({ a: grp.id + ":" + pool[1], b: node.id });
      }
    });
    for (let k = 0; k < 2; k++) {
      const t = pool[2 + Math.floor(rand() * (pool.length - 2))];
      if (t) edges.push({ a: "center", b: grp.id + ":" + t, faint: true });
    }
  });

  const ids = nodes.filter(n => !n.isCenter).map(n => n.id);
  for (let k = 0; k < 9; k++) {
    const a = ids[Math.floor(rand() * ids.length)];
    const b = ids[Math.floor(rand() * ids.length)];
    if (a !== b && byId[a] && byId[b] && byId[a].group !== byId[b].group) edges.push({ a, b, cross: true });
  }

  const orphanNames = ["scratch-2026-06-18.md","tmp-export.json","untitled.md","clipboard.md","draft-notes.md","wip.ts"];
  orphanNames.forEach((nm, i) => {
    const a = rand() * Math.PI * 2, d = 300 + rand() * 70;
    add({ id: "orphan:" + nm, label: nm, group: "docs", groupColor: "#6b7079", status: "clean",
      cx: Math.max(46, Math.min(954, cx0 + Math.cos(a) * d)),
      cy: Math.max(48, Math.min(712, cy0 + Math.sin(a) * d * 0.78)),
      r: 0, type: "note", created: created[i % created.length], intentRef: "—", orphan: true, isHub: false, deg: 0 });
  });

  edges.forEach(e => {
    if (byId[e.a]) byId[e.a].deg = (byId[e.a].deg || 0) + 1;
    if (byId[e.b]) byId[e.b].deg = (byId[e.b].deg || 0) + 1;
  });

  nodes.forEach(n => {
    const deg = n.deg || 1;
    n.r = n.isCenter ? 24 : (n.isHub ? 11 : Math.min(9, 4.5 + deg * 0.7));
  });

  const neighbors: Record<string, Set<string>> = {};
  edges.forEach(e => {
    (neighbors[e.a] = neighbors[e.a] || new Set()).add(e.b);
    (neighbors[e.b] = neighbors[e.b] || new Set()).add(e.a);
  });

  return { groups, nodes, edges, byId, neighbors };
}

const G = buildGraph();

// ---------------------------------------------------------------------------
// Status config
// ---------------------------------------------------------------------------

const STATUS = {
  clean:   { label: "Clean",   dot: "#46c98a", glow: "rgba(70,201,138,.18)",   color: "#46c98a", why: "Committed — matches git HEAD." },
  pending: { label: "Pending", dot: "#dba53f", glow: "rgba(219,165,63,.2)",   color: "#dba53f", why: "Modified — not yet committed." },
  blocked: { label: "Blocked", dot: "#f26d78", glow: "rgba(242,109,120,.22)",   color: "#f26d78", why: "scanForSecrets flagged a secret." },
};

// ---------------------------------------------------------------------------
// Secret scanner (client-side demo)
// ---------------------------------------------------------------------------

const SECRET_PATTERNS = [
  { re: /AKIA[0-9A-Z]{8,}/, m: "AWS access key id" },
  { re: /AWS_SECRET_ACCESS_KEY\s*[=:]/i, m: "AWS_SECRET_ACCESS_KEY assignment" },
  { re: /sk_live_[0-9A-Za-z]{6,}/, m: "Stripe live secret key" },
  { re: /sk-[0-9A-Za-z]{8,}/, m: "API secret key (sk-…)" },
  { re: /-----BEGIN [A-Z ]*PRIVATE KEY-----/, m: "PEM private key block" },
  { re: /(api[_-]?key|secret|token|password)\s*[=:]\s*['"][^'"]{8,}['"]/i, m: "hardcoded credential" },
];

function scanForSecrets(text: string): { m: string; snippet: string } | null {
  for (const p of SECRET_PATTERNS) {
    const hit = text.match(p.re);
    if (hit) return { m: p.m, snippet: hit[0].slice(0, 42) };
  }
  return null;
}

function contentFor(node: GNode, overrides: Record<string, { status?: string; content?: string }>): string {
  const ov = overrides[node.id];
  if (ov?.content != null) return ov.content;
  if (node.label === "rotate-keys.ts")
    return `// rotate-keys.ts\nimport { refreshFromVault } from "./vault";\n\nexport const AWS_SECRET_ACCESS_KEY =\n  "REDACTED_EXAMPLE_KEY";\n\nexport function rotate() {\n  return refreshFromVault(AWS_SECRET_ACCESS_KEY);\n}`;
  if (node.label === "stripe-webhook.ts")
    return `// stripe-webhook.ts\nconst STRIPE_SECRET = "REDACTED_EXAMPLE_KEY";\n\nexport function verify(req) {\n  return stripe.webhooks.constructEvent(\n    req.body, req.headers["stripe-signature"], STRIPE_SECRET\n  );\n}`;
  if (node.isCenter)
    return `---\nintent: ship the trust graph\nstatus: in progress\n---\n\nThe live map of everything the agent has\ntouched this session. Nodes commit on Stop;\nhandoff fires on SessionEnd.\n\nLinked from every working file below.`;
  const grp = G.groups.find(x => x.id === node.group);
  return `# ${node.label}\n\nLinked from [[trust-graph-v1]].\n\n${grp?.desc ?? ""}\n\n- status: ${node.status}\n- owner: @agent\n- last touched by the watcher`;
}

// ---------------------------------------------------------------------------
// GraphPage
// ---------------------------------------------------------------------------

export default function GraphPage() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [tipPos, setTipPos] = useState<{ x: number; y: number } | null>(null);
  const [query, setQuery] = useState("");
  const [activeGroup, setActiveGroup] = useState<string | null>(null);
  const [activeStatus, setActiveStatus] = useState<string | null>(null);
  const [toggles, setToggles] = useState({ tags: false, attachments: true, existingOnly: false, orphans: false });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [commitMsg, setCommitMsg] = useState("");
  const [warning, setWarning] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, { status?: string; content?: string }>>({});
  const [toast, setToast] = useState<{ msg: string; kind: "ok" | "bad" | "info" } | null>(null);
  const [liveCount, setLiveCount] = useState(4);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const showToast = useCallback((msg: string, kind: "ok" | "bad" | "info" = "ok") => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ msg, kind });
    toastTimer.current = setTimeout(() => setToast(null), 2600);
  }, []);

  const effStatus = useCallback((n: GNode): "clean" | "pending" | "blocked" => {
    const ov = overrides[n.id];
    if (ov?.status) return ov.status as "clean" | "pending" | "blocked";
    return n.status;
  }, [overrides]);

  // Visibility
  const visible = G.nodes.filter(n => n.orphan ? toggles.orphans : true);

  // Active set
  const q = query.trim().toLowerCase();
  let activeSet: Set<string> | null = null;
  if (selectedId) {
    activeSet = new Set([selectedId]);
    (G.neighbors[selectedId] || new Set()).forEach(x => activeSet!.add(x));
  } else if (q) {
    activeSet = new Set(visible.filter(n => n.label.toLowerCase().includes(q)).map(n => n.id));
  } else if (hoverId) {
    activeSet = new Set([hoverId]);
    (G.neighbors[hoverId] || new Set()).forEach(x => activeSet!.add(x));
  } else if (activeGroup) {
    activeSet = new Set(visible.filter(n => n.group === activeGroup).map(n => n.id));
  } else if (activeStatus) {
    activeSet = new Set(visible.filter(n => effStatus(n) === activeStatus).map(n => n.id));
  }
  const isActive = (id: string) => activeSet ? activeSet.has(id) : true;
  const hasFocus = !!(selectedId || q || activeGroup || activeStatus);

  // Counts
  const counts = { clean: 0, pending: 0, blocked: 0 };
  visible.forEach(n => { counts[effStatus(n)] = (counts[effStatus(n)] || 0) + 1; });

  const selected = selectedId ? G.byId[selectedId] : null;

  const saveNode = () => {
    if (!commitMsg.trim() || !selectedId) return;
    const node = G.byId[selectedId];
    const hit = scanForSecrets(draft);
    if (hit) { setWarning(`${hit.m} → "${hit.snippet}…"`); showToast("save blocked — secret detected", "bad"); return; }
    setOverrides(o => ({ ...o, [selectedId]: { status: "clean", content: draft } }));
    setEditing(false); setWarning(null); setCommitMsg("");
    setLiveCount(c => c + 1);
    showToast(`committed ${node.label} → disk`, "ok");
  };

  const toastColor = toast?.kind === "bad" ? "var(--red)" : toast?.kind === "info" ? "var(--accent)" : "var(--green)";

  return (
    <div style={{
      height: "100vh", display: "flex", flexDirection: "column",
      background: "var(--bg)", color: "var(--text)",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
      fontSize: 14, lineHeight: 1.5, WebkitFontSmoothing: "antialiased", overflow: "hidden",
    }}>
      <style>{`
        @keyframes vm-spin { to { transform: rotate(360deg); } }
        @keyframes vm-ring { 0% { transform: scale(.85); opacity: .65; } 100% { transform: scale(2); opacity: 0; } }
        @keyframes vm-livedot { 0%, 100% { opacity: .35; } 50% { opacity: 1; } }
        @keyframes vm-slidein { from { transform: translateX(24px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        @keyframes vm-toast { from { transform: translateY(8px); opacity: 0; } to { opacity: 1; } }
      `}</style>

      <VaultNav theme={theme} onToggle={toggleTheme} liveCount={liveCount} />

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>

        {/* LEFT RAIL */}
        <aside style={{
          flexShrink: 0, width: 276, background: "var(--bg)",
          borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", minHeight: 0,
        }}>
          {/* Search */}
          <div style={{ padding: "14px 14px 10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 10px" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="var(--muted)" strokeWidth="2" /><path d="M21 21l-4-4" stroke="var(--muted)" strokeWidth="2" strokeLinecap="round" /></svg>
              <input
                value={query}
                onChange={e => { setQuery(e.target.value); setSelectedId(null); }}
                placeholder="Search nodes…"
                style={{ flex: 1, minWidth: 0, background: "transparent", border: "none", outline: "none", color: "var(--text)", fontSize: 13, fontFamily: "inherit" }}
              />
              {query && <span onClick={() => setQuery("")} style={{ cursor: "pointer", color: "var(--faint)", fontSize: 14 }}>✕</span>}
            </div>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "6px 14px 16px" }}>
            {/* Display toggles */}
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)", margin: "8px 4px 8px" }}>Display</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 18 }}>
              {(["tags", "attachments", "existingOnly", "orphans"] as const).map(k => {
                const labels: Record<string, string> = { tags: "Tags", attachments: "Attachments", existingOnly: "Existing files only", orphans: "Orphans" };
                const on = toggles[k];
                return (
                  <div key={k} onClick={() => setToggles(t => ({ ...t, [k]: !t[k] }))} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "7px 8px", borderRadius: 7, cursor: "pointer" }}>
                    <span style={{ fontSize: 13, color: "var(--text)" }}>{labels[k]}</span>
                    <span style={{ flexShrink: 0, width: 30, height: 18, borderRadius: 9999, background: on ? "var(--accent)" : "var(--border)", position: "relative", transition: "background .2s" }}>
                      <span style={{ position: "absolute", top: 2, left: on ? 14 : 2, width: 14, height: 14, borderRadius: "50%", background: "#fff", transition: "left .2s", boxShadow: "0 1px 2px rgba(0,0,0,.4)" }} />
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Status */}
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)", margin: "0 4px 8px" }}>Status</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 18 }}>
              {(["clean", "pending", "blocked"] as const).map(k => {
                const st = STATUS[k];
                const active = activeStatus === k;
                return (
                  <div key={k} onClick={() => setActiveStatus(s => s === k ? null : k)} style={{
                    display: "flex", alignItems: "center", gap: 9, padding: "7px 8px", borderRadius: 7, cursor: "pointer",
                    background: active ? "var(--surface)" : "transparent",
                    border: `1px solid ${active ? "var(--border)" : "transparent"}`,
                  }}>
                    <span style={{ flexShrink: 0, width: 11, height: 11, borderRadius: "50%", background: st.dot, boxShadow: `0 0 0 3px ${st.glow}` }} />
                    <span style={{ flex: 1, fontSize: 13, color: "var(--text)" }}>{st.label}</span>
                    <span style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12, color: "var(--muted)" }}>{counts[k]}</span>
                  </div>
                );
              })}
            </div>

            {/* Color groups */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", margin: "0 4px 8px" }}>
              <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)" }}>Color groups</span>
              <span style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>by path</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {G.groups.map(g => {
                const active = activeGroup === g.id;
                const cnt = visible.filter(n => !n.isCenter && !n.orphan && n.group === g.id).length;
                return (
                  <div key={g.id} onClick={() => setActiveGroup(a => a === g.id ? null : g.id)} style={{
                    display: "flex", alignItems: "center", gap: 9, padding: "7px 8px", borderRadius: 7, cursor: "pointer",
                    background: active ? "var(--surface)" : "transparent",
                    border: `1px solid ${active ? "var(--border)" : "transparent"}`,
                  }}>
                    <span style={{ flexShrink: 0, width: 11, height: 11, borderRadius: 3, background: g.color }} />
                    <span style={{ flex: 1, fontSize: 13, color: "var(--text)", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>{g.label}</span>
                    <span style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12, color: "var(--muted)" }}>{cnt}</span>
                  </div>
                );
              })}
            </div>
            <button
              onClick={() => showToast("color groups configured in settings", "info")}
              style={{
                width: "100%", marginTop: 12, padding: 8,
                background: "var(--accent-btn)", border: "1px solid color-mix(in srgb, #fff 14%, var(--accent-btn))",
                borderRadius: 8, color: "var(--accent-fg)", fontSize: 13, fontWeight: 600, cursor: "pointer",
              }}
            >New group</button>
          </div>
        </aside>

        {/* CANVAS */}
        <div style={{
          position: "relative", flex: 1, minWidth: 0,
          background: "var(--bg)",
          overflow: "hidden",
        }}>
          {/* Top-left toolbar */}
          <div style={{ position: "absolute", top: 14, left: 16, zIndex: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              background: "var(--inset)", backdropFilter: "blur(6px)",
              border: "1px solid var(--border)", borderRadius: 8, padding: "5px 10px",
            }}>
              <span style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12, color: "var(--muted)" }}>
                {visible.length} nodes · {G.edges.length} links
              </span>
            </div>
            {hasFocus && (
              <button
                onClick={() => { setSelectedId(null); setActiveGroup(null); setActiveStatus(null); setQuery(""); }}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  background: "var(--inset)", backdropFilter: "blur(6px)",
                  border: "1px solid var(--border)", borderRadius: 8, padding: "6px 11px",
                  color: "var(--text)", fontSize: 12, fontWeight: 500, cursor: "pointer",
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M9 3H5a2 2 0 0 0-2 2v4M15 3h4a2 2 0 0 1 2 2v4M21 15v4a2 2 0 0 1-2 2h-4M3 15v4a2 2 0 0 0 2 2h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                Reset view
              </button>
            )}
          </div>

          {/* Top-right chips */}
          <div style={{ position: "absolute", top: 14, right: 16, zIndex: 10, display: "flex", alignItems: "center", gap: 8 }}>
            {counts.blocked > 0 && (
              <button
                onClick={() => { setActiveStatus("blocked"); setActiveGroup(null); setQuery(""); setSelectedId(null); }}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  background: "var(--red-dim)", border: "1px solid color-mix(in srgb, var(--red) 45%, transparent)",
                  borderRadius: 8, padding: "7px 12px", color: "var(--red)", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                  backdropFilter: "blur(6px)",
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" /></svg>
                {counts.blocked} blocked — secret detected
              </button>
            )}
            <Link href="/merge" style={{
              display: "flex", alignItems: "center", gap: 8,
              background: "var(--inset)", backdropFilter: "blur(6px)",
              border: "1px solid color-mix(in srgb, var(--amber) 45%, var(--border))",
              borderRadius: 8, padding: "7px 12px", color: "var(--amber)", fontSize: 12.5, fontWeight: 600, cursor: "pointer", textDecoration: "none",
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="6" cy="6" r="2.4" stroke="currentColor" strokeWidth="2" /><circle cx="6" cy="18" r="2.4" stroke="currentColor" strokeWidth="2" /><circle cx="18" cy="12" r="2.4" stroke="currentColor" strokeWidth="2" /><path d="M6 8.4v7.2M8.2 6h4a3.6 3.6 0 0 1 3.6 3.6V12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
              2 conflicts — resolve
            </Link>
            <Link href="/intent" style={{
              display: "flex", alignItems: "center", gap: 8,
              background: "var(--inset)", backdropFilter: "blur(6px)",
              border: "1px solid var(--border)", borderRadius: 8, padding: "7px 12px",
              color: "var(--text)", fontSize: 12.5, fontWeight: 500, cursor: "pointer", textDecoration: "none",
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M4 7h16M4 12h16M4 17h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
              Intent log
            </Link>
          </div>

          {/* SVG graph */}
          <svg
            viewBox="0 0 1000 760"
            preserveAspectRatio="xMidYMid meet"
            style={{ width: "100%", height: "100%", display: "block" }}
          >
            <g>
              {G.edges.filter(e => {
                const a = G.byId[e.a], b = G.byId[e.b];
                if (!a || !b) return false;
                if ((a.orphan && !toggles.orphans) || (b.orphan && !toggles.orphans)) return false;
                return true;
              }).map((e, i) => {
                const a = G.byId[e.a], b = G.byId[e.b];
                const on = isActive(e.a) && isActive(e.b);
                const strong = !!(selectedId || hoverId) && on;
                return (
                  <line key={i}
                    x1={a.cx} y1={a.cy} x2={b.cx} y2={b.cy}
                    stroke={strong ? "#b3b8bf" : (e.cross ? "#565b63" : "#3a3e44")}
                    strokeWidth={e.spoke ? 2 : (strong ? 1.8 : 1.3)}
                    opacity={activeSet ? (on ? (strong ? 0.9 : 0.55) : 0.06) : (e.spoke ? 0.48 : 0.34)}
                    style={{ transition: "opacity .25s" }}
                  />
                );
              })}
            </g>
            <g>
              {visible.map(n => {
                const st = effStatus(n);
                const sel = n.id === selectedId;
                let fill = n.groupColor;
                let stroke = "var(--bg)", strokeW = 1;
                if (st === "blocked") { fill = "#f26d78"; stroke = "#c2414b"; strokeW = 1.5; }
                else if (st === "pending") { stroke = "#dba53f"; strokeW = 2; }
                if (n.isHub && !n.isCenter) { stroke = st === "pending" ? "#dba53f" : (st === "blocked" ? "#c2414b" : "var(--border)"); }
                if (n.isCenter) { fill = "var(--faint)"; stroke = "var(--border)"; strokeW = 2; }
                if (sel) { stroke = "var(--accent)"; strokeW = 2.6; }
                const showLabel = n.isCenter || (n.isHub && (!activeSet || isActive(n.id))) || sel || n.id === hoverId;
                return (
                  <g key={n.id}
                    onClick={() => { setSelectedId(n.id); setEditing(false); setWarning(null); setDraft(""); }}
                    onMouseEnter={ev => { setHoverId(n.id); setTipPos({ x: ev.clientX, y: ev.clientY }); }}
                    onMouseLeave={() => { setHoverId(null); setTipPos(null); }}
                    style={{ cursor: "pointer", opacity: isActive(n.id) ? 1 : 0.14, transition: "opacity .25s" }}
                  >
                    {st === "blocked" && (
                      <circle cx={n.cx} cy={n.cy} r={n.r + 5} fill="none" stroke="#f26d78" strokeWidth="1.5"
                        style={{ transformOrigin: `${n.cx}px ${n.cy}px`, animation: "vm-ring 2.2s ease-out infinite" }} />
                    )}
                    <circle cx={n.cx} cy={n.cy} r={n.r} fill={fill} stroke={stroke} strokeWidth={strokeW} />
                    {showLabel && (
                      <text x={n.cx} y={n.cy - n.r - 7} textAnchor="middle"
                        fontSize={n.isCenter ? 14 : 11} fill="var(--text)"
                        stroke="var(--bg)" strokeWidth="3" paintOrder="stroke"
                        style={{ fontFamily: "-apple-system, sans-serif", fontWeight: 500, pointerEvents: "none", letterSpacing: ".2px" }}>
                        {n.label}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          </svg>

          {/* Hover tooltip */}
          {hoverId && tipPos && (() => {
            const n = G.byId[hoverId];
            const st = effStatus(n);
            const stDef = STATUS[st];
            const grp = G.groups.find(x => x.id === n.group);
            const path = n.isCenter ? "session intent" : (n.orphan ? "unlinked note" : (grp?.label ?? "") + n.label);
            return (
              <div style={{
                position: "fixed", left: tipPos.x, top: tipPos.y, zIndex: 50,
                pointerEvents: "none", transform: "translate(-50%, calc(-100% - 12px))",
                background: "var(--inset)", border: "1px solid var(--border)",
                borderRadius: 9, padding: "9px 11px", boxShadow: "0 8px 24px rgba(0,0,0,.35)",
                minWidth: 160, maxWidth: 230,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4 }}>
                  <span style={{ width: 9, height: 9, borderRadius: "50%", background: stDef.dot, boxShadow: `0 0 0 3px ${stDef.glow}` }} />
                  <span style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12.5, color: "#e9eaec", fontWeight: 500 }}>{n.label}</span>
                </div>
                <div style={{ fontSize: 11.5, color: "#8a9099" }}>{path}</div>
                <div style={{ marginTop: 5, fontSize: 11.5, color: stDef.color }}>{stDef.label} — {stDef.why}</div>
              </div>
            );
          })()}

          {/* Node side panel */}
          {selected && (() => {
            const st = effStatus(selected);
            const stDef = STATUS[st];
            const grp = G.groups.find(x => x.id === selected.group);
            const path = selected.isCenter
              ? ".vaultmind/intents/trust-graph-v1.md"
              : (selected.orphan ? "(unlinked) " + selected.label : (grp?.label ?? "") + selected.label);
            const nodeContent = contentFor(selected, overrides);
            const neigh = [...(G.neighbors[selected.id] || new Set())]
              .filter(id => id !== "center").slice(0, 4)
              .map(id => G.byId[id]).filter(Boolean);
            const fm = [
              { k: "type",       v: selected.type,       color: "var(--text)" },
              { k: "status",     v: st,                  color: stDef.color },
              { k: "created",    v: selected.created,    color: "var(--muted)" },
              { k: "intent_ref", v: selected.intentRef,  color: "var(--accent)" },
            ];
            const canCommit = !!commitMsg.trim();

            return (
              <div style={{
                position: "absolute", top: 0, right: 0, bottom: 0, width: 392, maxWidth: "88vw",
                background: "var(--surface)", borderLeft: "1px solid var(--border)",
                boxShadow: "-12px 0 32px rgba(0,0,0,.18)",
                display: "flex", flexDirection: "column", zIndex: 20,
                animation: "vm-slidein .28s cubic-bezier(.4,0,.2,1) both",
              }}>
                {/* Panel header */}
                <div style={{ flexShrink: 0, padding: "16px 16px 14px", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: stDef.dot, boxShadow: `0 0 0 3px ${stDef.glow}` }} />
                        <span style={{ fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: stDef.color }}>{stDef.label}</span>
                      </div>
                      <h2 style={{ margin: 0, fontSize: 17, fontWeight: 600, letterSpacing: "-.2px", fontFamily: "var(--font-jetbrains-mono, monospace)", wordBreak: "break-all" }}>{selected.label}</h2>
                      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>{path}</div>
                    </div>
                    <button onClick={() => { setSelectedId(null); setEditing(false); setWarning(null); }} style={{
                      flexShrink: 0, width: 30, height: 30, display: "flex", alignItems: "center", justifyContent: "center",
                      background: "transparent", border: "1px solid var(--border)", borderRadius: 7, color: "var(--muted)", cursor: "pointer",
                    }}>✕</button>
                  </div>
                </div>

                <div style={{ flex: 1, overflowY: "auto" }}>
                  {/* Blocked banner */}
                  {st === "blocked" && !editing && (
                    <div style={{ margin: "14px 16px 0", background: "var(--red-dim)", border: "1px solid color-mix(in srgb, var(--red) 45%, transparent)", borderRadius: 9, padding: "11px 12px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--red)", fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><rect x="4" y="10" width="16" height="11" rx="2" stroke="currentColor" strokeWidth="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="2" /></svg>
                        Secret detected — save blocked
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--text)" }}>
                        {selected.label === "stripe-webhook.ts"
                          ? "A Stripe live key (sk_live_…) is hardcoded on line 2."
                          : "An AWS secret access key is hardcoded in this file."
                        } Remove it and re-scan before this node can commit.
                      </div>
                    </div>
                  )}

                  {/* Edit mode */}
                  {editing && (
                    <div style={{ padding: "14px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)" }}>Staging editor</span>
                        <span style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>writes to disk on save</span>
                      </div>
                      <div style={{ marginBottom: 10 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)", marginBottom: 6 }}>
                          Commit message <span style={{ color: "var(--red)", fontSize: 10, fontWeight: 500, letterSpacing: 0, textTransform: "none" }}>· required</span>
                        </div>
                        <input
                          value={commitMsg}
                          onChange={e => setCommitMsg(e.target.value)}
                          placeholder="Describe what changed…"
                          style={{ width: "100%", boxSizing: "border-box", background: "var(--inset)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px", color: "var(--text)", fontFamily: "inherit", fontSize: 13, outline: "none" }}
                        />
                      </div>
                      <textarea
                        value={draft}
                        onChange={e => { setDraft(e.target.value); setWarning(null); }}
                        spellCheck={false}
                        style={{
                          width: "100%", boxSizing: "border-box", minHeight: 200, resize: "vertical",
                          background: "var(--inset)", border: `1px solid ${warning ? "var(--red)" : "var(--border)"}`,
                          borderRadius: 9, padding: 12, color: "var(--text)",
                          fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12.5, lineHeight: 1.7, outline: "none",
                        }}
                      />
                      {warning && (
                        <div style={{ marginTop: 10, background: "var(--red-dim)", border: "1px solid color-mix(in srgb, var(--red) 45%, transparent)", borderRadius: 8, padding: "10px 11px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--red)", fontWeight: 600, fontSize: 12.5, marginBottom: 4 }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" /></svg>
                            scanForSecrets blocked the save
                          </div>
                          <div style={{ fontSize: 12, color: "var(--text)", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>{warning}</div>
                        </div>
                      )}
                      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                        <button onClick={saveNode} style={{
                          flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 7, padding: 9,
                          background: canCommit ? "var(--accent-btn)" : "var(--surface)",
                          border: `1px solid ${canCommit ? "color-mix(in srgb, #fff 14%, var(--accent-btn))" : "var(--border)"}`,
                          borderRadius: 8, color: canCommit ? "var(--accent-fg)" : "var(--faint)",
                          fontSize: 13, fontWeight: 600, cursor: canCommit ? "pointer" : "not-allowed",
                          opacity: canCommit ? 1 : 0.55, transition: "all .15s",
                        }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /><path d="M17 21v-8H7v8M7 3v5h8" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /></svg>
                          Scan &amp; save
                        </button>
                        <button onClick={() => { setEditing(false); setWarning(null); setCommitMsg(""); }} style={{
                          flexShrink: 0, padding: "9px 14px", background: "transparent",
                          border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", fontSize: 13, fontWeight: 500, cursor: "pointer",
                        }}>Cancel</button>
                      </div>
                    </div>
                  )}

                  {/* View mode */}
                  {!editing && (
                    <>
                      <div style={{ padding: "14px 16px 6px" }}>
                        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)", marginBottom: 8 }}>Content</div>
                        <pre style={{
                          margin: 0, background: "var(--inset)", border: "1px solid var(--border)", borderRadius: 9,
                          padding: 12, overflowX: "auto", fontFamily: "var(--font-jetbrains-mono, monospace)",
                          fontSize: 12.5, lineHeight: 1.7, color: "var(--text)", whiteSpace: "pre-wrap", wordBreak: "break-word",
                        }}>{nodeContent}</pre>
                      </div>

                      <div style={{ padding: "8px 16px 6px" }}>
                        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)", marginBottom: 8 }}>Frontmatter</div>
                        <div style={{ background: "var(--inset)", border: "1px solid var(--border)", borderRadius: 9, overflow: "hidden" }}>
                          {fm.map(f => (
                            <div key={f.k} style={{ display: "flex", gap: 12, padding: "8px 12px", borderBottom: "1px solid var(--border-muted)" }}>
                              <span style={{ flexShrink: 0, width: 96, fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12, color: "var(--muted)" }}>{f.k}</span>
                              <span style={{ flex: 1, fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12, color: f.color, wordBreak: "break-word" }}>{f.v}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div style={{ padding: "8px 16px 6px" }}>
                        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)", marginBottom: 8 }}>Related topics</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                          {(neigh.length ? neigh : [G.byId["center"]]).filter(Boolean).map(m => (
                            <span key={m.id} onClick={() => { setSelectedId(m.id); setEditing(false); }} style={{
                              display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 10px",
                              background: "var(--inset)", border: "1px solid var(--border)", borderRadius: 9999,
                              fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12, color: "var(--accent)", cursor: "pointer",
                            }}>
                              <span style={{ width: 7, height: 7, borderRadius: "50%", background: m.groupColor }} />
                              {m.label}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div style={{ padding: "14px 16px 18px" }}>
                        <button onClick={() => { setEditing(true); setDraft(nodeContent); setWarning(null); setCommitMsg(""); }} style={{
                          width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 7, padding: 9,
                          background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8,
                          color: "var(--text)", fontSize: 13, fontWeight: 600, cursor: "pointer",
                        }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" /></svg>
                          Edit node
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            );
          })()}

          {/* Toast */}
          {toast && (
            <div style={{
              position: "absolute", bottom: 22, left: "50%", transform: "translateX(-50%)",
              zIndex: 60, display: "flex", alignItems: "center", gap: 9,
              background: "var(--inset)",
              border: `1px solid color-mix(in srgb, ${toastColor} 45%, var(--border))`,
              borderRadius: 10, padding: "10px 14px", boxShadow: "0 10px 30px rgba(0,0,0,.35)",
              animation: "vm-toast .25s both",
            }}>
              <span style={{ display: "inline-flex", color: toastColor }}>
                {toast.kind === "bad"
                  ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" /></svg>
                  : toast.kind === "info"
                  ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" /><path d="M12 11v5M12 8h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                  : <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 6" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
                }
              </span>
              <span style={{ fontSize: 13, color: "#e9eaec", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>{toast.msg}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}