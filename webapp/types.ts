/**
 * types.ts — Frozen message contracts for VaultMind (TypeScript mirror).
 *
 * This file MUST stay in lock-step with vaultmind/contracts.py.
 * Field names and types are identical; never edit one without editing the other.
 * The Bucket-2 parity check asserts every field in contracts.py appears here
 * with a matching name and compatible type.
 *
 * Shapes:
 *   1. QueueItem        — Redis Stream vaultmind:turns  (P1 writes → P2 reads)
 *   2. ScribeResult     — Scribe → Note Creator         (in-process, P2-internal)
 *   3. NodeWritten      — Note Creator → Connector      (in-process, P2↔P3 seam)
 *   4. LinkResult       — Connector → Orchestrator      (in-process / record)
 *   5. NodeChangedEvent — Redis pub/sub vaultmind:events → web app via SSE
 *   6. TurnProgress     — Redis pub/sub vaultmind:progress → Orchestrator
 */

// ---------------------------------------------------------------------------
// Shared enums
// ---------------------------------------------------------------------------

export type NodeType = "decision" | "constraint" | "goal" | "question" | "scope";

export type NodeStatus = "pending" | "approved";

export type TurnStage =
  | "started"
  | "extracted"
  | "written"
  | "linked"
  | "done"
  | "failed";

export type NodeChangedEventType =
  | "created"
  | "linked"
  | "updated"
  | "deleted"
  | "secret-detected"
  | "intent-updated"
  | "session-event";

export type SourceTool = "claude-code" | "codex";

// ---------------------------------------------------------------------------
// 1. QueueItem — Redis Stream vaultmind:turns
// ---------------------------------------------------------------------------

/** Verbatim user+assistant pair from a single hook invocation. */
export interface TurnText {
  user: string;
  assistant: string;
}

/**
 * Written by P1 (hook → Redis Stream vaultmind:turns).
 * Read by P2 (watcher consumer group vaultmind-workers).
 *
 * Consumer group is created once by the watcher at startup — P1's producer
 * must never create it.
 */
export interface QueueItem {
  /** Unique per turn: <session_id>-<seq> */
  turn_id: string;
  source_tool: SourceTool;
  /** session_id from the hook stdin */
  session_id: string;
  /** Absolute path to transcript file; null is possible on Codex */
  transcript_path: string | null;
  /** Verbatim fresh turn — hook puts this directly in the queue */
  turn_text: TurnText;
  /** ISO 8601 timestamp */
  enqueued_at: string;
}

// ---------------------------------------------------------------------------
// 2. ScribeResult — Scribe → Note Creator (in-process)
// ---------------------------------------------------------------------------

/** One extracted node from a turn. */
export interface Extraction {
  type: NodeType;
  title: string;
  /** URL-safe slug; part of the filename basename */
  slug: string;
  /** Immutable, Scribe-authored markdown body. Never edited downstream. */
  body: string;
}

/**
 * Produced by the Scribe; consumed in-process by the Note Creator.
 * Also the basis for the Orchestrator 'turn-started' notice.
 *
 * extractions is 0..n — empty means nothing noteworthy, no node written.
 * intent_shift is turn-level; when non-null it routes by mode:
 *   Auto → append to IntentLog as ai-detected
 *   Review → surface as a suggestion
 */
export interface ScribeResult {
  turn_id: string;
  source_tool: SourceTool;
  source_session: string;
  extractions: Extraction[];
  /** Detected intent shift text, or null if no shift detected */
  intent_shift: string | null;
}

// ---------------------------------------------------------------------------
// 3. NodeWritten — Note Creator → Connector (in-process, P2↔P3 seam)
// ---------------------------------------------------------------------------

/**
 * Emitted by the Note Creator after writing a node to disk.
 * Consumed in-process by the Connector (P3).
 */
export interface NodeWritten {
  /** Node basename == filename basename == [[wikilink]] target */
  id: string;
  /** Relative path from repo root, e.g. vault/nodes/<id>.md */
  path: string;
  type: NodeType;
  title: string;
  status: NodeStatus;
  flags: string[];
  /** IntentLog entry key current at write-time, e.g. '2026-06-21 14:32' */
  intent_ref: string;
}

// ---------------------------------------------------------------------------
// 4. LinkResult — Connector → Orchestrator (point of record)
// ---------------------------------------------------------------------------

/**
 * Produced by the Connector after writing `related` frontmatter.
 * Consumed by the Orchestrator as the turn's point-of-record.
 */
export interface LinkResult {
  id: string;
  /** Wikilinks written to frontmatter, e.g. ['[[Constraints]]'] */
  related: string[];
  status: NodeStatus;
  /** ISO 8601 timestamp */
  linked_at: string;
}

// ---------------------------------------------------------------------------
// 5. NodeChangedEvent — Redis pub/sub vaultmind:events → web app via SSE
// ---------------------------------------------------------------------------

/**
 * Published on Redis pub/sub channel vaultmind:events.
 * Delivered to the browser via SSE.
 *
 * Deliberately minimal — 'something changed, here's the id.'
 * On receipt the web app re-reads the file from disk + reruns git status.
 * Disk is the source of truth; the event is a trigger, not a payload.
 *
 * secret-detected is a display-cache signal, NOT a write-failure indicator.
 */
export interface NodeChangedEvent {
  event: NodeChangedEventType;
  id: string;
  /** ISO 8601 timestamp */
  ts: string;
}

// ---------------------------------------------------------------------------
// 6. TurnProgress — Redis pub/sub vaultmind:progress → Orchestrator
// ---------------------------------------------------------------------------

/**
 * Published at each pipeline stage to Redis pub/sub vaultmind:progress.
 * Consumed by the Orchestrator for failure visibility + stuck detection.
 *
 * The Orchestrator keeps an in-flight table {turn_id → last stage + ts}.
 * A turn at 'written' but not 'done' past a timeout is flagged 'stuck'.
 */
export interface TurnProgress {
  turn_id: string;
  stage: TurnStage;
  node_ids: string[];
  /** ISO 8601 timestamp */
  ts: string;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Node frontmatter (AC-1) — web app reads this from parsed .md files
// ---------------------------------------------------------------------------

/**
 * Parsed frontmatter of a vault node (vault/nodes/<id>.md).
 * The web app reads this; the pipeline writes it via contracts above.
 * The `related` field is CONNECTOR-OWNED; the body is immutable after write.
 */
export interface NodeFrontmatter {
  /** == filename basename; stable [[link]] target */
  id: string;
  type: NodeType;
  title: string;
  /** ISO 8601 + tz; stamped by Note Creator at write */
  created: string;
  source_tool: SourceTool;
  source_session: string;
  /** IntentLog entry key current at write-time */
  intent_ref: string;
  status: NodeStatus;
  /** [[wikilinks]] — CONNECTOR-OWNED, starts empty */
  related: string[];
  /** e.g. ['post-compaction', 'secret-detected'] */
  flags: string[];
}

// ---------------------------------------------------------------------------
// Display states (AC-7) — derived by the web app, never stored in frontmatter
// ---------------------------------------------------------------------------

/**
 * The five display states for a node, derived live by the web app.
 * Precedence (most urgent wins): conflicted > blocked > awaiting-review >
 * uncommitted > clean.
 */
export type NodeDisplayState =
  | "conflicted"     // git conflict markers in file — blocks commit + handoff
  | "blocked"        // live scanForSecrets match — blocks commit + handoff
  | "awaiting-review"// frontmatter status: pending — blocks handoff until approved
  | "uncommitted"    // git status differs from HEAD — nothing blocked
  | "clean";         // approved + committed + scan-clean
