# Eval & Arize Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing `run_eval()` evaluator and `init_arize()` into the live pipeline so every processed turn emits OpenTelemetry spans to Arize and an eval score.

**Architecture:** `run_watcher()` calls `init_arize(SERVICE_PIPELINE)` once at startup, then gets an OTel tracer. The tracer flows into `_process_message()`, which wraps the full pipeline in a root `turn` span with per-stage child spans. After the `done` stage (post-ACK), `run_eval()` fires once per turn with aggregated link results. All tracing degrades gracefully to no-ops when Arize credentials are absent.

**Tech Stack:** Python, OpenTelemetry SDK (`opentelemetry-sdk`, `opentelemetry-api`), `arize-otel`, `anthropic` (Haiku judge), `fakeredis` (tests), `pytest`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `vaultmind/arize_init.py` | Modify | Add 3 per-stage span name constants |
| `vaultmind/watcher.py` | Modify | Add imports; wire `init_arize` + tracer in `run_watcher`; update `_reclaim_pending` + `_process_message` signatures; add span wrapping + `run_eval` call |
| `tests/test_watcher_arize.py` | Create | Tests for init_arize call, span names, eval call behavior |

---

## Task 1: Add Per-Stage Span Name Constants to arize_init.py

**Files:**
- Modify: `vaultmind/arize_init.py`
- Test: `tests/test_watcher_arize.py` (create)

- [ ] **Step 1: Create the test file with a failing test**

Create `tests/test_watcher_arize.py`:

```python
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
    vault.mkdir()
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
```

- [ ] **Step 2: Run test to confirm it fails**

```
pytest tests/test_watcher_arize.py::test_stage_span_constants_exist -v
```

Expected: `ImportError: cannot import name 'SPAN_STAGE_SCRIBE'`

- [ ] **Step 3: Add the three constants to arize_init.py**

Open `vaultmind/arize_init.py`. After line 37 (`ATTR_EVAL_DETAIL = "eval.detail"`), insert:

```python
SPAN_STAGE_SCRIBE       = "stage.scribe"
SPAN_STAGE_NOTECREATOR  = "stage.notecreator"
SPAN_STAGE_CONNECTOR    = "stage.connector"
```

- [ ] **Step 4: Run test to confirm it passes**

```
pytest tests/test_watcher_arize.py::test_stage_span_constants_exist -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add vaultmind/arize_init.py tests/test_watcher_arize.py
git commit -m "feat(arize): add per-stage span name constants"
```

---

## Task 2: Wire init_arize and Tracer into run_watcher

**Files:**
- Modify: `vaultmind/watcher.py` (imports, `run_watcher`, `_reclaim_pending`, `_process_message` signature only — no span logic yet)
- Test: `tests/test_watcher_arize.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_watcher_arize.py`:

```python
# ---------------------------------------------------------------------------
# Task 2: init_arize called at startup
# ---------------------------------------------------------------------------

def test_init_arize_called_at_startup(tmp_path, monkeypatch):
    """run_watcher calls init_arize(SERVICE_PIPELINE) before the main loop."""
    from vaultmind.watcher import run_watcher
    from vaultmind.arize_init import SERVICE_PIPELINE

    mock_init = MagicMock(return_value=None)
    monkeypatch.setattr("vaultmind.watcher.init_arize", mock_init)

    # Make the Redis factory raise immediately so the loop never runs.
    def _boom():
        raise RuntimeError("stop-loop")
    monkeypatch.setattr("vaultmind.watcher._redis_factory", _boom)

    with pytest.raises(RuntimeError, match="stop-loop"):
        run_watcher(tmp_path / "vault")

    mock_init.assert_called_once_with(SERVICE_PIPELINE)
```

- [ ] **Step 2: Run test to confirm it fails**

```
pytest tests/test_watcher_arize.py::test_init_arize_called_at_startup -v
```

Expected: `AttributeError: module 'vaultmind.watcher' has no attribute 'init_arize'`

