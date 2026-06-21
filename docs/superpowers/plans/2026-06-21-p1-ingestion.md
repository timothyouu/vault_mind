# P1 — Ingestion Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up Claude Code's Stop/SessionEnd hooks so every completed turn is automatically captured, queued in Redis, and written as a vault node — no manual injection required.

**Architecture:** Four focused modules in `vaultmind/ingest/` (cursor, reader, producer, session_state) with thin hook shims in `.vaultmind/hooks/`. All logic is in the importable package for testability; hooks are ~15-line wrappers that always exit 0.

**Tech Stack:** Python 3.11+, Pydantic v2, redis-py ≥ 6, fakeredis (tests), pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `vaultmind/ingest/cursor.py` | Create | Per-session cursor: load/save last processed UUID (atomic) |
| `vaultmind/ingest/reader.py` | Create | Parse Claude Code transcript JSONL, extract new typed turn pairs |
| `vaultmind/ingest/producer.py` | Create | Build QueueItem, XADD to Redis `vaultmind:turns` |
| `vaultmind/ingest/session_state.py` | Create | Atomic append to `vault/SessionState.md` with `.lock` sentinel |
| `.vaultmind/hooks/on_stop.py` | Replace stub | 15-line shim calling ingest |
| `.vaultmind/hooks/on_session_end.py` | Replace stub | 15-line shim calling ingest |
| `.claude/settings.json` | Create | Register Stop + SessionEnd hooks with Claude Code |
| `.gitignore` | Modify | Add `.vaultmind/cursors/` |
| `tests/test_p1_cursor.py` | Create | Unit tests for cursor |
| `tests/test_p1_reader.py` | Create | Unit tests for reader |
| `tests/test_p1_producer.py` | Create | Unit tests for producer (fakeredis) |
| `tests/test_p1_session_state.py` | Create | Unit tests for session_state (concurrency) |

**Never touch:** `contracts.py`, `types.ts`, `watcher.py`, `secrets.py`, any other stream's files.

---

## Task 1: `cursor.py` — per-session bookmark

**Files:**
- Create: `vaultmind/ingest/cursor.py`
- Create: `tests/test_p1_cursor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_p1_cursor.py`:

```python
import json
import os
import pytest
from pathlib import Path
from vaultmind.ingest import cursor


@pytest.fixture
def cursors_dir(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("VAULTMIND_VAULT_ROOT", str(vault))
    return tmp_path / ".vaultmind" / "cursors"


def test_load_returns_none_when_no_cursor(cursors_dir):
    assert cursor.load("session-abc") is None


def test_roundtrip(cursors_dir):
    cursor.save("session-abc", "uuid-1234")
    assert cursor.load("session-abc") == "uuid-1234"


def test_save_overwrites(cursors_dir):
    cursor.save("session-abc", "uuid-1")
    cursor.save("session-abc", "uuid-2")
    assert cursor.load("session-abc") == "uuid-2"


def test_load_returns_none_on_corrupt_file(cursors_dir, tmp_path):
    cursors_dir.mkdir(parents=True)
    (cursors_dir / "session-bad.json").write_text("not json")
    assert cursor.load("session-bad") is None


def test_atomic_write_uses_replace(cursors_dir, monkeypatch):
    # Verify no .tmp file is left behind after a successful save
    cursor.save("session-abc", "uuid-xyz")
    assert not (cursors_dir / "session-abc.tmp").exists()
    assert (cursors_dir / "session-abc.json").exists()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_p1_cursor.py -v
```

Expected: 5 failures — `cannot import name 'cursor' from 'vaultmind.ingest'`

- [ ] **Step 3: Implement `cursor.py`**

Create `vaultmind/ingest/cursor.py`:

