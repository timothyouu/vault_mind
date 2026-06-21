# P1 — Ingestion Stream Design

**Date:** 2026-06-21  
**Scope:** Full P1 implementation — hooks, transcript reader, cursor, Redis producer, SessionState writer  
**Approach:** Thin hook shims + `vaultmind/ingest/` module (Approach B)

---

## Goal

Wire up Claude Code's Stop and SessionEnd hooks so that every completed turn is automatically
captured, packaged as a `QueueItem`, and pushed to the Redis Stream `vaultmind:turns`. The
watcher (already running) picks these up and writes vault nodes. After this stream, talking to
Claude creates nodes — no manual injection needed.

---

## File Layout

```
vaultmind/ingest/
  __init__.py          (exists, stays empty)
  reader.py            — transcript JSONL parser + turn-pair extractor
  cursor.py            — per-session cursor (atomic JSON under .vaultmind/cursors/)
  producer.py          — QueueItem builder + Redis XADD
  session_state.py     — SessionState.md append (atomic rename + .lock)

.vaultmind/hooks/
  on_stop.py           — replaces stub; ~10-line shim → ingest
  on_session_end.py    — replaces stub; ~10-line shim → ingest

.vaultmind/cursors/    — new dir, git-ignored; one JSON file per session_id

tests/
  test_p1_reader.py
  test_p1_cursor.py
  test_p1_producer.py
  test_p1_session_state.py
```

No changes to `contracts.py`, `types.ts`, `watcher.py`, or any other stream's files.

---

## Data Flow

```
Claude Code turn completes
        │
        ▼
on_stop.py  (stdin JSON: session_id, transcript_path)
        │
        ├─► cursor.py        load cursor for session_id → last_uuid (None on first run)
        │
        ├─► reader.py        parse transcript JSONL
        │                    skip entries ≤ last_uuid
        │                    collect new (user_text, assistant_text) typed turn pairs
        │                    detect compact_boundary entries → flag list
        │
        ├─► producer.py      for each new turn pair:
        │                    build QueueItem (contracts.py)
        │                    XADD → Redis Stream vaultmind:turns
        │                    (never creates consumer group — watcher's job per AC-3)
        │
        ├─► session_state.py append timestamped row to vault/SessionState.md
        │                    atomic write-temp-rename + .lock sentinel
        │
        └─► cursor.py        save last processed user UUID

SessionEnd hook fires (Claude Code only)
        │
        ▼
on_session_end.py  (stdin JSON: session_id, reason)
        └─► session_state.py  append "session ended (reason: X)" row
```

---

## Components

### `reader.py`

- Accepts `transcript_path: str | None` and `last_uuid: str | None`.
- Returns `(list[ParsedTurn], list[str] flags)` where `ParsedTurn` is a small dataclass:
  ```python
  @dataclass
  class ParsedTurn:
      turn_text: TurnText   # user + assistant verbatim text
      uuid: str             # UUID of the user message — used to save the cursor
  ```
- If `transcript_path` is None or the file doesn't exist: return `([], [])` — no exception.
- Parses JSONL line by line. Each line is a dict with a `type` field.
- **Turn pair extraction:**
  - A typed human message has `type == "user"` and `promptSource == "typed"`.
  - `message.content` is either a plain string or a list of content blocks; extract all
    `type == "text"` blocks and join with `\n`.
  - The assistant message immediately following (next `type == "assistant"` entry) provides
    the assistant text: join all `type == "text"` content blocks.
  - Skip entries until `last_uuid` is found; collect pairs after that point only.
  - Each `ParsedTurn.uuid` is the `uuid` field of the user message entry.
- **Compaction detection:**
  - Watch for entries with `type == "system"` and `subtype == "compact_boundary"`.
  - Once seen, set a `post_compaction` flag on all subsequent turn pairs in this batch.

### `cursor.py`

- Cursor file path: `.vaultmind/cursors/{session_id}.json`
- Schema: `{"last_uuid": "...", "saved_at": "<ISO8601>"}`.
- `load(session_id) -> str | None` — returns `last_uuid` or None if no cursor.
- `save(session_id, last_uuid)` — atomic: write to `.vaultmind/cursors/{session_id}.tmp`,
  then `os.replace()` to final path (POSIX atomic; safe on Windows too).
- If cursor file is corrupt (JSON parse error): treat as None (start fresh for that session).

### `producer.py`

- `enqueue(turn_text: TurnText, session_id: str, transcript_path: str | None, source_tool: SourceTool, redis_url: str) -> bool`
- Builds `QueueItem` with:
  - `turn_id`: `f"{session_id}-{uuid4().hex[:8]}"` — unique per turn, stable for idempotency.
  - `session_id`, `transcript_path`, `source_tool`, `turn_text`, `enqueued_at`: UTC ISO8601.
