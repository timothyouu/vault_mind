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