```python
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _cursors_dir() -> Path:
    vault_root = Path(os.environ.get("VAULTMIND_VAULT_ROOT", "./vault"))
    return vault_root.parent / ".vaultmind" / "cursors"


def load(session_id: str) -> str | None:
    path = _cursors_dir() / f"{session_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("last_uuid")
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def save(session_id: str, last_uuid: str) -> None:
    d = _cursors_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{session_id}.json"
    tmp = d / f"{session_id}.tmp"
    payload = {
        "last_uuid": last_uuid,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)
```

- [ ] **Step 4: Run tests — all pass**

```
pytest tests/test_p1_cursor.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```
git add vaultmind/ingest/cursor.py tests/test_p1_cursor.py
git commit -m "feat(p1): cursor — atomic per-session bookmark"
```

---

## Task 2: `reader.py` — transcript parser

**Files:**
- Create: `vaultmind/ingest/reader.py`
- Create: `tests/test_p1_reader.py`

The Claude Code transcript is a JSONL file. Each line is one of:
- `{"type": "user", "promptSource": "typed", "uuid": "...", "message": {"role": "user", "content": "..." or [...]}, ...}`
- `{"type": "assistant", "uuid": "...", "message": {"role": "assistant", "content": [{"type": "text", "text": "..."}]}, ...}`
- `{"type": "system", "subtype": "compact_boundary", ...}` — context compaction marker
- Other types (tool_result, mode, permission-mode, etc.) — ignored

A "turn pair" is one typed user message + the next assistant message.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_p1_reader.py`:

