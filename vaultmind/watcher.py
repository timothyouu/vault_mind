"""
vaultmind/watcher.py — Pipeline consumer loop.

Run with: python -m vaultmind.watcher

Reads QueueItems from Redis Stream vaultmind:turns (consumer group vaultmind-workers).
Hot path: stub_scribe → stub_note_creator → stub_connector
ACKs ONLY after the full chain succeeds; crash-before-ACK = item stays in PEL.

Plug-in points (replace stubs when P1/P2/P3 land):
  SCRIBE_FN       = stub_scribe        # P2 replaces
  NOTE_CREATOR_FN = stub_note_creator  # P2 replaces
  CONNECTOR_FN    = stub_connector     # P3 replaces
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import pathlib
import sys
import time

# Redis is a required runtime dependency but may not be installed at import time.
# The module must remain importable so tests and static analysis work without it.
try:
    import redis
    import redis.exceptions
    _REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]
    _REDIS_AVAILABLE = False

from vaultmind.contracts import (
    Extraction,
    LinkResult,
    NodeChangedEvent,
    NodeChangedEventType,
    NodeStatus,
    NodeType,
    NodeWritten,
    QueueItem,
    ScribeResult,
    SourceTool,
    TurnProgress,
    TurnStage,
)
from vaultmind.secrets import scan_for_secrets
from opentelemetry import trace as otel_trace
from vaultmind.arize_init import (
    init_arize,
    SERVICE_PIPELINE,
    ATTR_TURN_ID,
    SPAN_TURN,
    SPAN_STAGE_SCRIBE,
    SPAN_STAGE_NOTECREATOR,
    SPAN_STAGE_CONNECTOR,
)
from vaultmind.evals import run_eval

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stream / group constants
# ---------------------------------------------------------------------------

STREAM_TURNS     = "vaultmind:turns"      # Redis Stream (XADD / XREADGROUP)
CHANNEL_PROGRESS = "vaultmind:progress"   # Redis pub/sub channel
CHANNEL_EVENTS   = "vaultmind:events"     # Redis pub/sub channel
GROUP_NAME       = "vaultmind-workers"

# Minimum idle time (ms) before a PEL entry is auto-claimed on restart.
_RECLAIM_MIN_IDLE_MS = 5 * 60 * 1000  # 5 minutes

# ---------------------------------------------------------------------------
# Redis connection factory
# ---------------------------------------------------------------------------

def _redis() -> "redis.Redis":  # type: ignore[name-defined]
    """Return a Redis client.  URL from REDIS_URL env var (default: localhost)."""
    if not _REDIS_AVAILABLE:
        raise RuntimeError(
            "redis-py is not installed.  "
            "Install it with: pip install redis"
        )
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    return redis.from_url(url, decode_responses=True)  # type: ignore[attr-defined]


# Test injection point — tests can replace this with a fakeredis factory.
# Production code always calls _redis_factory() to get a client.
_redis_factory = _redis


# ---------------------------------------------------------------------------
# Consumer-group bootstrap (idempotent)
# ---------------------------------------------------------------------------

def _ensure_consumer_group(r: "redis.Redis") -> None:  # type: ignore[name-defined]
    """
    Create the consumer group vaultmind-workers on vaultmind:turns.

    Uses MKSTREAM so the stream itself is created if absent.
    Uses id='0' so new consumers see all existing messages on first read.
    Safe to call on every startup — BUSYGROUP means it already exists.

    Per AC-3: this must be called by the watcher only; P1's producer must
    never create this group.
    """
    try:
        r.xgroup_create(STREAM_TURNS, GROUP_NAME, id="0", mkstream=True)
        logger.info("Created consumer group %s on %s", GROUP_NAME, STREAM_TURNS)
    except redis.exceptions.ResponseError as exc:  # type: ignore[attr-defined]
        if "BUSYGROUP" in str(exc):
            pass  # already exists — fully idempotent
        else:
            raise


# ---------------------------------------------------------------------------
# TurnProgress publisher
# ---------------------------------------------------------------------------

def _publish_progress(
    r: "redis.Redis",  # type: ignore[name-defined]
    turn_id: str,
    stage: TurnStage,
    node_ids: list[str] | None = None,
    error: str | None = None,
) -> None:
    """Publish a TurnProgress event to vaultmind:progress (Redis pub/sub)."""
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = {
        "turn_id": turn_id,
        "stage": stage.value,
        "node_ids": node_ids or [],
        "ts": ts,
        "error": error,
    }
    r.publish(CHANNEL_PROGRESS, json.dumps(payload))


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------

def _idempotency_key(turn_id: str) -> str:
    return f"vaultmind:turn:{turn_id}"


def _get_stage(r: "redis.Redis", turn_id: str) -> str | None:  # type: ignore[name-defined]
    """Return the last recorded pipeline stage for this turn, or None."""
    return r.hget(_idempotency_key(turn_id), "stage")


def _set_stage(
    r: "redis.Redis",  # type: ignore[name-defined]
    turn_id: str,
    stage: str,
    node_ids: list[str] | None = None,
) -> None:
    """Persist the current stage + node_ids; set a 7-day TTL."""
    r.hset(
        _idempotency_key(turn_id),
        mapping={
            "stage": stage,
            "node_ids": json.dumps(node_ids or []),
        },
    )
    r.expire(_idempotency_key(turn_id), 86400 * 7)  # 7-day TTL


# ---------------------------------------------------------------------------
# Stub: Scribe
# ---------------------------------------------------------------------------

def stub_scribe(qi: QueueItem) -> ScribeResult:
    """
    Stub Scribe — returns a single 'decision' extraction derived from turn_id.

    P2 replaces this with the real Scribe (LLM extraction).
    The contract: accepts QueueItem, returns ScribeResult.
    """
    slug = qi.turn_id.replace(":", "-").replace("/", "-").lower()
    extraction = Extraction(
        type=NodeType.decision,
        title=f"[stub] Decision from turn {qi.turn_id}",
        slug=slug,
        body=(
            f"Stub extraction from turn {qi.turn_id}.\n\n"
            f"> \"{qi.turn_text.user[:120]}…\""
        ),
    )
    return ScribeResult(
        turn_id=qi.turn_id,
        source_tool=qi.source_tool,
        source_session=qi.session_id,
        extractions=[extraction],
        intent_shift=None,
    )


# ---------------------------------------------------------------------------
# Stub: NoteCreator
# ---------------------------------------------------------------------------

_NODE_TEMPLATE = """\
---
id: {id}
type: {type}
title: "{title}"
created: {created}
source_tool: {source_tool}
source_session: {source_session}
intent_ref: {intent_ref}
status: approved
related: []
flags: {flags_yaml}
---
{body}
"""


def stub_note_creator(
    sr: ScribeResult,
    vault_root: pathlib.Path,
) -> list[NodeWritten]:
    """
    Stub NoteCreator — writes a real .md file per extraction to vault_root/nodes/.

    Steps:
      1. Derive the node id from current datetime + extraction.slug.
      2. Build frontmatter + body via the AC-1 template.
      3. Run scanForSecrets on the content; if matched, set flags=[secret-detected].
      4. Write the file to disk.
      5. Return a NodeWritten per extraction (empty list if extractions=[]).

    P2 replaces this with the real NoteCreator.
    """
    nodes_dir = vault_root / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    written: list[NodeWritten] = []

    now = datetime.datetime.now(datetime.timezone.utc)
    # id prefix: YYYY-MM-DD-HHMM
    id_prefix = now.strftime("%Y-%m-%d-%H%M")
    # intent_ref: YYYY-MM-DD HH:MM
    intent_ref = now.strftime("%Y-%m-%d %H:%M")
    # created: full ISO 8601 with timezone
    created_iso = now.isoformat()

    for extraction in sr.extractions:
        node_id = f"{id_prefix}-{extraction.slug}"
        node_path = nodes_dir / f"{node_id}.md"

        # Build content without flags first to check for secrets
        flags: list[str] = []
        flags_yaml = "[]"

        # Escape any double-quotes in title so the YAML frontmatter stays valid.
        safe_title = extraction.title.replace('"', '\\"')

        content_no_flags = _NODE_TEMPLATE.format(
            id=node_id,
            type=extraction.type.value,
            title=safe_title,
            created=created_iso,
            source_tool=sr.source_tool.value,
            source_session=sr.source_session,
            intent_ref=intent_ref,
            flags_yaml="[]",
            body=extraction.body,
        )

        # Write-time secret scan (per AC-5): flags node, does NOT block write.
        secret_matches = scan_for_secrets(content_no_flags)
        if secret_matches:
            flags = ["secret-detected"]
            flags_yaml = '["secret-detected"]'
            logger.warning(
                "Secret detected in node %s (%d match(es)); flagging node.",
                node_id,
                len(secret_matches),
            )

        content = _NODE_TEMPLATE.format(
            id=node_id,
            type=extraction.type.value,
            title=safe_title,
            created=created_iso,
            source_tool=sr.source_tool.value,
            source_session=sr.source_session,
            intent_ref=intent_ref,
            flags_yaml=flags_yaml,
            body=extraction.body,
        )

        node_path.write_text(content, encoding="utf-8")
        logger.info("NoteCreator wrote node: %s", node_path)

        # NodeWritten.path must be relative from repo root per the contract doc.
        # vault_root.parent == repo root (vault_root is e.g. /repo/vault/).
        relative_path = node_path.relative_to(vault_root.parent)
        written.append(
            NodeWritten(
                id=node_id,
                path=str(relative_path),
                type=extraction.type,
                title=extraction.title,
                status=NodeStatus.approved,
                flags=flags,
                intent_ref=intent_ref,
            )
        )

    return written


# ---------------------------------------------------------------------------
# Stub: Connector
# ---------------------------------------------------------------------------

def stub_connector(
    nw: NodeWritten,
    r: "redis.Redis",  # type: ignore[name-defined]
    vault_root: pathlib.Path,
) -> LinkResult:
    """
    Stub Connector — writes a hardcoded related link to the node's frontmatter
    and publishes a NodeChangedEvent to vaultmind:events.

    Steps:
      1. Read the node file written by NoteCreator.
      2. Replace 'related: []' with 'related:\\n  - "[[Constraints]]"' (stub link).
      3. Write the file back (per AC-1: Connector edits ONLY frontmatter related).
      4. Publish NodeChangedEvent(event="linked", ...) to vaultmind:events.
      5. Return LinkResult.

    P3 replaces this with the real Connector (vector search + heuristic linking).
    """
    # Resolve path: NodeWritten.path is relative from repo root per the contract;
    # vault_root.parent == repo root.  Accept absolute paths too for safety.
    _p = pathlib.Path(nw.path)
    node_path = _p if _p.is_absolute() else vault_root.parent / _p
    content = node_path.read_text(encoding="utf-8")

    # Simple string replacement on the YAML line — stub only.
    # The Connector (P3) will use a proper YAML-aware implementation.
    if "related: []" in content:
        content = content.replace(
            "related: []",
            'related:\n  - "[[Constraints]]"',
        )
        node_path.write_text(content, encoding="utf-8")
        logger.info("Connector updated related for node: %s", nw.id)
    else:
        logger.warning(
            "Connector: expected 'related: []' in %s but not found; skipping.",
            nw.id,
        )

    related = ["[[Constraints]]"]

    # Publish NodeChangedEvent to vaultmind:events (→ web app via SSE).
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    event = NodeChangedEvent(
        event=NodeChangedEventType.linked,
        id=nw.id,
        ts=ts,
    )
    r.publish(CHANNEL_EVENTS, json.dumps({
        "event": event.event.value,
        "id": event.id,
        "ts": event.ts,
    }))

    linked_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return LinkResult(
        id=nw.id,
        related=related,
        status=nw.status,
        linked_at=linked_at,
    )


# ---------------------------------------------------------------------------
# Plug-in points — replace these names when P2 / P3 land
# ---------------------------------------------------------------------------

SCRIBE_FN       = stub_scribe        # P2 replaces
NOTE_CREATOR_FN = stub_note_creator  # P2 replaces
CONNECTOR_FN    = stub_connector     # P3 replaces


# ---------------------------------------------------------------------------
# Per-message processing
# ---------------------------------------------------------------------------

def _process_message(
    r: "redis.Redis",  # type: ignore[name-defined]
    msg_id: str,
    fields: dict[str, str],
    vault_root: pathlib.Path,
    tracer=None,
) -> None:
    """
    Process one Redis Stream message through the full pipeline chain.

    Hot path: stub_scribe → stub_note_creator → stub_connector.
    ACKs ONLY after the complete chain succeeds (AC-4).
    On any exception: publish failed progress, do NOT ACK, log and return.
    """
    # Deserialize QueueItem from Redis Stream fields.
    # Redis Stream XADD serialises nested objects as JSON strings on the way in
    # (see the P1 producer); we reconstruct from the raw fields dict.
    try:
        # The stream field 'data' holds the full JSON payload, or fields are
        # individual keys — support both formats (producer detail is P1-owned).
        if "data" in fields:
            raw = json.loads(fields["data"])
        else:
            # Fields are individual keys; turn_text is nested JSON.
            raw = dict(fields)
            if isinstance(raw.get("turn_text"), str):
                raw["turn_text"] = json.loads(raw["turn_text"])

        qi = QueueItem.model_validate(raw)
    except Exception as exc:
        logger.error("Failed to deserialize QueueItem from msg %s: %s", msg_id, exc)
        # Cannot publish progress without a turn_id; just log and do NOT ACK.
        # The message stays in PEL and will be retried.
        return

    turn_id = qi.turn_id

    # ------------------------------------------------------------------
    # Idempotency guard: if this turn already completed, ACK and skip.
    # ------------------------------------------------------------------
    prior_stage = _get_stage(r, turn_id)
    if prior_stage == TurnStage.done.value:
        logger.info("Turn %s already done (idempotency); ACKing msg %s", turn_id, msg_id)
        r.xack(STREAM_TURNS, GROUP_NAME, msg_id)
        return

    logger.info("Processing turn %s (msg %s)", turn_id, msg_id)

    # ------------------------------------------------------------------
    # Stage: started
    # ------------------------------------------------------------------
    _publish_progress(r, turn_id, TurnStage.started)
    _set_stage(r, turn_id, TurnStage.started.value)

    try:
        # ----------------------------------------------------------------
        # Stage: Scribe extraction
        # ----------------------------------------------------------------
        scribe_result = SCRIBE_FN(qi)

        extracted_ids = [
            f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d-%H%M')}"
            f"-{ext.slug}"
            for ext in scribe_result.extractions
        ]
        _publish_progress(r, turn_id, TurnStage.extracted, node_ids=extracted_ids)
        _set_stage(r, turn_id, TurnStage.extracted.value, node_ids=extracted_ids)

        # ----------------------------------------------------------------
        # Stage: NoteCreator — write .md files
        # ----------------------------------------------------------------
        nodes_written: list[NodeWritten] = NOTE_CREATOR_FN(scribe_result, vault_root)

        written_ids = [nw.id for nw in nodes_written]
        _publish_progress(r, turn_id, TurnStage.written, node_ids=written_ids)
        _set_stage(r, turn_id, TurnStage.written.value, node_ids=written_ids)

        # ----------------------------------------------------------------
        # Stage: Connector — populate related, publish node-changed
        # ----------------------------------------------------------------
        link_results: list[LinkResult] = []
        for nw in nodes_written:
            lr = CONNECTOR_FN(nw, r, vault_root)
            link_results.append(lr)

        linked_ids = [lr.id for lr in link_results]
        _publish_progress(r, turn_id, TurnStage.linked, node_ids=linked_ids)
        _set_stage(r, turn_id, TurnStage.linked.value, node_ids=linked_ids)

        # ----------------------------------------------------------------
        # ACK — only here, after the full chain succeeds (AC-4)
        # ----------------------------------------------------------------
        r.xack(STREAM_TURNS, GROUP_NAME, msg_id)
        logger.info("ACKed msg %s for turn %s", msg_id, turn_id)

        # ----------------------------------------------------------------
        # Stage: done — set idempotency key + final progress event
        # ----------------------------------------------------------------
        _set_stage(r, turn_id, TurnStage.done.value, node_ids=linked_ids)
        _publish_progress(r, turn_id, TurnStage.done, node_ids=linked_ids)
        logger.info("Turn %s completed successfully", turn_id)

    except Exception as exc:
        # Any failure: publish failed progress, do NOT ACK.
        # The item stays in PEL and will be reclaimed via XAUTOCLAIM on restart.
        err_str = str(exc)
        logger.error("Turn %s failed: %s", turn_id, err_str, exc_info=True)
        _publish_progress(r, turn_id, TurnStage.failed, error=err_str)
        # Deliberately do NOT set idempotency stage to 'failed' so a retry can
        # resume from the last successfully completed stage on redelivery.


# ---------------------------------------------------------------------------
# PEL reclaim (stuck-message recovery on restart)
# ---------------------------------------------------------------------------

def _reclaim_pending(
    r: "redis.Redis",  # type: ignore[name-defined]
    consumer: str,
    vault_root: pathlib.Path,
    tracer=None,
) -> None:
    """
    Claim and reprocess any PEL entries idle longer than _RECLAIM_MIN_IDLE_MS.

    This handles crash-before-ACK recovery (AC-4): a turn that failed mid-chain
    stays in the PEL; on restart the watcher claims it and retries from the
    last completed stage (idempotency key guards duplicate work).
    """
    try:
        # XAUTOCLAIM returns (next-cursor, entries, deleted-ids) in redis-py ≥4
        result = r.xautoclaim(
            STREAM_TURNS,
            GROUP_NAME,
            consumer,
            min_idle_time=_RECLAIM_MIN_IDLE_MS,
            start_id="0-0",
            count=10,
        )
        # redis-py ≥4 returns (next_start_id, messages, deleted)
        # redis-py 3.x returns a different shape — handle both.
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            entries = result[1]
        else:
            entries = result  # fallback: treat the whole result as entries

        if entries:
            logger.info("Reclaimed %d pending message(s)", len(entries))
            for msg_id, fields in entries:
                logger.info("Reprocessing reclaimed msg %s", msg_id)
                _process_message(r, msg_id, fields, vault_root, tracer)
    except Exception as exc:  # pragma: no cover
        # XAUTOCLAIM may not be available in very old Redis versions; log and continue.
        logger.warning("XAUTOCLAIM failed (skipping PEL reclaim): %s", exc)


# ---------------------------------------------------------------------------
# Main watcher loop
# ---------------------------------------------------------------------------

def run_watcher(vault_root: pathlib.Path) -> None:
    """
    Start the watcher loop.

    1. Init Arize tracing (no-op if credentials absent).
    2. Connect to Redis.
    3. Ensure the consumer group exists (idempotent).
    4. Loop:
       a. Reclaim any stuck PEL messages.
       b. XREADGROUP for new messages (block 2 s).
       c. Process each message through the full pipeline chain.
    """
    init_arize(SERVICE_PIPELINE)
    tracer = otel_trace.get_tracer(SERVICE_PIPELINE)

    r = _redis_factory()
    _ensure_consumer_group(r)

    # Consumer name includes PID so multiple watcher processes don't share a
    # consumer slot; P1 may adjust this convention to watcher-<pid>.
    consumer = f"watcher-{os.getpid()}"
    logger.info(
        "Watcher started — consumer=%s, vault=%s",
        consumer,
        vault_root,
    )

    # Reclaim any stuck PEL messages left by a previous crashed process.
    _reclaim_pending(r, consumer, vault_root, tracer)

    _reclaim_counter = 0
    while True:
        # Periodically re-check PEL for items that became idle after startup
        # (e.g., a peer consumer that crashed while we were running).
        _reclaim_counter += 1
        if _reclaim_counter % 150 == 0:  # ~every 5 minutes at 2 s/iteration
            _reclaim_pending(r, consumer, vault_root, tracer)

        # Read the next message (block up to 2 s for new arrivals).
        try:
            messages = r.xreadgroup(
                GROUP_NAME,
                consumer,
                {STREAM_TURNS: ">"},
                count=1,
                block=2000,  # 2 s
            )
        except Exception as exc:
            logger.error("XREADGROUP error: %s — sleeping 1 s", exc, exc_info=True)
            time.sleep(1)
            continue

        if not messages:
            # No new messages within the block window; loop again.
            continue

        for _stream_name, entries in messages:
            for msg_id, fields in entries:
                _process_message(r, msg_id, fields, vault_root, tracer)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    vault_root = pathlib.Path(os.environ.get("VAULTMIND_VAULT_ROOT", "./vault"))
    vault_root.mkdir(parents=True, exist_ok=True)
    (vault_root / "nodes").mkdir(exist_ok=True)

    run_watcher(vault_root)