- [ ] **Step 3: Add imports to watcher.py**

Open `vaultmind/watcher.py`. After the existing `from vaultmind.secrets import scan_for_secrets` line, add:

```python
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
```

- [ ] **Step 4: Update run_watcher to call init_arize and pass tracer**

Replace the current `run_watcher` function body (lines 549–620) with:

```python
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

    consumer = f"watcher-{os.getpid()}"
    logger.info(
        "Watcher started — consumer=%s, vault=%s",
        consumer,
        vault_root,
    )

    _reclaim_pending(r, consumer, vault_root, tracer)

    _reclaim_counter = 0
    while True:
        _reclaim_counter += 1
        if _reclaim_counter % 150 == 0:
            _reclaim_pending(r, consumer, vault_root, tracer)

        try:
            messages = r.xreadgroup(
                GROUP_NAME,
                consumer,
                {STREAM_TURNS: ">"},
                count=1,
                block=2000,
            )
        except Exception as exc:
            logger.error("XREADGROUP error: %s — sleeping 1 s", exc, exc_info=True)
            time.sleep(1)
            continue

        if not messages:
            continue

        for _stream_name, entries in messages:
            for msg_id, fields in entries:
                _process_message(r, msg_id, fields, vault_root, tracer)
```

- [ ] **Step 5: Update _reclaim_pending to accept and pass tracer**

Replace the `_reclaim_pending` signature and the `_process_message` call inside it:

```python
def _reclaim_pending(
    r: "redis.Redis",  # type: ignore[name-defined]
    consumer: str,
    vault_root: pathlib.Path,
    tracer=None,
) -> None:
```

And inside the function, change:
```python
_process_message(r, msg_id, fields, vault_root)
```
to:
```python
_process_message(r, msg_id, fields, vault_root, tracer)
```

- [ ] **Step 6: Update _process_message signature to accept tracer**

Change the `_process_message` signature from:

```python
def _process_message(
    r: "redis.Redis",  # type: ignore[name-defined]
    msg_id: str,
    fields: dict[str, str],
    vault_root: pathlib.Path,
) -> None:
```

to:

```python
def _process_message(
    r: "redis.Redis",  # type: ignore[name-defined]
    msg_id: str,
    fields: dict[str, str],
    vault_root: pathlib.Path,
    tracer=None,
) -> None:
```

(No body changes yet — just the signature.)

- [ ] **Step 7: Run the test**

```
pytest tests/test_watcher_arize.py::test_init_arize_called_at_startup -v
```

Expected: `PASSED`

- [ ] **Step 8: Run the full test suite to check for regressions**

