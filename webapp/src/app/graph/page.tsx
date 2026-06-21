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
// Graph data types
// ---------------------------------------------------------------------------

interface GNode {
  id: string; label: string; group: string; groupColor: string;
  status: "clean" | "pending" | "blocked";
  cx: number; cy: number; r: number;
  isCenter?: boolean; isHub?: boolean; orphan?: boolean;
  // AC-1 node schema fields
  nodeId: string;
  nodeType: "decision" | "constraint" | "goal" | "question" | "scope";
  title: string;
  created: string;
  sourceTool: "claude-code" | "codex";
  sourceSession: string;
  intentRef: string;
  reviewStatus: "approved" | "pending";
  related: string[];
  flags: string[];
  deg: number;
  content?: string;
}

interface GEdge { a: string; b: string; spoke?: boolean; cross?: boolean; faint?: boolean; }

interface GGroup { id: string; label: string; color: string; desc: string; }

// ---------------------------------------------------------------------------
// Node metadata (AC-1 schema for every demo node)
// ---------------------------------------------------------------------------

type NodeMeta = {
  nodeType: "decision" | "constraint" | "goal" | "question" | "scope";
  title: string;
  nodeId: string;
  sourceTool: "claude-code" | "codex";
  sourceSession: string;
  intentRef: string;
  reviewStatus: "approved" | "pending";
  related: string[];
  flags: string[];
};

