"""
tests/test_integration_session.py — P1 ingestion integration tests.

Exercises the full P1 path:
  Hook input → reader.parse() → cursor.load/save → producer.enqueue()
             → session_state updates

These tests verify the seams between the four P1 components as they operate
together in a single flow, catching issues that unit tests of each component
in isolation would miss:

  - reader.parse uses the saved cursor from cursor.load to skip processed turns.
  - New turns from reader.parse are enqueued by producer.enqueue.
  - session_state records each enqueue and session-end event.
  - cursor.save advances the cursor after each batch so the next invocation is
    incremental.
  - compaction flags flow from reader through session_state correctly.
  - Concurrent session_state appends from multiple simulated hooks don't corrupt
    the file.
"""
from __future__ import annotations

import json
import pathlib
import threading

import fakeredis
import pytest
from unittest.mock import patch

from vaultmind.ingest import cursor, producer, reader, session_state
from vaultmind.contracts import QueueItem, SourceTool, TurnText

FIXTURE_TRANSCRIPT = pathlib.Path(__file__).parent.parent / "fixtures" / "transcript.jsonl"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Set up VAULTMIND_VAULT_ROOT pointing at a fresh tmp vault."""
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("VAULTMIND_VAULT_ROOT", str(vault))
    return vault


@pytest.fixture
def fake_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


def _write_transcript(path: pathlib.Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


def _user(uuid: str, text: str, session: str = "sess-1") -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "promptSource": "typed",
        "message": {"role": "user", "content": text},
        "sessionId": session,
        "timestamp": "2026-06-21T10:00:00Z",
    }


def _assistant(uuid: str, text: str, session: str = "sess-1") -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
        "sessionId": session,
        "timestamp": "2026-06-21T10:01:00Z",
    }


def _compact_boundary(session: str = "sess-1") -> dict:
    return {"type": "system", "subtype": "compact_boundary", "sessionId": session}


# ===========================================================================
# 1. reader.parse + cursor integration
# ===========================================================================

class TestReaderCursorIntegration:
    """reader.parse uses cursor.load output to return only unprocessed turns."""

    def test_first_parse_returns_all_turns(
        self, env: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "First"),
            _assistant("a1", "R1"),
            _user("u2", "Second"),
            _assistant("a2", "R2"),
        ])
        # No cursor saved yet → load returns None
        last = cursor.load("sess-1")
        assert last is None
        turns, _ = reader.parse(str(t), last)
        assert len(turns) == 2

    def test_save_and_reload_cursor_skips_processed(
        self, env: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "First"),
            _assistant("a1", "R1"),
            _user("u2", "Second"),
            _assistant("a2", "R2"),
            _user("u3", "Third"),
            _assistant("a3", "R3"),
        ])
        # Simulate first run: process first two turns, save cursor at u2
        cursor.save("sess-1", "u2")

        # Second run: load cursor, parse only remaining turns
        last = cursor.load("sess-1")
        assert last == "u2"
        turns, _ = reader.parse(str(t), last)
        assert len(turns) == 1
        assert turns[0].uuid == "u3"

    def test_cursor_save_is_atomic(
        self, env: pathlib.Path
    ) -> None:
        """cursor.save must not leave a .tmp file behind."""
        cursor.save("sess-atom", "uuid-final")
        cursors_dir = env.parent / ".vaultmind" / "cursors"
        tmp_files = list(cursors_dir.glob("*.tmp"))
        assert tmp_files == [], f"Leftover tmp files: {tmp_files}"

    def test_cursor_advances_incrementally(
        self, env: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        """Three invocations each advance the cursor by one turn."""
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "T1"), _assistant("a1", "R1"),
            _user("u2", "T2"), _assistant("a2", "R2"),
            _user("u3", "T3"), _assistant("a3", "R3"),
        ])
        session = "sess-incr"

        # Each iteration: load cursor, parse (should get exactly 1 new turn),
        # save cursor at that turn's UUID, then move on.
        for expected_uuid in ["u1", "u2", "u3"]:
            last = cursor.load(session)
            turns, _ = reader.parse(str(t), last)
            # Filter to just the first unprocessed turn to simulate one-at-a-time
            # (reader returns all turns from cursor onward; we process one and advance)
            assert len(turns) >= 1
            assert turns[0].uuid == expected_uuid
            # Save cursor at the first new turn only, to simulate processing one at a time
            cursor.save(session, turns[0].uuid)

        # After processing all three, no more turns
        last = cursor.load(session)
        turns, _ = reader.parse(str(t), last)
        assert turns == []

    def test_compaction_flag_preserved_through_cursor(
        self, env: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        """post-compaction flag from reader is still present after cursor reload."""
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "Before"),
            _assistant("a1", "R1"),
            _compact_boundary(),
            _user("u2", "After compaction"),
            _assistant("a2", "R2"),
        ])
        cursor.save("sess-compact", "u1")
        last = cursor.load("sess-compact")
        turns, flags = reader.parse(str(t), last)
        assert len(turns) == 1
        assert turns[0].uuid == "u2"
        assert "post-compaction" in flags


# ===========================================================================
# 2. reader.parse + producer.enqueue integration
# ===========================================================================

class TestReaderProducerIntegration:
    """Turns from reader.parse are enqueued as valid QueueItems."""

    def test_turns_enqueued_match_transcript(
        self, env: pathlib.Path, tmp_path: pathlib.Path, fake_redis: fakeredis.FakeRedis
    ) -> None:
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "How does RLS work?"),
            _assistant("a1", "RLS enforces per-row access."),
        ])
        turns, _ = reader.parse(str(t), None)
        assert len(turns) == 1

        with patch("redis.from_url", return_value=fake_redis):
            ok = producer.enqueue(
                turns[0].turn_text,
                "sess-rp-001",
                str(t),
                SourceTool.claude_code,
                "redis://localhost:6379",
            )
        assert ok is True

        entries = fake_redis.xrange("vaultmind:turns")
        assert len(entries) == 1
        qi = QueueItem.model_validate(json.loads(entries[0][1]["data"]))
        assert qi.turn_text.user == "How does RLS work?"
        assert qi.turn_text.assistant == "RLS enforces per-row access."
        assert qi.transcript_path == str(t)

    def test_all_hook_turns_enqueued(
        self, env: pathlib.Path, tmp_path: pathlib.Path, fake_redis: fakeredis.FakeRedis
    ) -> None:
        """All turns from a hook-format transcript are parsed and enqueued."""
        t = tmp_path / "hook_tr.jsonl"
        # Hook transcript: 4 user/assistant pairs
        _write_transcript(t, [
            _user("u1", "Q1"), _assistant("a1", "A1"),
            _user("u2", "Q2"), _assistant("a2", "A2"),
            _user("u3", "Q3"), _assistant("a3", "A3"),
            _user("u4", "Q4"), _assistant("a4", "A4"),
        ])

        turns, _ = reader.parse(str(t), None)
        assert len(turns) == 4

        session = "sess-all-enq"
        with patch("redis.from_url", return_value=fake_redis):
            for turn in turns:
                producer.enqueue(
                    turn.turn_text, session, str(t),
                    SourceTool.claude_code, "redis://localhost:6379",
                )

        entries = fake_redis.xrange("vaultmind:turns")
        assert len(entries) == 4

    def test_incremental_enqueue_only_new_turns(
        self, env: pathlib.Path, tmp_path: pathlib.Path, fake_redis: fakeredis.FakeRedis
    ) -> None:
        """After saving a cursor, only unseen turns are enqueued on the next run."""
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "T1"), _assistant("a1", "R1"),
            _user("u2", "T2"), _assistant("a2", "R2"),
            _user("u3", "T3"), _assistant("a3", "R3"),
        ])
        session = "sess-incr-enq"

        # Run 1: enqueue all
        turns, _ = reader.parse(str(t), None)
        with patch("redis.from_url", return_value=fake_redis):
            for turn in turns:
                producer.enqueue(turn.turn_text, session, str(t),
                                 SourceTool.claude_code, "redis://localhost:6379")
        cursor.save(session, turns[-1].uuid)

        # Run 2: no new turns → nothing enqueued
        last = cursor.load(session)
        turns2, _ = reader.parse(str(t), last)
        assert turns2 == []
        count_before = len(fake_redis.xrange("vaultmind:turns"))

        with patch("redis.from_url", return_value=fake_redis):
            for turn in turns2:
                producer.enqueue(turn.turn_text, session, str(t),
                                 SourceTool.claude_code, "redis://localhost:6379")

        assert len(fake_redis.xrange("vaultmind:turns")) == count_before

    def test_turn_id_unique_per_enqueue(
        self, env: pathlib.Path, tmp_path: pathlib.Path, fake_redis: fakeredis.FakeRedis
    ) -> None:
        """Each enqueue produces a unique turn_id even for the same session."""
        turn = TurnText(user="Same question", assistant="Same answer")
        session = "sess-uid"
        with patch("redis.from_url", return_value=fake_redis):
            for _ in range(3):
                producer.enqueue(turn, session, None, SourceTool.claude_code, "redis://localhost")

        ids = [
            json.loads(fields["data"])["turn_id"]
            for _, fields in fake_redis.xrange("vaultmind:turns")
        ]
        assert len(set(ids)) == 3, f"Expected 3 unique turn_ids, got: {ids}"


# ===========================================================================
# 3. session_state integration
# ===========================================================================

class TestSessionStateIntegration:
    """session_state.turn_enqueued and session_ended record correctly."""

    def test_turn_enqueued_creates_session_state_file(
        self, env: pathlib.Path
    ) -> None:
        assert not (env / "SessionState.md").exists()
        session_state.turn_enqueued("sess-ss-001", 1, [])
        assert (env / "SessionState.md").exists()

    def test_enqueue_then_session_end_both_recorded(
        self, env: pathlib.Path
    ) -> None:
        session_state.turn_enqueued("sess-ss-002", 3, [])
        session_state.session_ended("sess-ss-002", "logout")
        content = (env / "SessionState.md").read_text()
        assert "turn(s) enqueued" in content
        assert "session ended" in content
        assert "logout" in content

    def test_compaction_flag_in_session_state(
        self, env: pathlib.Path
    ) -> None:
        session_state.turn_enqueued("sess-ss-003", 2, ["post-compaction"])
        content = (env / "SessionState.md").read_text()
        assert "post-compaction" in content

    def test_session_state_line_count_matches_events(
        self, env: pathlib.Path
    ) -> None:
        """Each call to turn_enqueued/session_ended appends exactly one line."""
        session_state.turn_enqueued("sess-ss-004", 1, [])
        session_state.turn_enqueued("sess-ss-004", 2, [])
        session_state.session_ended("sess-ss-004", "clear")
        session_state.context_compacted("sess-ss-004")

        lines = [
            l for l in (env / "SessionState.md").read_text().splitlines()
            if l.strip()
        ]
        assert len(lines) == 4

    def test_concurrent_session_state_writes_no_corruption(
        self, env: pathlib.Path
    ) -> None:
        """Simulates multiple hooks firing simultaneously without corruption."""
        errors: list[Exception] = []

        def _write(i: int) -> None:
            try:
                session_state.turn_enqueued(f"sess-conc-{i}", 1, [])
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_write, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent writes raised: {errors}"
        lines = [
            l for l in (env / "SessionState.md").read_text().splitlines()
            if l.strip()
        ]
        assert len(lines) == 12


# ===========================================================================
# 4. Full P1 flow: transcript → parse → enqueue → session_state → cursor
# ===========================================================================

class TestFullP1Flow:
    """End-to-end P1 simulation across all four components."""

    def test_full_flow_first_run(
        self, env: pathlib.Path, tmp_path: pathlib.Path, fake_redis: fakeredis.FakeRedis
    ) -> None:
        """
        First run: parse all turns, enqueue each, record in session_state,
        save cursor at last processed UUID.
        """
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "Question about auth"),
            _assistant("a1", "Use Supabase RLS."),
            _user("u2", "Any constraints?"),
            _assistant("a2", "No PII in logs."),
        ])
        session = "sess-full-p1"

        # Step 1: Load cursor (first run → None)
        last = cursor.load(session)
        assert last is None

        # Step 2: Parse
        turns, flags = reader.parse(str(t), last)
        assert len(turns) == 2

        # Step 3: Enqueue each turn
        with patch("redis.from_url", return_value=fake_redis):
            for turn in turns:
                ok = producer.enqueue(
                    turn.turn_text, session, str(t),
                    SourceTool.claude_code, "redis://localhost:6379",
                )
                assert ok

        # Step 4: Record in session_state
        session_state.turn_enqueued(session, len(turns), flags)

        # Step 5: Save cursor
        cursor.save(session, turns[-1].uuid)

        # Verify
        entries = fake_redis.xrange("vaultmind:turns")
        assert len(entries) == 2

        ss = (env / "SessionState.md").read_text()
        assert "2 turn(s) enqueued" in ss

        assert cursor.load(session) == "u2"

    def test_full_flow_second_run_incremental(
        self, env: pathlib.Path, tmp_path: pathlib.Path, fake_redis: fakeredis.FakeRedis
    ) -> None:
        """
        Second run after cursor saved at u2: only u3 is new.
        """
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "T1"), _assistant("a1", "R1"),
            _user("u2", "T2"), _assistant("a2", "R2"),
            _user("u3", "T3 — new turn"), _assistant("a3", "R3"),
        ])
        session = "sess-full-incr"
        cursor.save(session, "u2")

        last = cursor.load(session)
        turns, flags = reader.parse(str(t), last)
        assert len(turns) == 1
        assert turns[0].turn_text.user == "T3 — new turn"

        with patch("redis.from_url", return_value=fake_redis):
            for turn in turns:
                producer.enqueue(
                    turn.turn_text, session, str(t),
                    SourceTool.claude_code, "redis://localhost:6379",
                )
        session_state.turn_enqueued(session, len(turns), flags)
        cursor.save(session, turns[-1].uuid)

        entries = fake_redis.xrange("vaultmind:turns")
        assert len(entries) == 1

        ss = (env / "SessionState.md").read_text()
        assert "1 turn(s) enqueued" in ss
        assert cursor.load(session) == "u3"

    def test_full_flow_with_compaction(
        self, env: pathlib.Path, tmp_path: pathlib.Path, fake_redis: fakeredis.FakeRedis
    ) -> None:
        """
        A compact_boundary in the transcript sets the post-compaction flag in
        both reader output and session_state.
        """
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "Before compaction"),
            _assistant("a1", "R1"),
            _compact_boundary(),
            _user("u2", "After compaction"),
            _assistant("a2", "R2"),
        ])
        session = "sess-compact-full"

        last = cursor.load(session)
        turns, flags = reader.parse(str(t), last)
        assert "post-compaction" in flags

        with patch("redis.from_url", return_value=fake_redis):
            for turn in turns:
                producer.enqueue(
                    turn.turn_text, session, str(t),
                    SourceTool.claude_code, "redis://localhost:6379",
                )
        session_state.turn_enqueued(session, len(turns), flags)

        ss = (env / "SessionState.md").read_text()
        assert "post-compaction" in ss

    def test_full_flow_session_end(
        self, env: pathlib.Path, tmp_path: pathlib.Path, fake_redis: fakeredis.FakeRedis
    ) -> None:
        """
        After processing all turns, session_ended records the reason; cursor
        remains at last processed UUID.
        """
        t = tmp_path / "tr.jsonl"
        _write_transcript(t, [
            _user("u1", "Final question"),
            _assistant("a1", "Final answer"),
        ])
        session = "sess-end-full"

        turns, flags = reader.parse(str(t), None)
        with patch("redis.from_url", return_value=fake_redis):
            for turn in turns:
                producer.enqueue(
                    turn.turn_text, session, str(t),
                    SourceTool.claude_code, "redis://localhost:6379",
                )
        cursor.save(session, turns[-1].uuid)
        session_state.session_ended(session, "clear")

        ss = (env / "SessionState.md").read_text()
        assert "session ended" in ss
        assert "clear" in ss
        assert cursor.load(session) == "u1"

    def test_fixture_queue_items_full_flow(
        self, env: pathlib.Path, fake_redis: fakeredis.FakeRedis
    ) -> None:
        """
        The fixture transcript.jsonl holds pre-built QueueItems (not hook JSONL).
        Enqueue all four directly via xadd, verifying the fixture round-trips cleanly.
        """
        lines = FIXTURE_TRANSCRIPT.read_text().strip().splitlines()
        qis = [QueueItem.model_validate(json.loads(l)) for l in lines]
        assert len(qis) == 4

        session = qis[0].session_id

        with patch("redis.from_url", return_value=fake_redis):
            for qi in qis:
                ok = producer.enqueue(
                    qi.turn_text, qi.session_id, qi.transcript_path,
                    qi.source_tool, "redis://localhost:6379",
                )
                assert ok

        session_state.turn_enqueued(session, len(qis), [])

        entries = fake_redis.xrange("vaultmind:turns")
        assert len(entries) == 4

        # Verify the queue items are valid QueueItems
        for _, fields in entries:
            qi_back = QueueItem.model_validate(json.loads(fields["data"]))
            assert qi_back.session_id == session
            assert qi_back.source_tool == SourceTool.claude_code
            assert qi_back.turn_text.user
