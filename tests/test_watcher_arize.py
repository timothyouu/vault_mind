import json
import pytest
import fakeredis
from pathlib import Path
from unittest.mock import MagicMock

from vaultmind.contracts import (
    Extraction, LinkResult, NodeStatus, NodeType, NodeWritten,
    QueueItem, ScribeResult, SourceTool, TurnText, TurnStage,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_QI_DATA = {
    "turn_id": "sess-001-abc",
    "source_tool": "claude-code",
    "session_id": "sess-001",
    "transcript_path": None,
    "turn_text": {
        "user": "Should we use Redis or Kafka?",
        "assistant": "Redis is simpler for our scale.",
    },
    "enqueued_at": "2026-06-21T14:32:00Z",
}

SAMPLE_QI = QueueItem.model_validate(SAMPLE_QI_DATA)


def _make_redis(tmp_path: Path) -> fakeredis.FakeRedis:
    r = fakeredis.FakeRedis(decode_responses=True)
    r.xgroup_create("vaultmind:turns", "vaultmind-workers", id="0", mkstream=True)
    return r


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    return vault


# ---------------------------------------------------------------------------
# Task 1: span name constants
# ---------------------------------------------------------------------------

def test_stage_span_constants_exist():
    from vaultmind.arize_init import (
        SPAN_STAGE_SCRIBE,
        SPAN_STAGE_NOTECREATOR,
        SPAN_STAGE_CONNECTOR,
    )
    assert SPAN_STAGE_SCRIBE == "stage.scribe"
    assert SPAN_STAGE_NOTECREATOR == "stage.notecreator"
    assert SPAN_STAGE_CONNECTOR == "stage.connector"
