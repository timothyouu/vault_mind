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