```python
import json
import pytest
from pathlib import Path
from vaultmind.ingest import reader
from vaultmind.ingest.reader import ParsedTurn


# ---------------------------------------------------------------------------
# Helpers to build synthetic CC transcript entries
# ---------------------------------------------------------------------------

def _user(uuid: str, text: str, prompt_source: str = "typed") -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "promptSource": prompt_source,
        "message": {"role": "user", "content": text},
        "sessionId": "sess-1",
        "timestamp": "2026-06-21T10:00:00Z",
    }


def _user_list(uuid: str, text: str) -> dict:
    """User message with content as a list of blocks (tool_result style)."""
    return {
        "type": "user",
        "uuid": uuid,
        "promptSource": "typed",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}, {"type": "tool_result", "content": "ignored"}],
        },
        "sessionId": "sess-1",
        "timestamp": "2026-06-21T10:00:00Z",
    }


def _assistant(uuid: str, text: str) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
        "sessionId": "sess-1",
        "timestamp": "2026-06-21T10:01:00Z",
    }


def _compact_boundary() -> dict:
    return {"type": "system", "subtype": "compact_boundary", "sessionId": "sess-1"}


def _write_transcript(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_returns_empty_for_none_path():
    turns, flags = reader.parse(None, None)
    assert turns == []
    assert flags == []


def test_returns_empty_for_missing_file(tmp_path):
    turns, flags = reader.parse(str(tmp_path / "nonexistent.jsonl"), None)
    assert turns == []
    assert flags == []


def test_full_transcript_two_turns(tmp_path):
    t = tmp_path / "transcript.jsonl"
    _write_transcript(t, [
        _user("u1", "Hello"),
        _assistant("a1", "Hi there"),
        _user("u2", "Follow up"),
        _assistant("a2", "Sure thing"),
    ])
    turns, flags = reader.parse(str(t), None)
    assert len(turns) == 2
    assert turns[0].uuid == "u1"
    assert turns[0].turn_text.user == "Hello"
    assert turns[0].turn_text.assistant == "Hi there"
    assert turns[1].uuid == "u2"
    assert turns[1].turn_text.user == "Follow up"
    assert turns[1].turn_text.assistant == "Sure thing"
    assert flags == []


def test_incremental_skips_processed(tmp_path):
    t = tmp_path / "transcript.jsonl"
    _write_transcript(t, [
        _user("u1", "First"),
        _assistant("a1", "Response 1"),
        _user("u2", "Second"),
        _assistant("a2", "Response 2"),
        _user("u3", "Third"),
        _assistant("a3", "Response 3"),
    ])
    turns, flags = reader.parse(str(t), last_uuid="u2")
    assert len(turns) == 1
    assert turns[0].uuid == "u3"
    assert turns[0].turn_text.user == "Third"


def test_skips_non_typed_user_messages(tmp_path):
    t = tmp_path / "transcript.jsonl"
    _write_transcript(t, [
        {"type": "user", "uuid": "u-tool", "promptSource": "tool",
         "message": {"role": "user", "content": [{"type": "tool_result", "content": "data"}]},
         "sessionId": "sess-1", "timestamp": "2026-06-21T10:00:00Z"},
        _user("u1", "Real message"),
        _assistant("a1", "Real response"),
    ])
    turns, flags = reader.parse(str(t), None)
    assert len(turns) == 1
    assert turns[0].turn_text.user == "Real message"


def test_content_as_list_of_blocks(tmp_path):
    t = tmp_path / "transcript.jsonl"
    _write_transcript(t, [
        _user_list("u1", "List content message"),
        _assistant("a1", "Reply"),
    ])
    turns, flags = reader.parse(str(t), None)
    assert len(turns) == 1
    assert turns[0].turn_text.user == "List content message"


def test_compaction_sets_flag(tmp_path):
    t = tmp_path / "transcript.jsonl"
    _write_transcript(t, [
        _user("u1", "Before compaction"),
        _assistant("a1", "Response 1"),
        _compact_boundary(),
        _user("u2", "After compaction"),
        _assistant("a2", "Response 2"),
    ])
    turns, flags = reader.parse(str(t), None)
    assert len(turns) == 2
    assert "post-compaction" in flags


def test_no_compaction_flag_without_marker(tmp_path):
    t = tmp_path / "transcript.jsonl"
    _write_transcript(t, [
        _user("u1", "Normal turn"),
        _assistant("a1", "Normal response"),
    ])
    turns, flags = reader.parse(str(t), None)
    assert flags == []


def test_turn_without_following_assistant(tmp_path):
    """User message at end of file with no assistant response yet — include with empty assistant."""
    t = tmp_path / "transcript.jsonl"
    _write_transcript(t, [
        _user("u1", "Waiting for response"),
    ])
    turns, flags = reader.parse(str(t), None)
    assert len(turns) == 1
    assert turns[0].turn_text.user == "Waiting for response"
    assert turns[0].turn_text.assistant == ""


def test_empty_transcript(tmp_path):
    t = tmp_path / "transcript.jsonl"
    t.write_text("", encoding="utf-8")
    turns, flags = reader.parse(str(t), None)
    assert turns == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_p1_reader.py -v
```

Expected: all fail — `cannot import name 'reader'`

- [ ] **Step 3: Implement `reader.py`**

Create `vaultmind/ingest/reader.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from vaultmind.contracts import TurnText


@dataclass
class ParsedTurn:
    turn_text: TurnText
    uuid: str


def _extract_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return ""


def parse(
    transcript_path: str | None,
    last_uuid: str | None,
) -> tuple[list[ParsedTurn], list[str]]:
    if transcript_path is None:
        return [], []

    path = Path(transcript_path)
    if not path.exists():
        return [], []

    entries: list[dict] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return [], []

    # Skip everything up to and including last_uuid
    start = 0
    if last_uuid is not None:
        for i, entry in enumerate(entries):
            if entry.get("uuid") == last_uuid:
                start = i + 1
                break

    new_entries = entries[start:]

    turns: list[ParsedTurn] = []
    flags: list[str] = []
    post_compaction = False

    i = 0
    while i < len(new_entries):
        entry = new_entries[i]

        if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
            post_compaction = True
            i += 1
            continue

        if entry.get("type") == "user" and entry.get("promptSource") == "typed":
            user_text = _extract_text(entry.get("message", {}).get("content", ""))
            user_uuid = entry.get("uuid", "")

            # Find the next assistant entry
            assistant_text = ""
            j = i + 1
            while j < len(new_entries):
                nxt = new_entries[j]
                if nxt.get("type") == "assistant":
                    assistant_text = _extract_text(
                        nxt.get("message", {}).get("content", [])
                    )
                    break
                j += 1

            turns.append(
                ParsedTurn(
                    turn_text=TurnText(user=user_text, assistant=assistant_text),
                    uuid=user_uuid,
                )
            )
            if post_compaction and "post-compaction" not in flags:
                flags.append("post-compaction")

        i += 1

    return turns, flags
```