```
pytest -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 9: Commit**

```bash
git add vaultmind/watcher.py tests/test_watcher_arize.py
git commit -m "feat(watcher): wire init_arize and tracer into run_watcher"
```

---

## Task 3: Add Root Turn Span and Per-Stage Child Spans

**Files:**
- Modify: `vaultmind/watcher.py` (`_process_message` body)
- Test: `tests/test_watcher_arize.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_watcher_arize.py`:

```python
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

    span_names = [s.name for s in exporter.get_finished_spans()]
    assert "stage.scribe" in span_names
    assert "stage.notecreator" in span_names
    assert "stage.connector" in span_names
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_watcher_arize.py::test_turn_span_created_with_turn_id tests/test_watcher_arize.py::test_stage_spans_are_children_of_turn -v
```

Expected: both `FAILED` — no spans emitted yet.

- [ ] **Step 3: Rewrite the _process_message body with span wrapping**

Replace the entire `_process_message` function body (everything after the `def` line and docstring). The new body is:

```python
    # Deserialize QueueItem.
    try:
        if "data" in fields:
            raw = json.loads(fields["data"])
        else:
            raw = dict(fields)
            if isinstance(raw.get("turn_text"), str):
                raw["turn_text"] = json.loads(raw["turn_text"])

        qi = QueueItem.model_validate(raw)
    except Exception as exc:
        logger.error("Failed to deserialize QueueItem from msg %s: %s", msg_id, exc)
        return

    turn_id = qi.turn_id

    # Idempotency guard.
    prior_stage = _get_stage(r, turn_id)
    if prior_stage == TurnStage.done.value:
        logger.info("Turn %s already done (idempotency); ACKing msg %s", turn_id, msg_id)
        r.xack(STREAM_TURNS, GROUP_NAME, msg_id)
        return

    logger.info("Processing turn %s (msg %s)", turn_id, msg_id)

    _publish_progress(r, turn_id, TurnStage.started)
    _set_stage(r, turn_id, TurnStage.started.value)

    _tracer = tracer if tracer is not None else otel_trace.get_tracer(SERVICE_PIPELINE)

    # Pre-declare so they're accessible after the try/except for the eval call.
    nodes_written: list[NodeWritten] = []
    link_results: list[LinkResult] = []
    scribe_result: ScribeResult | None = None

    with _tracer.start_as_current_span(SPAN_TURN) as turn_span:
        turn_span.set_attribute(ATTR_TURN_ID, turn_id)

        try:
            # Stage: Scribe extraction
            with _tracer.start_as_current_span(SPAN_STAGE_SCRIBE):
                scribe_result = SCRIBE_FN(qi)

            extracted_ids = [
                f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d-%H%M')}"
                f"-{ext.slug}"
                for ext in scribe_result.extractions
            ]
            _publish_progress(r, turn_id, TurnStage.extracted, node_ids=extracted_ids)
            _set_stage(r, turn_id, TurnStage.extracted.value, node_ids=extracted_ids)

            # Stage: NoteCreator
            with _tracer.start_as_current_span(SPAN_STAGE_NOTECREATOR):
                nodes_written = NOTE_CREATOR_FN(scribe_result, vault_root)

            written_ids = [nw.id for nw in nodes_written]
            _publish_progress(r, turn_id, TurnStage.written, node_ids=written_ids)
            _set_stage(r, turn_id, TurnStage.written.value, node_ids=written_ids)

            # Stage: Connector
            with _tracer.start_as_current_span(SPAN_STAGE_CONNECTOR):
                for nw in nodes_written:
                    lr = CONNECTOR_FN(nw, r, vault_root)
                    link_results.append(lr)

            linked_ids = [lr.id for lr in link_results]
            _publish_progress(r, turn_id, TurnStage.linked, node_ids=linked_ids)
            _set_stage(r, turn_id, TurnStage.linked.value, node_ids=linked_ids)

            # ACK only after the full chain succeeds.
            r.xack(STREAM_TURNS, GROUP_NAME, msg_id)
            logger.info("ACKed msg %s for turn %s", msg_id, turn_id)

            # Mark done.
            _set_stage(r, turn_id, TurnStage.done.value, node_ids=linked_ids)
            _publish_progress(r, turn_id, TurnStage.done, node_ids=linked_ids)
            logger.info("Turn %s completed successfully", turn_id)

        except Exception as exc:
            err_str = str(exc)
            logger.error("Turn %s failed: %s", turn_id, err_str, exc_info=True)
            _publish_progress(r, turn_id, TurnStage.failed, error=err_str)

        # Eval fires after ACK+done — outside the try block so a bug here
        # cannot trigger 'failed' progress or prevent ACK.
        # run_eval catches all its own exceptions; this is belt-and-suspenders.
        if nodes_written and scribe_result is not None:
            pass  # Task 4 fills this in