const NODE_META: Record<string, NodeMeta> = {
  // PIPELINE
  "pipeline:turn-ingestion": {
    nodeType: "decision", title: "Use Redis Streams (vaultmind:turns) for the turn queue",
    nodeId: "2026-06-18-1015-turn-ingestion",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[redis-streams]]", "[[queue-item]]", "[[Constraints]]"], flags: [],
  },
  "pipeline:claude-hook": {
    nodeType: "decision", title: "PostToolUse hook writes QueueItem to vaultmind:turns",
    nodeId: "2026-06-18-1020-claude-hook",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[turn-ingestion]]", "[[queue-item]]", "[[queue-producer]]"], flags: [],
  },
  "pipeline:codex-hook": {
    nodeType: "decision", title: "Codex post-exec hook mirrors QueueItem contract; transcript_path may be null",
    nodeId: "2026-06-18-1025-codex-hook",
    sourceTool: "codex", sourceSession: "14b72cd1-8ae3",
    intentRef: "2026-06-18 14:30", reviewStatus: "approved",
    related: ["[[turn-ingestion]]", "[[queue-item]]", "[[transcript-reader]]"], flags: [],
  },
  "pipeline:session-start": {
    nodeType: "decision", title: "SessionStart hook seeds SessionState.md and the current intent slot",
    nodeId: "2026-06-18-1030-session-start",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[session-state]]", "[[intent-log]]", "[[sessionstate-writer]]"], flags: [],
  },
  "pipeline:session-end": {
    nodeType: "decision", title: "SessionEnd hook triggers vault commit + Orchestrator handoff",
    nodeId: "2026-06-18-1035-session-end",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[session-state]]", "[[orchestrator]]", "[[handoff-gate]]"], flags: [],
  },
  "pipeline:transcript-reader": {
    nodeType: "decision", title: "P1 reads transcript_path from QueueItem; null-safe for Codex turns",
    nodeId: "2026-06-18-1040-transcript-reader",
    sourceTool: "codex", sourceSession: "14b72cd1-8ae3",
    intentRef: "2026-06-18 14:30", reviewStatus: "approved",
    related: ["[[turn-ingestion]]", "[[queue-item]]", "[[codex-hook]]"], flags: [],
  },
  "pipeline:queue-producer": {
    nodeType: "decision", title: "XADD to vaultmind:turns; consumer group created once by watcher at startup",
    nodeId: "2026-06-18-1045-queue-producer",
    sourceTool: "codex", sourceSession: "14b72cd1-8ae3",
    intentRef: "2026-06-18 14:30", reviewStatus: "approved",
    related: ["[[redis-streams]]", "[[consumer-group]]", "[[turn-ingestion]]"], flags: [],
  },
  "pipeline:sessionstate-writer": {
    nodeType: "constraint", title: "SessionState.md appends use atomic write-temp-rename + .lock sentinel",
    nodeId: "2026-06-18-1050-sessionstate-writer",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[session-state]]", "[[intent-log]]", "[[Constraints]]"], flags: [],
  },
  "pipeline:compaction-detect": {
    nodeType: "decision", title: "compact_boundary subtype in transcript sets [post-compaction] flag on subsequent nodes",
    nodeId: "2026-06-18-1055-compaction-detect",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[session-state]]", "[[node-store]]", "[[sessionstate-writer]]"], flags: [],
  },
  "pipeline:intent-shift": {
    nodeType: "question", title: "When exactly does a topic change warrant a new IntentLog entry vs amending the current one?",
    nodeId: "2026-06-20-1145-intent-shift",
    sourceTool: "claude-code", sourceSession: "3e8b5522-aa17",
    intentRef: "2026-06-20 11:45", reviewStatus: "pending",
    related: ["[[intent-log]]", "[[scribe]]"], flags: [],
  },
  // AGENTS
  "agents:orchestrator": {
    nodeType: "goal", title: "Orchestrator uAgent is point-of-record + in-flight tracker for every turn",
    nodeId: "2026-06-18-0900-orchestrator",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[fetch-ai-uagent]]", "[[turn-progress]]", "[[link-result]]", "[[arize-telemetry]]"], flags: [],
  },
  "agents:scribe": {
    nodeType: "goal", title: "Scribe extracts decisions, constraints, goals from each turn via Claude API",
    nodeId: "2026-06-18-0910-scribe",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[note-creator]]", "[[scribe-result]]", "[[queue-item]]"], flags: [],
  },
  "agents:note-creator": {
    nodeType: "goal", title: "Note Creator wraps Scribe output verbatim; body is byte-for-byte immutable after write",
    nodeId: "2026-06-19-0900-note-creator",
    sourceTool: "claude-code", sourceSession: "2f4a9011-cc41",
    intentRef: "2026-06-19 09:00", reviewStatus: "pending",
    related: ["[[scribe]]", "[[node-store]]", "[[write-time-scan]]", "[[Constraints]]"], flags: [],
  },
  "agents:connector": {
    nodeType: "constraint", title: "Connector writes ONLY frontmatter related field; never touches node body",
    nodeId: "2026-06-18-0920-connector",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[node-store]]", "[[link-result]]", "[[node-written]]", "[[Constraints]]"], flags: [],
  },
  "agents:fetch-ai-uagent": {
    nodeType: "goal", title: "Orchestrator published as uAgent on Agentverse; ASI:One exposes three intents",
    nodeId: "2026-06-19-0915-fetch-ai-uagent",
    sourceTool: "claude-code", sourceSession: "2f4a9011-cc41",
    intentRef: "2026-06-19 09:00", reviewStatus: "pending",
    related: ["[[orchestrator]]", "[[asi-one-intents]]", "[[agentverse]]"], flags: [],
  },
  "agents:arize-telemetry": {
    nodeType: "constraint", title: "All agents emit OpenTelemetry traces to Arize Phoenix for observability",
    nodeId: "2026-06-18-0930-arize-telemetry",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[orchestrator]]", "[[Constraints]]"], flags: ["secret-detected"],
  },
  "agents:agentverse": {
    nodeType: "decision", title: "Agentverse registration and Profile URL are human-owned carve-outs; Devin never touches them",
    nodeId: "2026-06-20-1150-agentverse",
    sourceTool: "claude-code", sourceSession: "3e8b5522-aa17",
    intentRef: "2026-06-20 11:45", reviewStatus: "approved",
    related: ["[[fetch-ai-uagent]]", "[[orchestrator]]"], flags: [],
  },
  "agents:asi-one-intents": {
    nodeType: "scope", title: "Three ASI:One intents: capture (turn arrives), summarise (session end), handoff (SessionEnd)",
    nodeId: "2026-06-20-1155-asi-one-intents",
    sourceTool: "claude-code", sourceSession: "3e8b5522-aa17",
    intentRef: "2026-06-20 11:45", reviewStatus: "pending",
    related: ["[[orchestrator]]", "[[fetch-ai-uagent]]", "[[session-end]]"], flags: [],
  },
  // STORAGE
  "storage:redis-streams": {
    nodeType: "constraint", title: "Redis is the only cross-language seam; disk is source of truth, Redis delivers events",
    nodeId: "2026-06-18-0830-redis-streams",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[turn-ingestion]]", "[[redis-pubsub]]", "[[node-store]]", "[[Constraints]]"], flags: [],
  },
  "storage:vault-layout": {
    nodeType: "scope", title: "Vault: nodes/, ProjectGoal.md, Constraints.md, TechStack.md, IntentLog.md, VaultIndex.md, SessionState.md",
    nodeId: "2026-06-18-0835-vault-layout",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[node-store]]", "[[intent-log]]", "[[session-state]]", "[[vault-index]]"], flags: [],
  },
  "storage:node-store": {
    nodeType: "constraint", title: "Disk is source of truth; Redis events are minimal 're-read this id' triggers, never payloads",
    nodeId: "2026-06-18-0840-node-store",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[vault-layout]]", "[[redis-pubsub]]", "[[Constraints]]"], flags: [],
  },
  "storage:intent-log": {
    nodeType: "scope", title: "IntentLog.md is append-only, newest-on-top; exactly one entry marked Current",
    nodeId: "2026-06-18-0845-intent-log",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[vault-layout]]", "[[sessionstate-writer]]", "[[Constraints]]"], flags: [],
  },
  "storage:session-state": {
    nodeType: "scope", title: "SessionState.md records session-event rows and compaction flags deterministically",
    nodeId: "2026-06-18-0850-session-state",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[vault-layout]]", "[[compaction-detect]]", "[[sessionstate-writer]]"], flags: ["secret-detected"],
  },
  "storage:vault-index": {
    nodeType: "scope", title: "VaultIndex.md is the static entry point for LLM context loading order",
    nodeId: "2026-06-18-0855-vault-index",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[vault-layout]]", "[[node-store]]"], flags: [],
  },
  "storage:redis-pubsub": {
    nodeType: "constraint", title: "vaultmind:events pub/sub channel delivers NodeChangedEvent to the web app via SSE",
    nodeId: "2026-06-18-0900-redis-pubsub",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[redis-streams]]", "[[node-changed-event]]", "[[sse-endpoint]]"], flags: [],
  },
  "storage:vector-memory": {
    nodeType: "decision", title: "Redis vector memory stores embeddings for semantic node search across the vault",
    nodeId: "2026-06-19-0905-vector-memory",
    sourceTool: "claude-code", sourceSession: "2f4a9011-cc41",
    intentRef: "2026-06-19 09:00", reviewStatus: "pending",
    related: ["[[redis-streams]]", "[[connector]]"], flags: [],
  },
  "storage:consumer-group": {
    nodeType: "constraint", title: "Consumer group vaultmind-workers created once by the watcher at startup; P1 producer must never create it",
    nodeId: "2026-06-18-0905-consumer-group",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[redis-streams]]", "[[queue-producer]]"], flags: [],
  },
  "storage:constraints": {
    nodeType: "scope", title: "Standing constraints anchor: no second scanForSecrets, no silent commit, disk is truth",
    nodeId: "2026-06-18-0910-constraints",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[scan-secrets]]", "[[handoff-gate]]", "[[node-store]]"], flags: [],
  },
  // CONTRACTS
  "contracts:types-ts": {
    nodeType: "scope", title: "types.ts is frozen; every field must match contracts.py exactly at each Devin Review boundary",
    nodeId: "2026-06-18-0845-types-ts",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[contracts-py]]", "[[queue-item]]", "[[TechStack]]"], flags: [],
  },
  "contracts:contracts-py": {
    nodeType: "scope", title: "contracts.py is frozen; Devin sessions must never edit it",
    nodeId: "2026-06-18-0846-contracts-py",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[types-ts]]", "[[queue-item]]"], flags: [],
  },
  "contracts:queue-item": {
    nodeType: "scope", title: "QueueItem: turn_id, source_tool, session_id, transcript_path, turn_text, enqueued_at",
    nodeId: "2026-06-18-0847-queue-item",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[types-ts]]", "[[turn-ingestion]]", "[[queue-producer]]", "[[transcript-reader]]"], flags: [],
  },
  "contracts:scribe-result": {
    nodeType: "scope", title: "ScribeResult: turn_id, extractions[{type, title, slug, body}], intent_shift",
    nodeId: "2026-06-18-0848-scribe-result",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[types-ts]]", "[[scribe]]", "[[note-creator]]"], flags: [],
  },
  "contracts:node-written": {
    nodeType: "scope", title: "NodeWritten: id, path, type, title, status, flags, intent_ref — Connector reads this",
    nodeId: "2026-06-18-0849-node-written",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[types-ts]]", "[[note-creator]]", "[[connector]]"], flags: [],
  },
  "contracts:link-result": {
    nodeType: "scope", title: "LinkResult: id, related[], status, linked_at — Connector → Orchestrator",
    nodeId: "2026-06-18-0850-link-result",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[types-ts]]", "[[connector]]", "[[orchestrator]]"], flags: [],
  },
  "contracts:turn-progress": {
    nodeType: "scope", title: "TurnProgress: turn_id, stage, node_ids[] — enables idempotent resume on redelivery",
    nodeId: "2026-06-18-0851-turn-progress",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[types-ts]]", "[[orchestrator]]"], flags: [],
  },
  "contracts:node-changed-event": {
    nodeType: "scope", title: "NodeChangedEvent enum: created|linked|updated|deleted|secret-detected|intent-updated|session-event",
    nodeId: "2026-06-18-0852-node-changed-event",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[types-ts]]", "[[redis-pubsub]]", "[[sse-endpoint]]"], flags: [],
  },
  // WEBAPP
  "webapp:graph-canvas": {
    nodeType: "decision", title: "Force-layout trust graph as the primary vault view; five display states from AC-7",
    nodeId: "2026-06-19-1100-graph-canvas",
    sourceTool: "claude-code", sourceSession: "2f4a9011-cc41",
    intentRef: "2026-06-19 09:00", reviewStatus: "approved",
    related: ["[[node-panel]]", "[[sse-endpoint]]", "[[node-changed-event]]"], flags: [],
  },
  "webapp:merge-page": {
    nodeType: "decision", title: "GitHub-dark conflict resolution UI with per-hunk accept/reject and secret-scan gate",
    nodeId: "2026-06-20-1145-merge-page",
    sourceTool: "claude-code", sourceSession: "3e8b5522-aa17",
    intentRef: "2026-06-20 11:45", reviewStatus: "pending",
    related: ["[[conflict-resolver]]", "[[scan-secrets]]", "[[graph-canvas]]"], flags: [],
  },
  "webapp:intent-page": {
    nodeType: "decision", title: "Intent log view: append-only timeline, newest-on-top, mirrors IntentLog.md",
    nodeId: "2026-06-20-1150-intent-page",
    sourceTool: "claude-code", sourceSession: "3e8b5522-aa17",
    intentRef: "2026-06-20 11:45", reviewStatus: "pending",
    related: ["[[intent-log]]", "[[graph-canvas]]"], flags: [],
  },
  "webapp:sse-endpoint": {
    nodeType: "decision", title: "/api/events SSE route subscribes to vaultmind:events Redis pub/sub",
    nodeId: "2026-06-19-1105-sse-endpoint",
    sourceTool: "claude-code", sourceSession: "2f4a9011-cc41",
    intentRef: "2026-06-19 09:00", reviewStatus: "pending",
    related: ["[[redis-pubsub]]", "[[node-changed-event]]", "[[graph-canvas]]"], flags: [],
  },
  "webapp:node-panel": {
    nodeType: "decision", title: "Right-hand panel renders AC-1 frontmatter + staging editor with scanForSecrets on save",
    nodeId: "2026-06-19-1110-node-panel",
    sourceTool: "claude-code", sourceSession: "2f4a9011-cc41",
    intentRef: "2026-06-19 09:00", reviewStatus: "pending",
    related: ["[[graph-canvas]]", "[[scan-secrets]]", "[[types-ts]]"], flags: [],
  },
  "webapp:conflict-resolver": {
    nodeType: "decision", title: "Merge page resolves git conflict markers via server-side parser in conflicts.ts",
    nodeId: "2026-06-20-1155-conflict-resolver",
    sourceTool: "claude-code", sourceSession: "3e8b5522-aa17",
    intentRef: "2026-06-20 11:45", reviewStatus: "approved",
    related: ["[[merge-page]]", "[[scan-secrets]]"], flags: [],
  },
  "webapp:setup-page": {
    nodeType: "decision", title: "Setup page guides PostToolUse hook installation for claude-code and codex",
    nodeId: "2026-06-19-1115-setup-page",
    sourceTool: "claude-code", sourceSession: "2f4a9011-cc41",
    intentRef: "2026-06-19 09:00", reviewStatus: "approved",
    related: ["[[claude-hook]]", "[[codex-hook]]"], flags: [],
  },
  "webapp:agent-chat": {
    nodeType: "decision", title: "AgentChat widget sends prompts to /api/agent which forwards to the Orchestrator uAgent",
    nodeId: "2026-06-21-1432-agent-chat",
    sourceTool: "claude-code", sourceSession: "4c7d2831-bb92",
    intentRef: "2026-06-21 14:32", reviewStatus: "approved",
    related: ["[[orchestrator]]", "[[fetch-ai-uagent]]", "[[graph-canvas]]"], flags: [],
  },
  // SECURITY
  "security:scan-secrets": {
    nodeType: "constraint", title: "One scanForSecrets implementation in Python; never add a second",
    nodeId: "2026-06-18-0900-scan-secrets",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[pre-commit-hook]]", "[[handoff-gate]]", "[[write-time-scan]]", "[[Constraints]]"], flags: [],
  },
  "security:pre-commit-hook": {
    nodeType: "constraint", title: "Pre-commit hook runs scanForSecrets; detected secret blocks the commit",
    nodeId: "2026-06-18-0905-pre-commit-hook",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[scan-secrets]]", "[[handoff-gate]]"], flags: [],
  },
  "security:handoff-gate": {
    nodeType: "constraint", title: "Detected secret blocks handoff in both Auto and Review modes; no silent bypass",
    nodeId: "2026-06-18-0910-handoff-gate",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[scan-secrets]]", "[[pre-commit-hook]]", "[[Constraints]]"], flags: [],
  },
  "security:secret-patterns": {
    nodeType: "constraint", title: "Patterns: AWS keys, Stripe live keys, PEM private key blocks, hardcoded credentials",
    nodeId: "2026-06-18-0915-secret-patterns",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[scan-secrets]]"], flags: [],
  },
  "security:write-time-scan": {
    nodeType: "constraint", title: "Note Creator runs scanForSecrets on the node body before any disk write",
    nodeId: "2026-06-18-0920-write-time-scan",
    sourceTool: "claude-code", sourceSession: "00893aaf-19fa",
    intentRef: "2026-06-18 10:15", reviewStatus: "approved",
    related: ["[[scan-secrets]]", "[[note-creator]]", "[[pre-commit-hook]]"], flags: [],
  },
  "security:blocked-display": {
    nodeType: "decision", title: "Blocked nodes render red ring + scanForSecrets banner; status set to secret-detected",
    nodeId: "2026-06-19-1120-blocked-display",
    sourceTool: "claude-code", sourceSession: "2f4a9011-cc41",
    intentRef: "2026-06-19 09:00", reviewStatus: "approved",
    related: ["[[scan-secrets]]", "[[graph-canvas]]", "[[node-panel]]"], flags: [],
  },
};