- [ ] **Step 4: Run tests — all pass**

```
pytest tests/test_p1_reader.py -v
```

Expected: 10 passed

- [ ] **Step 5: Commit**

```
git add vaultmind/ingest/reader.py tests/test_p1_reader.py
git commit -m "feat(p1): reader — Claude Code transcript parser with cursor support"
```

---

## Task 3: `producer.py` — Redis queue writer

**Files:**
- Create: `vaultmind/ingest/producer.py`
- Create: `tests/test_p1_producer.py`

The watcher expects stream messages in the format `{"data": "<QueueItem JSON string>"}`. Confirmed in `watcher.py`: `if "data" in fields: raw = json.loads(fields["data"])`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_p1_producer.py`:

```python
import json
import sys
import fakeredis
import pytest
from unittest.mock import patch

from vaultmind.ingest import producer
from vaultmind.contracts import QueueItem, SourceTool, TurnText


TURN = TurnText(user="How does RLS work?", assistant="RLS enforces per-row access.")
SESSION = "sess-abc"
TRANSCRIPT = "/home/user/.claude/projects/foo/transcript.jsonl"
REDIS_URL = "redis://localhost:6379"


@pytest.fixture
def fake_redis():
    server = fakeredis.FakeServer()
    r = fakeredis.FakeRedis(server=server, decode_responses=True)
    return r


def test_enqueue_returns_true(fake_redis):
    with patch("redis.from_url", return_value=fake_redis):
        result = producer.enqueue(TURN, SESSION, TRANSCRIPT, SourceTool.claude_code, REDIS_URL)
    assert result is True


def test_enqueue_writes_to_stream(fake_redis):
    with patch("redis.from_url", return_value=fake_redis):
        producer.enqueue(TURN, SESSION, TRANSCRIPT, SourceTool.claude_code, REDIS_URL)

    messages = fake_redis.xrange("vaultmind:turns")
    assert len(messages) == 1
    _, fields = messages[0]
    assert "data" in fields

    data = json.loads(fields["data"])
    qi = QueueItem.model_validate(data)
    assert qi.session_id == SESSION
    assert qi.source_tool == SourceTool.claude_code
    assert qi.turn_text.user == TURN.user
    assert qi.turn_text.assistant == TURN.assistant
    assert qi.transcript_path == TRANSCRIPT
    assert qi.turn_id.startswith(SESSION)


def test_enqueue_null_transcript(fake_redis):
    with patch("redis.from_url", return_value=fake_redis):
        result = producer.enqueue(TURN, SESSION, None, SourceTool.claude_code, REDIS_URL)
    assert result is True
    messages = fake_redis.xrange("vaultmind:turns")
    data = json.loads(messages[0][1]["data"])
    assert data["transcript_path"] is None


def test_enqueue_never_creates_consumer_group(fake_redis):
    with patch("redis.from_url", return_value=fake_redis):
        producer.enqueue(TURN, SESSION, TRANSCRIPT, SourceTool.claude_code, REDIS_URL)
    # If consumer group existed, xinfo_groups would return it
    try:
        groups = fake_redis.xinfo_groups("vaultmind:turns")
    except Exception:
        groups = []
    assert groups == []


