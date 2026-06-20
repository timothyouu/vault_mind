"""
contracts.py — Frozen message contracts for VaultMind.

All six agent message shapes defined as Pydantic v2 BaseModel.
These types cross session-boundaries; NEVER edit without updating
webapp/types.ts in lock-step and surfacing the change for human review.

Shapes:
  1. QueueItem        — Redis Stream vaultmind:turns  (P1 writes → P2 reads)
  2. ScribeResult     — Scribe → Note Creator         (in-process, P2-internal)
  3. NodeWritten      — Note Creator → Connector      (in-process, P2↔P3 seam)
  4. LinkResult       — Connector → Orchestrator      (in-process / record)
  5. NodeChangedEvent — Redis pub/sub vaultmind:events → web app via SSE
  6. TurnProgress     — Redis pub/sub vaultmind:progress → Orchestrator
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------

class NodeType(str, Enum):
    decision = "decision"
    constraint = "constraint"
    goal = "goal"
    question = "question"
    scope = "scope"  # reserved for ProjectGoal, Constraints, TechStack anchors


class NodeStatus(str, Enum):
    pending = "pending"
    approved = "approved"


class TurnStage(str, Enum):
    started = "started"
    extracted = "extracted"
    written = "written"
    linked = "linked"
    done = "done"
    failed = "failed"


class NodeChangedEventType(str, Enum):
    created = "created"
    linked = "linked"
    updated = "updated"
    deleted = "deleted"
    secret_detected = "secret-detected"
    intent_updated = "intent-updated"
    session_event = "session-event"


class SourceTool(str, Enum):
    claude_code = "claude-code"
    codex = "codex"


# ---------------------------------------------------------------------------
# 1. QueueItem — Redis Stream vaultmind:turns
# ---------------------------------------------------------------------------

class TurnText(BaseModel):
    """Verbatim user+assistant pair from a single hook invocation."""
    user: str
    assistant: str


class QueueItem(BaseModel):
    """
    Written by P1 (hook → Redis Stream vaultmind:turns).
    Read by P2 (watcher consumer group vaultmind-workers).

    Consumer group is created once by the watcher at startup — P1's producer
    must never create it.
    """
    turn_id: str = Field(
        description="Unique per turn: <session_id>-<seq>",
    )
    source_tool: SourceTool
    session_id: str = Field(description="session_id from the hook stdin")
    transcript_path: str | None = Field(
        default=None,
        description="Absolute path to transcript file; null is possible on Codex",
    )
    turn_text: TurnText = Field(
        description="Verbatim fresh turn — hook puts this directly in the queue",
    )
    enqueued_at: str = Field(description="ISO 8601 timestamp")


# ---------------------------------------------------------------------------
# 2. ScribeResult — Scribe → Note Creator (in-process)
# ---------------------------------------------------------------------------

class Extraction(BaseModel):
    """One extracted node from a turn."""
    type: NodeType
    title: str
    slug: str = Field(description="URL-safe slug; part of the filename basename")
    body: str = Field(
        description="Immutable, Scribe-authored markdown body. Never edited downstream.",
    )


class ScribeResult(BaseModel):
    """
    Produced by the Scribe; consumed in-process by the Note Creator.
    Also the basis for the Orchestrator 'turn-started' notice.

    extractions is 0..n — empty means nothing noteworthy, no node written.
    intent_shift is turn-level; when non-null it routes by mode:
      Auto → append to IntentLog as ai-detected
      Review → surface as a suggestion
    """
    turn_id: str
    source_tool: SourceTool
    source_session: str
    extractions: list[Extraction] = Field(default_factory=list)
    intent_shift: str | None = Field(
        default=None,
        description="Detected intent shift text, or null if no shift detected",
    )


# ---------------------------------------------------------------------------
# 3. NodeWritten — Note Creator → Connector (in-process, P2↔P3 seam)
# ---------------------------------------------------------------------------

class NodeWritten(BaseModel):
    """
    Emitted by the Note Creator after writing a node to disk.
    Consumed in-process by the Connector (P3).
    """
    id: str = Field(
        description="Node basename == filename basename == [[wikilink]] target",
        examples=["2026-06-21-1432-supabase-rls-policies"],
    )
    path: str = Field(
        description="Relative path from repo root, e.g. vault/nodes/<id>.md",
    )
    type: NodeType
    title: str
    status: NodeStatus
    flags: list[str] = Field(default_factory=list)
    intent_ref: str = Field(
        description="IntentLog entry key current at write-time, e.g. '2026-06-21 14:32'",
    )


# ---------------------------------------------------------------------------
# 4. LinkResult — Connector → Orchestrator (point of record)
# ---------------------------------------------------------------------------

class LinkResult(BaseModel):
    """
    Produced by the Connector after writing `related` frontmatter.
    Consumed by the Orchestrator as the turn's point-of-record.
    """
    id: str
    related: list[str] = Field(
        description="Wikilinks written to frontmatter, e.g. ['[[Constraints]]']",
    )
    status: NodeStatus
    linked_at: str = Field(description="ISO 8601 timestamp")


# ---------------------------------------------------------------------------
# 5. NodeChangedEvent — Redis pub/sub vaultmind:events → web app via SSE
# ---------------------------------------------------------------------------

class NodeChangedEvent(BaseModel):
    """
    Published on Redis pub/sub channel vaultmind:events.
    Delivered to the browser via SSE.

    Deliberately minimal — 'something changed, here's the id.'
    On receipt the web app re-reads the file from disk + reruns git status.
    Disk is the source of truth; the event is a trigger, not a payload.

    secret-detected is a display-cache signal, NOT a write-failure indicator.
    """
    event: NodeChangedEventType
    id: str
    ts: str = Field(description="ISO 8601 timestamp")


# ---------------------------------------------------------------------------
# 6. TurnProgress — Redis pub/sub vaultmind:progress → Orchestrator
# ---------------------------------------------------------------------------

class TurnProgress(BaseModel):
    """
    Published at each pipeline stage to Redis pub/sub vaultmind:progress.
    Consumed by the Orchestrator for failure visibility + stuck detection.

    The Orchestrator keeps an in-flight table {turn_id → last stage + ts}.
    A turn at 'written' but not 'done' past a timeout is flagged 'stuck'.
    """
    turn_id: str
    stage: TurnStage
    node_ids: list[str] = Field(default_factory=list)
    ts: str = Field(description="ISO 8601 timestamp")
    error: str | None = Field(default=None)