// ---------------------------------------------------------------------------
// Graph builder
// ---------------------------------------------------------------------------

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
  const rand = rng(20260621);
  const groups: GGroup[] = [
    { id: "pipeline",  label: "pipeline/",  color: "#4c8dff", desc: "Turn ingestion, queue production, session-event detection." },
    { id: "agents",    label: "agents/",    color: "#e3934d", desc: "Scribe, Note Creator, Connector, Orchestrator uAgent." },
    { id: "storage",   label: "storage/",   color: "#57ab5a", desc: "Redis streams, pub/sub, vector memory, vault layout." },
    { id: "contracts", label: "contracts/", color: "#db61a2", desc: "Frozen type schemas, agent message shapes, field parity." },
    { id: "webapp",    label: "webapp/",    color: "#8b949e", desc: "Graph canvas, merge UI, SSE events, five display states." },
    { id: "security",  label: "security/",  color: "#a371f7", desc: "scanForSecrets, pre-commit hook, handoff gate." },
  ];
  const pools: Record<string, string[]> = {
    pipeline:  ["turn-ingestion","claude-hook","codex-hook","session-start","session-end","transcript-reader","queue-producer","sessionstate-writer","compaction-detect","intent-shift"],
    agents:    ["orchestrator","scribe","note-creator","connector","fetch-ai-uagent","arize-telemetry","agentverse","asi-one-intents"],
    storage:   ["redis-streams","vault-layout","node-store","intent-log","session-state","vault-index","redis-pubsub","vector-memory","consumer-group","constraints"],
    contracts: ["types-ts","contracts-py","queue-item","scribe-result","node-written","link-result","turn-progress","node-changed-event"],
    webapp:    ["graph-canvas","merge-page","intent-page","sse-endpoint","node-panel","conflict-resolver","setup-page","agent-chat"],
    security:  ["scan-secrets","pre-commit-hook","handoff-gate","secret-patterns","write-time-scan","blocked-display"],
  };

  // blocked = scanForSecrets flagged a secret; pending = not yet approved / in progress
  const blocked: Record<string, boolean> = { "arize-telemetry": true, "session-state": true };
  const pending: Record<string, boolean> = {
    "note-creator": true, "fetch-ai-uagent": true, "asi-one-intents": true,
    "vector-memory": true, "intent-shift": true,
    "merge-page": true, "intent-page": true, "sse-endpoint": true, "node-panel": true,
  };

  const cx0 = 500, cy0 = 380, RX = 300, RY = 235;
  const nodes: GNode[] = [];
  const edges: GEdge[] = [];
  const byId: Record<string, GNode> = {};

  const add = (n: GNode) => { nodes.push(n); byId[n.id] = n; return n; };

  add({
    id: "center", label: "ship-trust-graph", group: "intent", groupColor: "#9aa4b2",
    status: "pending", cx: cx0, cy: cy0, r: 24, isCenter: true, isHub: true,
    nodeId: "2026-06-21-1430-ship-trust-graph",
    nodeType: "goal",
    title: "Ship VaultMind trust graph demo",
    created: "2026-06-21T14:30:00-07:00",
    sourceTool: "claude-code", sourceSession: "4c7d2831-bb92",
    intentRef: "2026-06-21 14:30", reviewStatus: "pending",
    related: ["[[contracts-py]]", "[[types-ts]]", "[[TechStack]]"],
    flags: [], orphan: false, deg: 0,
  });

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
      const key = `${grp.id}:${name}`;
      const meta = NODE_META[key];
      const node = add({
        id: key, label: name, group: grp.id, groupColor: grp.color,
        status: status as "clean" | "pending" | "blocked",
        cx: x, cy: y, r: 0, isHub,
        nodeId: meta?.nodeId ?? `2026-06-18-0000-${name}`,
        nodeType: meta?.nodeType ?? "decision",
        title: meta?.title ?? name,
        created: "2026-06-18T10:00:00-07:00",
        sourceTool: meta?.sourceTool ?? "claude-code",
        sourceSession: meta?.sourceSession ?? "00893aaf-19fa",
        intentRef: meta?.intentRef ?? "2026-06-18 10:15",
        reviewStatus: meta?.reviewStatus ?? "approved",
        related: meta?.related ?? [],
        flags: blocked[name] ? ["secret-detected"] : (meta?.flags ?? []),
        orphan: false, deg: 0,
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

  const orphanData = [
    { name: "scratch-redis-bench.md",     nodeId: "2026-06-18-1300-scratch-redis-bench",     title: "Scratch: Redis Streams vs Celery latency numbers" },
    { name: "wip-arize-setup.md",         nodeId: "2026-06-19-0800-wip-arize-setup",         title: "WIP: Arize Phoenix SDK setup notes" },
    { name: "draft-handoff-prompt.md",    nodeId: "2026-06-20-1000-draft-handoff-prompt",    title: "Draft: handoff prompt wording for ASI:One" },
    { name: "tmp-scribe-prompt-v2.md",    nodeId: "2026-06-20-1500-tmp-scribe-prompt-v2",    title: "Temp: Scribe extraction prompt iteration v2" },
    { name: "untitled.md",                nodeId: "2026-06-21-0900-untitled",                title: "Untitled note" },
    { name: "clipboard.md",               nodeId: "2026-06-21-1100-clipboard",               title: "Clipboard scratch" },
  ];
  const orphanCreated = [
    "2026-06-18T13:00:00-07:00", "2026-06-19T08:00:00-07:00",
    "2026-06-20T10:00:00-07:00", "2026-06-20T15:00:00-07:00",
    "2026-06-21T09:00:00-07:00", "2026-06-21T11:00:00-07:00",
  ];
  orphanData.forEach((o, i) => {
    const a = rand() * Math.PI * 2, d = 300 + rand() * 70;
    add({
      id: "orphan:" + o.name, label: o.name, group: "docs", groupColor: "#6e7681", status: "clean",
      cx: Math.max(46, Math.min(954, cx0 + Math.cos(a) * d)),
      cy: Math.max(48, Math.min(712, cy0 + Math.sin(a) * d * 0.78)),
      r: 0,
      nodeId: o.nodeId, nodeType: "question", title: o.title,
      created: orphanCreated[i] ?? "2026-06-21T09:00:00-07:00",
      sourceTool: "claude-code", sourceSession: "4c7d2831-bb92",
      intentRef: "2026-06-21 14:32", reviewStatus: "pending",
      related: [], flags: [],
      orphan: true, isHub: false, deg: 0,
    });
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
  clean:   { label: "Clean",   dot: "#3fb950", glow: "rgba(63,185,80,.18)",   color: "#3fb950", why: "Committed — matches git HEAD." },
  pending: { label: "Pending", dot: "#d29922", glow: "rgba(210,153,34,.2)",   color: "#d29922", why: "Modified — not yet committed." },
  blocked: { label: "Blocked", dot: "#f85149", glow: "rgba(248,81,73,.22)",   color: "#f85149", why: "scanForSecrets flagged a secret." },
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

// ---------------------------------------------------------------------------
// Content generator — produces proper AC-1 YAML frontmatter + body
// ---------------------------------------------------------------------------

function contentFor(node: GNode, overrides: Record<string, { status?: string; content?: string }>): string {
  const ov = overrides[node.id];
  if (ov?.content != null) return ov.content;

  const relatedYaml = node.related.length
    ? node.related.map(r => `  - "${r}"`).join("\n")
    : "  []";
  const flagsYaml = node.flags.length ? `[${node.flags.join(", ")}]` : "[]";

  const fm = `---\nid: ${node.nodeId}\ntype: ${node.nodeType}\ntitle: ${node.title}\ncreated: ${node.created}\nsource_tool: ${node.sourceTool}\nsource_session: ${node.sourceSession}\nintent_ref: ${node.intentRef}\nstatus: ${node.reviewStatus}\nrelated:\n${relatedYaml}\nflags: ${flagsYaml}\n---`;

  if (node.label === "arize-telemetry") {
    return `${fm}\n\nAll agents emit OpenTelemetry traces to Arize Phoenix for observability.\n\n\`\`\`python\nimport phoenix as px\n\nARIZE_API_KEY = "ak_live_xK9mPqR3nJvWdL8tYzCbE2sF"\n\npx.launch_app(\n    collector_endpoint="https://arize.internal",\n    api_key=ARIZE_API_KEY,\n)\n\`\`\`\n\n> Remove hardcoded key and load from environment before this node can commit.`;
  }

  if (node.label === "session-state") {
    return `${fm}\n\nSessionState.md records session-event rows and compaction flags deterministically.\n\n\`\`\`python\nREDIS_URL = "redis://:session_secret_abc123@prod-redis.internal:6379"\n\ndef write_state(entry: str):\n    client = redis.from_url(REDIS_URL)\n    # atomic write-temp-rename + .lock sentinel\n\`\`\`\n\n> Hardcoded Redis password detected — load from env before this node can commit.`;
  }

  if (node.isCenter) {
    return `${fm}\n\nThe live trust graph showing every decision, constraint, and goal the agents have captured this session. Nodes commit on Stop; handoff fires on SessionEnd.\n\nLinked from every active node below.`;
  }

  const grp = G.groups.find(x => x.id === node.group);
  return `${fm}\n\n${node.title}.\n\n> Linked from [[ship-trust-graph]].\n\n${grp?.desc ?? ""}`;
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

  const visible = G.nodes.filter(n => n.orphan ? toggles.orphans : true);

  const q = query.trim().toLowerCase();
  let activeSet: Set<string> | null = null;
  if (selectedId) {
    activeSet = new Set([selectedId]);
    (G.neighbors[selectedId] || new Set()).forEach(x => activeSet!.add(x));
  } else if (q) {
    activeSet = new Set(visible.filter(n => n.label.toLowerCase().includes(q) || n.title.toLowerCase().includes(q)).map(n => n.id));
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
              <span style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>by module</span>
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
          background: "radial-gradient(120% 120% at 50% 40%, #0b1018 0%, #010409 70%)",
          overflow: "hidden",
        }}>
          {/* Top-left toolbar */}
          <div style={{ position: "absolute", top: 14, left: 16, zIndex: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              background: "rgba(13,17,23,.78)", backdropFilter: "blur(6px)",
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
                  background: "rgba(13,17,23,.78)", backdropFilter: "blur(6px)",
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
              background: "rgba(13,17,23,.78)", backdropFilter: "blur(6px)",
              border: "1px solid color-mix(in srgb, var(--amber) 45%, var(--border))",
              borderRadius: 8, padding: "7px 12px", color: "var(--amber)", fontSize: 12.5, fontWeight: 600, cursor: "pointer", textDecoration: "none",
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="6" cy="6" r="2.4" stroke="currentColor" strokeWidth="2" /><circle cx="6" cy="18" r="2.4" stroke="currentColor" strokeWidth="2" /><circle cx="18" cy="12" r="2.4" stroke="currentColor" strokeWidth="2" /><path d="M6 8.4v7.2M8.2 6h4a3.6 3.6 0 0 1 3.6 3.6V12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
              2 conflicts — resolve
            </Link>
            <Link href="/intent" style={{
              display: "flex", alignItems: "center", gap: 8,
              background: "rgba(13,17,23,.78)", backdropFilter: "blur(6px)",
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
                    stroke={strong ? "#b0bac6" : (e.cross ? "#4e5c72" : "#3d4f63")}
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
                let stroke = "#0b0f16", strokeW = 1;
                if (st === "blocked") { fill = "#f85149"; stroke = "#b5232b"; strokeW = 1.5; }
                else if (st === "pending") { stroke = "#d29922"; strokeW = 2; }
                if (n.isHub && !n.isCenter) { stroke = st === "pending" ? "#d29922" : (st === "blocked" ? "#b5232b" : "rgba(255,255,255,.22)"); }
                if (n.isCenter) { fill = "#6e7681"; stroke = "rgba(255,255,255,.28)"; strokeW = 2; }
                if (sel) { stroke = "#ffffff"; strokeW = 2.6; }
                const showLabel = n.isCenter || (n.isHub && (!activeSet || isActive(n.id))) || sel || n.id === hoverId;
                return (
                  <g key={n.id}
                    onClick={() => { setSelectedId(n.id); setEditing(false); setWarning(null); setDraft(""); }}
                    onMouseEnter={ev => { setHoverId(n.id); setTipPos({ x: ev.clientX, y: ev.clientY }); }}
                    onMouseLeave={() => { setHoverId(null); setTipPos(null); }}
                    style={{ cursor: "pointer", opacity: isActive(n.id) ? 1 : 0.14, transition: "opacity .25s" }}
                  >
                    {st === "blocked" && (
                      <circle cx={n.cx} cy={n.cy} r={n.r + 5} fill="none" stroke="#f85149" strokeWidth="1.5"
                        style={{ transformOrigin: `${n.cx}px ${n.cy}px`, animation: "vm-ring 2.2s ease-out infinite" }} />
                    )}
                    <circle cx={n.cx} cy={n.cy} r={n.r} fill={fill} stroke={stroke} strokeWidth={strokeW} />
                    {showLabel && (
                      <text x={n.cx} y={n.cy - n.r - 7} textAnchor="middle"
                        fontSize={n.isCenter ? 14 : 11} fill="#c9d1d9"
                        stroke="#010409" strokeWidth="3" paintOrder="stroke"
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
                background: "rgba(13,17,23,.96)", border: "1px solid var(--border)",
                borderRadius: 9, padding: "9px 11px", boxShadow: "0 8px 24px rgba(1,4,9,.6)",
                minWidth: 180, maxWidth: 280,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 3 }}>
                  <span style={{ width: 9, height: 9, borderRadius: "50%", background: stDef.dot, boxShadow: `0 0 0 3px ${stDef.glow}` }} />
                  <span style={{ fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12.5, color: "#e6edf3", fontWeight: 500 }}>{n.label}</span>
                </div>
                <div style={{ fontSize: 11.5, color: "#c9d1d9", marginBottom: 3, lineHeight: 1.4 }}>{n.title}</div>
                <div style={{ fontSize: 11, color: "#7d8590" }}>{path}</div>
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
              ? "vault/nodes/ship-trust-graph.md"
              : (selected.orphan ? "(unlinked) " + selected.label : (grp?.label ?? "") + selected.nodeId + ".md");
            const nodeContent = contentFor(selected, overrides);
            const canCommit = !!commitMsg.trim();

            // Build related chips: resolve wikilinks to graph nodes where possible
            const relatedChips = selected.related.map(link => {
              const slug = link.replace(/^\[\[/, "").replace(/\]\]$/, "");
              const match = Object.values(G.byId).find(n => n.label === slug || n.nodeId.endsWith(`-${slug}`));
              return { slug, match };
            });

            const fm = [
              { k: "id",             v: selected.nodeId,        color: "var(--muted)" },
              { k: "type",           v: selected.nodeType,      color: "var(--accent)" },
              { k: "title",          v: selected.title,         color: "var(--text)" },
              { k: "created",        v: selected.created,       color: "var(--muted)" },
              { k: "source_tool",    v: selected.sourceTool,    color: "var(--text)" },
              { k: "source_session", v: selected.sourceSession, color: "var(--muted)" },
              { k: "intent_ref",     v: selected.intentRef,     color: "var(--accent)" },
              { k: "status",         v: selected.reviewStatus,  color: selected.reviewStatus === "approved" ? "var(--green)" : "var(--amber)" },
              { k: "flags",          v: selected.flags.length ? selected.flags.join(", ") : "[]", color: selected.flags.length ? "var(--red)" : "var(--faint)" },
            ];

            return (
              <div style={{
                position: "absolute", top: 0, right: 0, bottom: 0, width: 420, maxWidth: "88vw",
                background: "var(--surface)", borderLeft: "1px solid var(--border)",
                boxShadow: "-12px 0 32px rgba(1,4,9,.35)",
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
                        <span style={{
                          padding: "1px 7px", borderRadius: 4, fontSize: 11, fontWeight: 600,
                          background: "var(--inset)", border: "1px solid var(--border-muted)",
                          color: "var(--accent)", fontFamily: "var(--font-jetbrains-mono, monospace)",
                        }}>{selected.nodeType}</span>
                      </div>
                      <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600, letterSpacing: "-.2px", fontFamily: "var(--font-jetbrains-mono, monospace)", wordBreak: "break-all" }}>{selected.label}</h2>
                      <div style={{ fontSize: 11.5, color: "var(--text)", marginTop: 3, lineHeight: 1.4 }}>{selected.title}</div>
                      <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 2 }}>{path}</div>
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
                        {selected.label === "arize-telemetry"
                          ? "A hardcoded Arize API key (ak_live_…) is present in this node. Remove it and re-scan before this node can commit."
                          : "A hardcoded Redis password is present in this node. Load credentials from environment before this node can commit."
                        }
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
                        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)", marginBottom: 8 }}>Frontmatter (AC-1)</div>
                        <div style={{ background: "var(--inset)", border: "1px solid var(--border)", borderRadius: 9, overflow: "hidden" }}>
                          {fm.map(f => (
                            <div key={f.k} style={{ display: "flex", gap: 12, padding: "7px 12px", borderBottom: "1px solid var(--border-muted)" }}>
                              <span style={{ flexShrink: 0, width: 108, fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 11.5, color: "var(--muted)" }}>{f.k}</span>
                              <span style={{ flex: 1, fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 11.5, color: f.color, wordBreak: "break-word" }}>{f.v}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {selected.related.length > 0 && (
                        <div style={{ padding: "8px 16px 6px" }}>
                          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--faint)", marginBottom: 8 }}>Related nodes</div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                            {relatedChips.map(({ slug, match }) => (
                              <span key={slug}
                                onClick={match ? () => { setSelectedId(match.id); setEditing(false); } : undefined}
                                style={{
                                  display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 10px",
                                  background: "var(--inset)", border: "1px solid var(--border)", borderRadius: 9999,
                                  fontFamily: "var(--font-jetbrains-mono, monospace)", fontSize: 12,
                                  color: match ? "var(--accent)" : "var(--muted)",
                                  cursor: match ? "pointer" : "default",
                                }}>
                                {match && <span style={{ width: 7, height: 7, borderRadius: "50%", background: match.groupColor }} />}
                                {slug}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

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
              background: "rgba(13,17,23,.96)",
              border: `1px solid color-mix(in srgb, ${toastColor} 45%, var(--border))`,
              borderRadius: 10, padding: "10px 14px", boxShadow: "0 10px 30px rgba(1,4,9,.6)",
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
              <span style={{ fontSize: 13, color: "#e6edf3", fontFamily: "var(--font-jetbrains-mono, monospace)" }}>{toast.msg}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