def test_enqueue_returns_false_on_redis_error(capsys):
    with patch("redis.from_url", side_effect=Exception("connection refused")):
        result = producer.enqueue(TURN, SESSION, TRANSCRIPT, SourceTool.claude_code, REDIS_URL)
    assert result is False
    captured = capsys.readouterr()
    assert "connection refused" in captured.err


def test_each_enqueue_gets_unique_turn_id(fake_redis):
    with patch("redis.from_url", return_value=fake_redis):
        producer.enqueue(TURN, SESSION, TRANSCRIPT, SourceTool.claude_code, REDIS_URL)
        producer.enqueue(TURN, SESSION, TRANSCRIPT, SourceTool.claude_code, REDIS_URL)

    messages = fake_redis.xrange("vaultmind:turns")
    ids = [json.loads(m[1]["data"])["turn_id"] for m in messages]
    assert ids[0] != ids[1]
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_p1_producer.py -v
```

Expected: all fail — `cannot import name 'producer'`

- [ ] **Step 3: Implement `producer.py`**

Create `vaultmind/ingest/producer.py`:

```python
from __future__ import annotations

import sys
import uuid as _uuid
from datetime import datetime, timezone

import redis as _redis

from vaultmind.contracts import QueueItem, SourceTool, TurnText


def enqueue(
    turn_text: TurnText,
    session_id: str,
    transcript_path: str | None,
    source_tool: SourceTool,
    redis_url: str,
) -> bool:
    try:
        r = _redis.from_url(redis_url, decode_responses=True)
        qi = QueueItem(
            turn_id=f"{session_id}-{_uuid.uuid4().hex[:8]}",
            session_id=session_id,
            source_tool=source_tool,
            transcript_path=transcript_path,
            turn_text=turn_text,
            enqueued_at=datetime.now(timezone.utc).isoformat(),
        )
        r.xadd("vaultmind:turns", {"data": qi.model_dump_json()})
        return True
    except Exception as exc:
        sys.stderr.write(f"producer: failed to enqueue for session {session_id}: {exc}\n")
        return False
```

- [ ] **Step 4: Run tests — all pass**

```
pytest tests/test_p1_producer.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```
git add vaultmind/ingest/producer.py tests/test_p1_producer.py
git commit -m "feat(p1): producer — QueueItem builder + Redis XADD"
```

---

## Task 4: `session_state.py` — atomic SessionState.md writer

**Files:**
- Create: `vaultmind/ingest/session_state.py`
- Create: `tests/test_p1_session_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_p1_session_state.py`:

```python
import os
import threading
import time
import pytest
from pathlib import Path
from vaultmind.ingest import session_state


@pytest.fixture
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    v.mkdir()
    monkeypatch.setenv("VAULTMIND_VAULT_ROOT", str(v))
    return v


def _read_state(vault: Path) -> str:
    p = vault / "SessionState.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_turn_enqueued_appends_line(vault):
    session_state.turn_enqueued("sess-1", 2, [])
    content = _read_state(vault)
    assert "2 turn(s) enqueued" in content


def test_turn_enqueued_with_compaction_flag(vault):
    session_state.turn_enqueued("sess-1", 1, ["post-compaction"])
    content = _read_state(vault)
    assert "post-compaction" in content


def test_session_ended_appends_line(vault):
    session_state.session_ended("sess-1", "clear")
    content = _read_state(vault)
    assert "session ended" in content
    assert "clear" in content


def test_context_compacted_appends_line(vault):
    session_state.context_compacted("sess-1")
    content = _read_state(vault)
    assert "context compacted" in content


def test_multiple_appends_produce_multiple_lines(vault):
    session_state.turn_enqueued("sess-1", 1, [])
    session_state.session_ended("sess-1", "logout")
    lines = [l for l in _read_state(vault).strip().splitlines() if l.strip()]
    assert len(lines) == 2


def test_creates_file_if_absent(vault):
    assert not (vault / "SessionState.md").exists()
    session_state.turn_enqueued("sess-1", 1, [])
    assert (vault / "SessionState.md").exists()


def test_concurrent_appends_no_corruption(vault):
    errors = []

    def append(n):
        try:
            session_state.turn_enqueued(f"sess-{n}", 1, [])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=append, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    lines = [l for l in _read_state(vault).strip().splitlines() if l.strip()]
    assert len(lines) == 8


def test_stale_lock_is_stolen(vault, monkeypatch):
    # Write a lock file with a timestamp far in the past
    lock = vault.parent / ".vaultmind" / "session_state.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("stale", encoding="utf-8")

    # Patch time so the lock appears older than the timeout
    original_monotonic = time.monotonic
    call_count = [0]

    def fast_monotonic():
        call_count[0] += 1
        # Return a time well past the deadline on the second call
        return original_monotonic() + (11 if call_count[0] > 1 else 0)

    monkeypatch.setattr(time, "monotonic", fast_monotonic)

    # Should succeed (steal the lock) without raising
    session_state.turn_enqueued("sess-1", 1, [])
    assert "turn(s) enqueued" in _read_state(vault)
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_p1_session_state.py -v
```

