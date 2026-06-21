import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from vaultmind.contracts import (
    Extraction, LinkResult, NodeStatus, NodeType, QueueItem, ScribeResult, SourceTool, TurnText
)
from vaultmind.evals import run_eval

FIXTURE_VAULT = Path(__file__).parent.parent / "fixtures" / "vault"

SAMPLE_QUEUE_ITEM = QueueItem(
    turn_id="sess-001-abc",
    source_tool=SourceTool.claude_code,
    session_id="sess-001",
    transcript_path=None,
    turn_text=TurnText(
        user="Let's use Supabase RLS for row-level auth",
        assistant="Good idea — RLS is the single source of truth for authz."
    ),
    enqueued_at="2026-06-21T14:32:00Z",
)

SAMPLE_SCRIBE = ScribeResult(
    turn_id="sess-001-abc",
    source_tool=SourceTool.claude_code,
    source_session="sess-001",
    extractions=[
        Extraction(
            type=NodeType.decision,
            title="Use Supabase RLS for row-level auth",
            slug="supabase-rls-policies",
            body="Decided to enforce per-row access with Supabase RLS.",
        )
    ],
    intent_shift=None,
)

SAMPLE_LINK = LinkResult(
    id="2026-06-21-1432-supabase-rls-policies",
    related=["[[Constraints]]"],
    status=NodeStatus.approved,
    linked_at="2026-06-21T14:32:09Z",
)

MOCK_EVAL_RESPONSE = json.dumps({
    "recall": 0.9,
    "precision": 1.0,
    "extraction_quality": 0.947,
    "link_relevance": 0.8,
    "grounding": 1.0,
    "pipeline_quality": 0.88,
    "missed": [],
    "spurious": [],
    "bad_links": []
})


def _make_mock_client():
    mock_content = MagicMock()
    mock_content.text = MOCK_EVAL_RESPONSE
    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


def test_run_eval_returns_scores(monkeypatch, tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    mock_client = _make_mock_client()
    monkeypatch.setattr("vaultmind.evals._get_client", lambda: mock_client)

    result = run_eval(SAMPLE_QUEUE_ITEM, SAMPLE_SCRIBE, SAMPLE_LINK, vault)

    assert result["recall"] == 0.9
    assert result["precision"] == 1.0
    assert result["pipeline_quality"] == 0.88
    assert result["missed"] == []


def test_run_eval_uses_haiku_model(monkeypatch, tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    mock_client = _make_mock_client()
    monkeypatch.setattr("vaultmind.evals._get_client", lambda: mock_client)

    run_eval(SAMPLE_QUEUE_ITEM, SAMPLE_SCRIBE, SAMPLE_LINK, vault)

    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"


def test_run_eval_handles_malformed_response(monkeypatch, tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    mock_content = MagicMock()
    mock_content.text = "NOT JSON"
    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    monkeypatch.setattr("vaultmind.evals._get_client", lambda: mock_client)

    result = run_eval(SAMPLE_QUEUE_ITEM, SAMPLE_SCRIBE, SAMPLE_LINK, vault)
    # Should return a zero-scored result rather than raising
    assert result["pipeline_quality"] == 0.0
