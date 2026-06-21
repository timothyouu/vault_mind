import json
import pytest
from unittest.mock import patch, MagicMock
from vaultmind.contracts import QueueItem, SourceTool, TurnText
from vaultmind.scribe import extract


SAMPLE_TURN = QueueItem(
    turn_id="sess-001-abc12345",
    source_tool=SourceTool.claude_code,
    session_id="sess-001",
    transcript_path=None,
    turn_text=TurnText(
        user="Let's use Supabase RLS for row-level auth instead of checking in app code",
        assistant="Good call — RLS keeps the DB as the single source of truth for authz."
    ),
    enqueued_at="2026-06-21T14:32:00Z",
)

MOCK_RESPONSE_ONE_EXTRACTION = json.dumps({
    "extractions": [
        {
            "type": "decision",
            "title": "Use Supabase RLS for row-level auth",
            "slug": "supabase-rls-policies",
            "body": "Decided to enforce per-row access with Supabase RLS rather than app-level checks.\n\n> \"let's just do RLS so we don't re-check ownership in every endpoint\""
        }
    ],
    "intent_shift": None
})

MOCK_RESPONSE_EMPTY = json.dumps({
    "extractions": [],
    "intent_shift": None
})

MOCK_RESPONSE_INTENT_SHIFT = json.dumps({
    "extractions": [],
    "intent_shift": "Help me finish the auth flow"
})


def _make_mock_client(response_text: str):
    mock_content = MagicMock()
    mock_content.text = response_text
    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


def test_extract_returns_scribe_result(monkeypatch):
    mock_client = _make_mock_client(MOCK_RESPONSE_ONE_EXTRACTION)
    monkeypatch.setattr("vaultmind.scribe._get_client", lambda: mock_client)
    result = extract(SAMPLE_TURN)
    assert result.turn_id == SAMPLE_TURN.turn_id
    assert result.source_tool == SourceTool.claude_code
    assert result.source_session == "sess-001"
    assert len(result.extractions) == 1
    assert result.extractions[0].type.value == "decision"
    assert result.extractions[0].title == "Use Supabase RLS for row-level auth"
    assert result.extractions[0].slug == "supabase-rls-policies"
    assert result.intent_shift is None


def test_extract_empty_extractions(monkeypatch):
    mock_client = _make_mock_client(MOCK_RESPONSE_EMPTY)
    monkeypatch.setattr("vaultmind.scribe._get_client", lambda: mock_client)
    result = extract(SAMPLE_TURN)
    assert result.extractions == []
    assert result.intent_shift is None


def test_extract_intent_shift(monkeypatch):
    mock_client = _make_mock_client(MOCK_RESPONSE_INTENT_SHIFT)
    monkeypatch.setattr("vaultmind.scribe._get_client", lambda: mock_client)
    result = extract(SAMPLE_TURN)
    assert result.intent_shift == "Help me finish the auth flow"


def test_extract_raises_on_missing_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("vaultmind.scribe._get_client", side_effect=RuntimeError("ANTHROPIC_API_KEY not set")):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            extract(SAMPLE_TURN)


def test_extract_passes_correct_model(monkeypatch):
    mock_client = _make_mock_client(MOCK_RESPONSE_EMPTY)
    monkeypatch.setattr("vaultmind.scribe._get_client", lambda: mock_client)
    extract(SAMPLE_TURN)
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"


def test_extract_handles_malformed_json_gracefully(monkeypatch):
    mock_client = _make_mock_client("NOT JSON AT ALL")
    monkeypatch.setattr("vaultmind.scribe._get_client", lambda: mock_client)
    result = extract(SAMPLE_TURN)
    assert result.extractions == []
    assert result.intent_shift is None