Expected: all fail — `cannot import name 'session_state'`

- [ ] **Step 3: Implement `session_state.py`**

Create `vaultmind/ingest/session_state.py`:

```python
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


_LOCK_TIMEOUT = 10.0


def _vault_root() -> Path:
    return Path(os.environ.get("VAULTMIND_VAULT_ROOT", "./vault"))


def _session_state_path() -> Path:
    return _vault_root() / "SessionState.md"


def _lock_path() -> Path:
    return _vault_root().parent / ".vaultmind" / "session_state.lock"


def _acquire_lock() -> None:
    lock = _lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if time.monotonic() > deadline:
                lock.unlink(missing_ok=True)
                continue
            time.sleep(0.05)


def _release_lock() -> None:
    _lock_path().unlink(missing_ok=True)


def _append(line: str) -> None:
    _acquire_lock()
    try:
        p = _session_state_path()
        current = p.read_text(encoding="utf-8") if p.exists() else ""
        new_content = (current.rstrip("\n") + "\n" + line + "\n").lstrip("\n")
        tmp = p.with_suffix(".tmp")
        tmp.write_text(new_content, encoding="utf-8")
        os.replace(tmp, p)
    finally:
        _release_lock()


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def turn_enqueued(session_id: str, count: int, flags: list[str]) -> None:
    parts = [f"- {_ts()} · claude-code · {count} turn(s) enqueued"]
    if "post-compaction" in flags:
        parts.append("⚠ post-compaction")
    try:
        _append(" ".join(parts))
    except Exception as exc:
        sys.stderr.write(f"session_state: write failed: {exc}\n")


def session_ended(session_id: str, reason: str) -> None:
    try:
        _append(f"- {_ts()} · claude-code · session ended (reason: {reason})")
    except Exception as exc:
        sys.stderr.write(f"session_state: write failed: {exc}\n")


def context_compacted(session_id: str) -> None:
    try:
        _append(f"- {_ts()} · claude-code · ⚠ context compacted")
    except Exception as exc:
        sys.stderr.write(f"session_state: write failed: {exc}\n")
```

- [ ] **Step 4: Run tests — all pass**

```
pytest tests/test_p1_session_state.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```
git add vaultmind/ingest/session_state.py tests/test_p1_session_state.py
git commit -m "feat(p1): session_state — atomic SessionState.md append with lock"
```

---

## Task 5: Hook shims — `on_stop.py` and `on_session_end.py`

**Files:**
- Modify: `.vaultmind/hooks/on_stop.py` (replace stub)
- Modify: `.vaultmind/hooks/on_session_end.py` (replace stub)

No unit tests for the shims themselves — they are 15-line wrappers around already-tested modules. Integration is verified in Task 6.

- [ ] **Step 1: Replace `on_stop.py`**

Overwrite `.vaultmind/hooks/on_stop.py`:

```python
"""
.vaultmind/hooks/on_stop.py — Stop hook for Claude Code and Codex.

Called after every turn. Reads new turns from transcript, enqueues
to Redis, updates cursor. Always exits 0 — never blocks the session.
"""
from __future__ import annotations

