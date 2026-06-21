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


# ---------------------------------------------------------------------------
# Task 2: init_arize called at startup
# ---------------------------------------------------------------------------

def test_init_arize_called_at_startup(tmp_path, monkeypatch):
    """run_watcher calls init_arize(SERVICE_PIPELINE) and get_tracer(SERVICE_PIPELINE) before Redis."""
    from opentelemetry import trace as otel_trace_module
    from vaultmind.watcher import run_watcher
    from vaultmind.arize_init import SERVICE_PIPELINE

    mock_init = MagicMock(return_value=None)
    monkeypatch.setattr("vaultmind.watcher.init_arize", mock_init)

    mock_get_tracer = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(otel_trace_module, "get_tracer", mock_get_tracer)

    # Make the Redis factory raise immediately so the loop never runs.
    def _boom():
        raise RuntimeError("stop-loop")
    monkeypatch.setattr("vaultmind.watcher._redis_factory", _boom)

    with pytest.raises(RuntimeError, match="stop-loop"):
        run_watcher(tmp_path / "vault")

    mock_init.assert_called_once_with(SERVICE_PIPELINE)
    mock_get_tracer.assert_called_once_with(SERVICE_PIPELINE)


# ---------------------------------------------------------------------------
# Task 3: span structure
# ---------------------------------------------------------------------------

def _make_tracer():
    """Return a (tracer, exporter) pair backed by an in-memory OTel provider."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def test_turn_span_created_with_turn_id(tmp_path):
    """A root 'turn' span is emitted for every processed message."""
    from vaultmind.watcher import _process_message

    tracer, exporter = _make_tracer()
    r = _make_redis(tmp_path)

    _process_message(r, "1-0", {"data": json.dumps(SAMPLE_QI_DATA)}, _vault(tmp_path), tracer)

    span_names = [s.name for s in exporter.get_finished_spans()]
    assert "turn" in span_names

    turn_span = next(s for s in exporter.get_finished_spans() if s.name == "turn")
    assert turn_span.attributes.get("turn_id") == "sess-001-abc"


def test_stage_spans_are_children_of_turn(tmp_path):
    """stage.scribe, stage.notecreator, stage.connector are child spans of 'turn'."""
    from vaultmind.watcher import _process_message

    tracer, exporter = _make_tracer()
    r = _make_redis(tmp_path)

    _process_message(r, "1-0", {"data": json.dumps(SAMPLE_QI_DATA)}, _vault(tmp_path), tracer)

    spans = exporter.get_finished_spans()
    span_names = [s.name for s in spans]
    assert "stage.scribe" in span_names
    assert "stage.notecreator" in span_names
    assert "stage.connector" in span_names

    turn_span = next(s for s in spans if s.name == "turn")
    for stage_name in ("stage.scribe", "stage.notecreator", "stage.connector"):
        stage_span = next(s for s in spans if s.name == stage_name)
        assert stage_span.parent is not None
        assert stage_span.parent.span_id == turn_span.context.span_id, \
            f"{stage_name} is not a child of 'turn'"