- Serialises to `{"data": json.dumps(qi.model_dump())}` and pushes via `XADD vaultmind:turns * data <json>`.
- Never calls `XGROUP CREATE` — that is the watcher's sole responsibility (AC-3).
- On any Redis exception: log to stderr, return False. Does not raise.

### `session_state.py`

- Appends a line to `vault/SessionState.md`.
- Three event types:
  - `turn_enqueued(session_id, count, flags)` → `- YYYY-MM-DD HH:MM · claude-code · N turn(s) enqueued` (plus `⚠ post-compaction` if flagged)
  - `session_ended(session_id, reason)` → `- YYYY-MM-DD HH:MM · claude-code · session ended (reason: <reason>)`
  - `context_compacted(session_id)` → `- YYYY-MM-DD HH:MM · claude-code · ⚠ context compacted`
- Note: node IDs are not available at hook time (the watcher writes nodes asynchronously after the hook exits). The hook logs turns enqueued, not nodes written.
- **Atomic append:**
  1. Acquire `.vaultmind/session_state.lock` (create exclusively; retry up to 10 s, then steal).
  2. Read current `vault/SessionState.md` (create if absent).
  3. Append the new line.
  4. Write to `vault/SessionState.md.tmp`.
  5. `os.replace()` to `vault/SessionState.md`.
  6. Remove `.lock`.

### `on_stop.py` (replaces stub)

```python
import json, os, sys
from vaultmind.ingest import cursor, reader, producer, session_state
from vaultmind.contracts import SourceTool

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id      = payload.get("session_id", "unknown")
    transcript_path = payload.get("transcript_path")  # may be None (Codex)
    redis_url       = os.environ.get("REDIS_URL", "redis://localhost:6379")

    last_uuid = cursor.load(session_id)
    turns, flags = reader.parse(transcript_path, last_uuid)

    for t in turns:
        producer.enqueue(t.turn_text, session_id, transcript_path,
                         SourceTool.claude_code, redis_url)

    if turns:
        cursor.save(session_id, turns[-1].uuid)
        session_state.turn_enqueued(session_id, len(turns), flags)

    sys.exit(0)

if __name__ == "__main__":
    main()
```

### `on_session_end.py` (replaces stub)

```python
import json, sys
from vaultmind.ingest import session_state

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id = payload.get("session_id", "unknown")
    reason     = payload.get("reason", "other")
    session_state.session_ended(session_id, reason)
    sys.exit(0)

if __name__ == "__main__":
    main()
```

---

## Error Handling

| Failure | Behaviour |
|---|---|
| Redis down | Log to stderr, skip enqueue, exit 0. Turn is lost — acceptable (hook must not block). |
| `transcript_path` None or missing | `reader.parse` returns `([], [])`. Nothing enqueued. Exit 0. |
| Cursor file corrupt | Treat as no cursor; start fresh. Watcher idempotency key prevents duplicate nodes. |
| `SessionState.md` write fails | Log to stderr, exit 0. Session state is a convenience log, not hard dependency. |
| Stale `.lock` file | Stolen after 10 s idle. Prevents permanent write block from a crashed process. |

**No retry queue.** Retrying failed Redis pushes from inside the hook could slow the developer's session. Lost turns are acceptable; a blocked terminal is not.

---

## Testing

All tests import `vaultmind.ingest` directly and replay `fixtures/transcript.jsonl`. No hooks
invoked. No live Redis — `fakeredis` for producer tests.

| Test | Assertion |
|---|---|
| `test_reader_full` | 4 fixture turns → 4 TurnText pairs, correct user + assistant text |
| `test_reader_incremental` | Cursor at turn-2 UUID → only turns 3 and 4 returned |
| `test_reader_null_path` | `None` path → `([], [])`, no exception |
| `test_reader_compaction` | compact_boundary entry → flag on subsequent turns |
| `test_cursor_roundtrip` | Save UUID, reload → same UUID |
| `test_cursor_atomic` | Corrupt temp file mid-write → cursor file untouched |
| `test_producer_shape` | QueueItem in fakeredis matches `contracts.py` shape |
| `test_producer_redis_down` | Unreachable Redis → logs to stderr, no exception raised |
| `test_session_state_append` | Two concurrent threads append → two rows, no corruption |
| `test_session_state_lock_timeout` | Stale lock → stolen after 10 s (mocked clock) |

---

## Constraints (from SPEC.md AC-3, AC-6)

- **Never call `XGROUP CREATE`** from P1. The watcher owns the consumer group.
- **Always exit 0** from both hook scripts, regardless of what fails.
- **`transcript_path` may be null on Codex** — handle gracefully at the reader level.
- **Stay in lane** — touch only `vaultmind/hooks/`, `vaultmind/ingest/`, `.vaultmind/cursors/`.
  Never edit `contracts.py`, `types.ts`, or any other stream's files.
- **`source_tool`** defaults to `SourceTool.claude_code` in `on_stop.py`. A future Codex
  adapter can pass `SourceTool.codex` if needed.