import json
import os
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id      = payload.get("session_id", "unknown")
    transcript_path = payload.get("transcript_path")   # None on Codex
    redis_url       = os.environ.get("REDIS_URL", "redis://localhost:6379")

    try:
        from vaultmind.ingest import cursor as _cursor
        from vaultmind.ingest import reader as _reader
        from vaultmind.ingest import producer as _producer
        from vaultmind.ingest import session_state as _ss
        from vaultmind.contracts import SourceTool

        last_uuid = _cursor.load(session_id)
        turns, flags = _reader.parse(transcript_path, last_uuid)

        for t in turns:
            _producer.enqueue(
                t.turn_text, session_id, transcript_path,
                SourceTool.claude_code, redis_url,
            )

        if turns:
            _cursor.save(session_id, turns[-1].uuid)
            _ss.turn_enqueued(session_id, len(turns), flags)

    except Exception as exc:
        sys.stderr.write(f"on_stop.py: unexpected error: {exc}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Replace `on_session_end.py`**

Overwrite `.vaultmind/hooks/on_session_end.py`:

```python
"""
.vaultmind/hooks/on_session_end.py — SessionEnd hook for Claude Code.

Called when the Claude Code session ends. Logs the event to
SessionState.md. Always exits 0.
"""
from __future__ import annotations

import json
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id = payload.get("session_id", "unknown")
    reason     = payload.get("reason", "other")

    try:
        from vaultmind.ingest import session_state as _ss
        _ss.session_ended(session_id, reason)
    except Exception as exc:
        sys.stderr.write(f"on_session_end.py: unexpected error: {exc}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```
git add .vaultmind/hooks/on_stop.py .vaultmind/hooks/on_session_end.py
git commit -m "feat(p1): wire on_stop + on_session_end hook shims"
```

---

## Task 6: Hook config + .gitignore

**Files:**
- Create: `.claude/settings.json`
- Modify: `.gitignore`

- [ ] **Step 1: Create `.claude/settings.json`**

This registers the hooks with Claude Code. Check if the file already exists first:

```
ls .claude/
```

If `settings.json` exists, merge carefully. If not, create it:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python .vaultmind/hooks/on_stop.py",
            "async": true
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python .vaultmind/hooks/on_session_end.py",
            "async": true
          }
        ]
      }
    ]
  }
}
```

Note: use `python` not `python3` — this is Windows where `python3` is not available.

- [ ] **Step 2: Add cursors dir to .gitignore**

Open `.gitignore` and add at the end:

```
.vaultmind/cursors/
```

- [ ] **Step 3: Verify the hooks file is not gitignored**

```
git check-ignore -v .claude/settings.json
```

Expected: no output (not ignored). If it is ignored, remove the relevant rule from `.gitignore`.

- [ ] **Step 4: Commit**

```
git add .claude/settings.json .gitignore
git commit -m "feat(p1): register Claude Code hooks + gitignore cursors dir"
```

---

## Task 7: End-to-end smoke test

Verify the full pipeline: hook fires → QueueItem lands in Redis → watcher processes → node file written → SSE event on webapp.

- [ ] **Step 1: Confirm Redis is running**

```
python -c "import redis; r = redis.from_url('redis://localhost:6379', decode_responses=True); print(r.ping())"
```

Expected: `True`. If not, start Redis: `docker compose up -d`

- [ ] **Step 2: Start the watcher**

In a separate terminal (leave running):

```
python -m vaultmind.watcher
```

Expected output: `Watcher started — consumer=watcher-<pid>, vault=vault`

- [ ] **Step 3: Simulate a hook call**

Run this from the repo root to simulate what Claude Code sends to the Stop hook:

```python
python -c "
import json, sys, subprocess
payload = {
    'session_id': 'smoke-test-001',
    'transcript_path': None,
    'hook_event_name': 'Stop'
}
proc = subprocess.run(
    ['python', '.vaultmind/hooks/on_stop.py'],
    input=json.dumps(payload),
    text=True,
    capture_output=True
)
print('exit:', proc.returncode)
print('stderr:', proc.stderr)
"
```

Expected: `exit: 0`, stderr may say "producer: failed..." if Redis stream had no items yet — that's fine. Since `transcript_path` is None, reader returns empty and nothing is enqueued. This just confirms the hook exits 0 cleanly.

- [ ] **Step 4: Simulate with a real transcript**

```python
python -c "
import json, subprocess
from pathlib import Path

# Point at the actual current session transcript
import glob, os
project_dir = os.path.expanduser(r'~/.claude/projects/C--Users-Samson-Du-vault-mind')
transcripts = sorted(glob.glob(f'{project_dir}/*.jsonl'))
if not transcripts:
    print('No transcripts found')
    exit(1)

latest = transcripts[-1]
print('Using transcript:', latest)

# Get the session_id from the filename
session_id = Path(latest).stem

payload = {
    'session_id': session_id,
    'transcript_path': latest,
    'hook_event_name': 'Stop'
}
proc = subprocess.run(
    ['python', '.vaultmind/hooks/on_stop.py'],
    input=json.dumps(payload),
    text=True,
    capture_output=True,
    env={**__import__('os').environ, 'VAULTMIND_VAULT_ROOT': 'vault', 'REDIS_URL': 'redis://localhost:6379'}
)
print('exit:', proc.returncode)
print('stdout:', proc.stdout)
print('stderr:', proc.stderr)
"
```

- [ ] **Step 5: Confirm nodes were written**

```
ls vault/nodes/
```

Expected: one or more `.md` files with today's date prefix.

- [ ] **Step 6: Confirm SessionState.md updated**

```
cat vault/SessionState.md
```

Expected: one or more lines like `- 2026-06-21 HH:MM · claude-code · N turn(s) enqueued`

- [ ] **Step 7: Confirm Redis stream is draining**

```
python -c "
import redis
r = redis.from_url('redis://localhost:6379', decode_responses=True)
pending = r.xpending('vaultmind:turns', 'vaultmind-workers')
print('pending:', pending)
"
```

Expected: `pending_count: 0` (watcher ACKed all messages)

- [ ] **Step 8: Run all P1 tests together**

```
pytest tests/test_p1_cursor.py tests/test_p1_reader.py tests/test_p1_producer.py tests/test_p1_session_state.py -v
```

Expected: all pass

- [ ] **Step 9: Final commit**

```
git add vault/SessionState.md .vaultmind/cursors/ 2>/dev/null; true
git status
git commit -m "feat(p1): end-to-end smoke test passing — turns flow hook → Redis → vault"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** cursor ✓, reader (incremental + compaction) ✓, producer (XADD, no XGROUP) ✓, session_state (atomic + lock) ✓, on_stop ✓, on_session_end ✓, hook config ✓, gitignore ✓
- [x] **No placeholders:** all steps have real code, real commands, real expected output
- [x] **Type consistency:** `ParsedTurn.uuid` used in Task 2 matches `turns[-1].uuid` in Task 5; `turn_enqueued(session_id, count, flags)` signature consistent across Task 4 and Task 5; `reader.parse()` returns `(list[ParsedTurn], list[str])` throughout
- [x] **AC-3:** producer never calls XGROUP CREATE — verified in test `test_enqueue_never_creates_consumer_group`
- [x] **AC-6:** transcript_path=None handled — `test_returns_empty_for_none_path` + `test_enqueue_null_transcript`; hooks always exit 0; `python` (not `python3`) used in Windows
