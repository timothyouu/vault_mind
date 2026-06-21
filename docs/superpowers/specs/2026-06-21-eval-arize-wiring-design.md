# Eval & Arize Wiring Design

**Date:** 2026-06-21  
**Scope:** Wire the existing `run_eval()` evaluator and `init_arize()` into the live pipeline (`watcher.py`). No changes to contracts, evals, or arize_init.

---

## Problem

`vaultmind/evals/__init__.py` and `vaultmind/arize_init.py` are fully implemented and tested, but never called by the pipeline. Every turn completes without emitting a trace or eval score.

---

## Goals

- Arize receives one root `turn` span per processed message, with `turn_id` as an attribute.
- Each pipeline stage (scribe, notecreator, connector, eval) appears as a child span inside that root.
- After the `done` stage, `run_eval()` fires once per turn and logs scores to Arize as a `turn.eval` child span.
- If Arize credentials are absent, all tracing is silently disabled and the pipeline is unaffected.

---

## Architecture

### 1. Arize init at watcher startup

`run_watcher()` calls `init_arize(SERVICE_PIPELINE)` once before the loop. If credentials are set, this registers an OTel tracer provider globally. We then unconditionally get a tracer:

```python
from opentelemetry import trace as otel_trace
init_arize(SERVICE_PIPELINE)  # registers global provider if credentials available
tracer = otel_trace.get_tracer(SERVICE_PIPELINE)  # no-op tracer if Arize not registered
```

`opentelemetry-api` is a required dep so the import always succeeds. When Arize is not configured, `get_tracer()` returns OTel's built-in no-op — `start_as_current_span()` is always safe to call with no credential guards needed in `_process_message`.

### 2. Root `turn` span per message

`_process_message` gains an optional `tracer=None` parameter. The entire pipeline body is wrapped:

```python
with tracer.start_as_current_span(SPAN_TURN) as span:
    span.set_attribute(ATTR_TURN_ID, turn_id)
    # ... existing pipeline stages ...
```

The tracer is passed from `run_watcher` → `_process_message`. `_reclaim_pending` also passes it through for reclaimed messages.

### 3. Per-stage child spans

Inside the root span, each stage gets its own child:

| Stage | Span name |
|---|---|
| Scribe extraction | `"stage.scribe"` |
| NoteCreator write | `"stage.notecreator"` |
| Connector link | `"stage.connector"` |
| Evaluator | `SPAN_TURN_EVAL` (`"turn.eval"`) |

Stage span names (`"stage.scribe"` etc.) are added as constants to `arize_init.py`.

### 4. Eval call — once per turn

After the `linked` stage and before `done`, `run_eval()` is called once with aggregated turn-level data:

```python
from vaultmind.evals import run_eval

agg_lr = LinkResult(
    id=turn_id,
    related=[link for lr in link_results for link in lr.related],
    status=link_results[0].status if link_results else NodeStatus.approved,
    linked_at=link_results[-1].linked_at if link_results else now_iso,
)
run_eval(qi, scribe_result, agg_lr, vault_root, tracer)
```

`run_eval` already handles the `turn.eval` child span internally (using the current OTel context), so no additional span management is needed at the call site. It always returns silently on failure — never raises.

If `nodes_written` is empty (no extractions), `run_eval` is skipped.

---

## Files changed

| File | Change |
|---|---|
| `vaultmind/watcher.py` | `run_watcher()`: call `init_arize` + get tracer; pass tracer to `_process_message` and `_reclaim_pending`. `_process_message`: root `turn` span, per-stage child spans, aggregated `run_eval()` call after `linked`. |
| `vaultmind/arize_init.py` | Add `SPAN_STAGE_SCRIBE`, `SPAN_STAGE_NOTECREATOR`, `SPAN_STAGE_CONNECTOR` constants. |

All other files (`contracts.py`, `evals/__init__.py`, test files) are untouched.

---

## No-op / graceful degradation

- `init_arize()` already returns `None` when credentials are absent and logs a warning.
- If `provider` is `None`, we use OTel's built-in no-op tracer (`trace.get_tracer()` on an un-configured provider returns a no-op). No conditional guards needed in `_process_message`.
- `run_eval()` already catches all exceptions and returns zero scores — pipeline ACK is never blocked.

---

## Packages

Already declared in `pyproject.toml`:
- `arize-otel>=0.0.1`
- `opentelemetry-api>=1.20`
- `opentelemetry-sdk>=1.20`

Ensure installed: `pip install -e .[dev]`

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `ARIZE_SPACE_KEY` | For Arize | Space key from Arize dashboard |
| `ARIZE_API_KEY` | For Arize | API key from Arize dashboard |
| `ANTHROPIC_API_KEY` | For eval | Powers the Haiku judge in `run_eval()` |
| `VAULTMIND_ARIZE_REQUIRED` | Optional | Set to `1` to make missing keys a hard error |

---

## Testing

Existing `tests/test_p3_evaluator.py` (3 tests) continues to pass unchanged — it tests `run_eval()` in isolation.

New tests to add in `tests/test_watcher_arize.py`:
- Arize init is called once at watcher startup with `SERVICE_PIPELINE`.
- `run_eval` is called once per turn (not per node) after the `linked` stage.
- `run_eval` is skipped when `nodes_written` is empty.
- Pipeline still ACKs and sets `done` when `run_eval` raises (simulated failure).
- Multi-node turn: `run_eval` receives aggregated `related` list combining all nodes.