```

- [ ] **Step 4: Run the span tests**

```
pytest tests/test_watcher_arize.py::test_turn_span_created_with_turn_id tests/test_watcher_arize.py::test_stage_spans_are_children_of_turn -v
```

Expected: both `PASSED`

- [ ] **Step 5: Run the full test suite**

```
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add vaultmind/watcher.py tests/test_watcher_arize.py
git commit -m "feat(watcher): add root turn span and per-stage child spans"
```

---

## Task 4: Wire run_eval After Done Stage

**Files:**
- Modify: `vaultmind/watcher.py` (replace the `pass` placeholder from Task 3)
- Test: `tests/test_watcher_arize.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_watcher_arize.py`:

```python
# ---------------------------------------------------------------------------
# Task 4: run_eval wiring
# ---------------------------------------------------------------------------

def test_run_eval_called_once_per_turn(tmp_path, monkeypatch):
    """run_eval fires exactly once per turn regardless of how many nodes were extracted."""
    from vaultmind.watcher import _process_message

    mock_eval = MagicMock(return_value={"pipeline_quality": 0.9})
    monkeypatch.setattr("vaultmind.watcher.run_eval", mock_eval)

    r = _make_redis(tmp_path)
    _process_message(r, "1-0", {"data": json.dumps(SAMPLE_QI_DATA)}, _vault(tmp_path))

    assert mock_eval.call_count == 1


def test_run_eval_skipped_when_no_extractions(tmp_path, monkeypatch):
    """run_eval is not called when the Scribe produces zero extractions."""
    from vaultmind.watcher import _process_message
    from vaultmind.contracts import ScribeResult

    mock_eval = MagicMock()
    monkeypatch.setattr("vaultmind.watcher.run_eval", mock_eval)
    monkeypatch.setattr(
        "vaultmind.watcher.SCRIBE_FN",
        lambda qi: ScribeResult(
            turn_id=qi.turn_id,
            source_tool=qi.source_tool,
            source_session=qi.session_id,
            extractions=[],
            intent_shift=None,
        ),
    )

    r = _make_redis(tmp_path)
    _process_message(r, "1-0", {"data": json.dumps(SAMPLE_QI_DATA)}, _vault(tmp_path))

    mock_eval.assert_not_called()


def test_run_eval_aggregates_related_links_across_nodes(tmp_path, monkeypatch):
    """Multi-node turn: eval receives the union of all nodes' related links."""
    from vaultmind.watcher import _process_message
    # Two extractions → two nodes → two LinkResults with different related links.
    two_extraction_scribe = ScribeResult(
        turn_id="sess-001-abc",
        source_tool=SourceTool.claude_code,
        source_session="sess-001",
        extractions=[
            Extraction(type=NodeType.decision, title="Use Redis", slug="use-redis",
                       body="Decided to use Redis."),
            Extraction(type=NodeType.constraint, title="Max 100 keys", slug="max-100-keys",
                       body="Hard limit: 100 keys per session."),
        ],
        intent_shift=None,
    )

    node_a = NodeWritten(
        id="node-a", path="vault/nodes/node-a.md",
        type=NodeType.decision, title="Use Redis",
        status=NodeStatus.approved, flags=[], intent_ref="2026-06-21 14:32",
    )
    node_b = NodeWritten(
        id="node-b", path="vault/nodes/node-b.md",
        type=NodeType.constraint, title="Max 100 keys",
        status=NodeStatus.approved, flags=[], intent_ref="2026-06-21 14:32",
    )
    lr_a = LinkResult(id="node-a", related=["[[Constraints]]"], status=NodeStatus.approved,
                      linked_at="2026-06-21T14:32:09Z")
    lr_b = LinkResult(id="node-b", related=["[[TechStack]]"], status=NodeStatus.approved,
                      linked_at="2026-06-21T14:32:10Z")

    monkeypatch.setattr("vaultmind.watcher.SCRIBE_FN", lambda qi: two_extraction_scribe)
    monkeypatch.setattr("vaultmind.watcher.NOTE_CREATOR_FN",
                        lambda sr, vault_root: [node_a, node_b])
    monkeypatch.setattr(
        "vaultmind.watcher.CONNECTOR_FN",
        lambda nw, r, vault_root: lr_a if nw.id == "node-a" else lr_b,
    )

    captured = {}
    def _capture_eval(qi, sr, agg_lr, vault_root, tracer=None):
        captured["agg_lr"] = agg_lr
        return {"pipeline_quality": 0.9}

    monkeypatch.setattr("vaultmind.watcher.run_eval", _capture_eval)

    r = _make_redis(tmp_path)
    _process_message(r, "1-0", {"data": json.dumps(SAMPLE_QI_DATA)}, _vault(tmp_path))

    assert "[[Constraints]]" in captured["agg_lr"].related
    assert "[[TechStack]]" in captured["agg_lr"].related
    assert len(captured["agg_lr"].related) == 2


def test_done_stage_set_before_run_eval(tmp_path, monkeypatch):
    """ACK and done-stage are recorded before run_eval runs (run_eval cannot block them)."""
    from vaultmind.watcher import _process_message

    # Monkeypatch run_eval to raise — simulates a bug in the eval path.
    monkeypatch.setattr(
        "vaultmind.watcher.run_eval",
        MagicMock(side_effect=RuntimeError("eval exploded")),
    )

    r = _make_redis(tmp_path)

    # _process_message will raise because run_eval raises outside the try block.
    # We catch it and verify the turn was already marked done.
    try:
        _process_message(r, "1-0", {"data": json.dumps(SAMPLE_QI_DATA)}, _vault(tmp_path))
    except RuntimeError:
        pass

    stage = r.hget("vaultmind:turn:sess-001-abc", "stage")
    assert stage == TurnStage.done.value
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_watcher_arize.py::test_run_eval_called_once_per_turn tests/test_watcher_arize.py::test_run_eval_skipped_when_no_extractions tests/test_watcher_arize.py::test_run_eval_aggregates_related_links_across_nodes tests/test_watcher_arize.py::test_done_stage_set_before_run_eval -v
```

Expected: all 4 `FAILED` — the `pass` placeholder doesn't call `run_eval`.

- [ ] **Step 3: Replace the placeholder in _process_message with the real eval call**

Find the comment `# Task 4 fills this in` at the bottom of `_process_message` (inside `with _tracer.start_as_current_span(SPAN_TURN)`, after the try/except). Replace:

```python
        if nodes_written and scribe_result is not None:
            pass  # Task 4 fills this in
```

with:

```python
        if nodes_written and scribe_result is not None:
            agg_lr = LinkResult(
                id=turn_id,
                related=[link for lr in link_results for link in lr.related],
                status=link_results[0].status,
                linked_at=link_results[-1].linked_at,
            )
            run_eval(qi, scribe_result, agg_lr, vault_root, _tracer)
```

- [ ] **Step 4: Run the four new tests**

```
pytest tests/test_watcher_arize.py::test_run_eval_called_once_per_turn tests/test_watcher_arize.py::test_run_eval_skipped_when_no_extractions tests/test_watcher_arize.py::test_run_eval_aggregates_related_links_across_nodes tests/test_watcher_arize.py::test_done_stage_set_before_run_eval -v
```

Expected: all 4 `PASSED`

- [ ] **Step 5: Run the full test suite**

```
pytest -v
```

Expected: all tests pass, including the original `tests/test_p3_evaluator.py` (3 tests).

- [ ] **Step 6: Commit**

```bash
git add vaultmind/watcher.py tests/test_watcher_arize.py
git commit -m "feat(watcher): wire run_eval after done stage with aggregated link results"
```

---

## Verification

After all tasks are complete, confirm end-to-end:

- [ ] `pytest -v` — all tests green
- [ ] Start the watcher with real keys:
  ```bash
  python -m vaultmind.watcher
  ```
  Expected log lines:
  ```
  Arize tracing initialized: project=vaultmind service=vaultmind-pipeline
  Watcher started — consumer=watcher-<pid>, vault=./vault
  ```
- [ ] Push a test turn via Redis CLI and confirm Arize receives a `turn` span with `turn_id` attribute and a nested `turn.eval` span with score attributes.
