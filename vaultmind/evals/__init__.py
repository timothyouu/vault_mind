"""
vaultmind/evals/__init__.py — End-to-end pipeline evaluator (AC-4b).

Public API:
    run_eval(qi, sr, lr, vault_root, tracer=None) -> dict

Fires after each turn's 'done' stage as a child Arize span 'turn.eval'.
Uses claude-haiku-4-5-20251001. Read-only, fire-and-forget.
Prompt loaded from vaultmind/evals/pipeline_eval_prompt.md via importlib.resources.
"""
from __future__ import annotations

import importlib.resources
import json
import logging
import os
import pathlib
from typing import Any

from vaultmind.contracts import LinkResult, QueueItem, ScribeResult
from vaultmind.arize_init import (
    ATTR_EVAL_DETAIL,
    ATTR_EVAL_EXTRACTION_Q,
    ATTR_EVAL_GROUNDING,
    ATTR_EVAL_LINK_RELEVANCE,
    ATTR_EVAL_PIPELINE_Q,
    ATTR_EVAL_PRECISION,
    ATTR_EVAL_RECALL,
    SPAN_TURN_EVAL,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 512
_client = None

_ZERO_RESULT: dict = {
    "recall": 0.0,
    "precision": 0.0,
    "extraction_quality": 0.0,
    "link_relevance": 0.0,
    "grounding": 0.0,
    "pipeline_quality": 0.0,
    "missed": [],
    "spurious": [],
    "bad_links": [],
}


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — required for the evaluator.")
    import anthropic
    _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _load_prompt() -> str:
    ref = importlib.resources.files("vaultmind.evals").joinpath("pipeline_eval_prompt.md")
    return ref.read_text(encoding="utf-8")


def _load_linked_node_contents(
    related: list[str],
    vault_root: pathlib.Path,
) -> list[dict]:
    """Read the bodies of linked nodes for grounding judgment."""
    nodes_dir = vault_root / "nodes"
    result = []
    for link in related:
        node_id = link.strip("[]").lstrip("[").rstrip("]")
        # Try nodes/ first, then scope anchors
        candidates = [
            nodes_dir / f"{node_id}.md",
            vault_root / f"{node_id}.md",
        ]
        for path in candidates:
            if path.exists():
                content = path.read_text(encoding="utf-8")
                # Extract body (after second ---)
                try:
                    body_start = content.index("---", 3) + 3
                    body = content[body_start:].strip()
                    fm_line = next(
                        (l for l in content[:body_start].splitlines() if l.startswith("title:")),
                        f"title: {node_id}"
                    )
                    title = fm_line.partition(":")[2].strip().strip('"')
                    result.append({"id": node_id, "title": title, "body": body})
                except ValueError:
                    pass
                break
    return result


def run_eval(
    qi: QueueItem,
    sr: ScribeResult,
    lr: LinkResult,
    vault_root: pathlib.Path,
    tracer: Any = None,
) -> dict:
    """
    Score the pipeline turn end-to-end. Returns the scores dict.
    If tracer is provided, logs scores as child span attributes.
    Always returns _ZERO_RESULT on any error (never raises).
    """
    try:
        client = _get_client()
        prompt = _load_prompt()

        linked_contents = _load_linked_node_contents(lr.related, vault_root)

        eval_input = {
            "turn_text": {
                "user": qi.turn_text.user,
                "assistant": qi.turn_text.assistant,
            },
            "extractions": [
                {"type": e.type.value, "title": e.title, "body": e.body}
                for e in sr.extractions
            ],
            "related_links": lr.related,
            "linked_node_contents": linked_contents,
        }

        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=prompt,
            messages=[{"role": "user", "content": json.dumps(eval_input)}],
        )
        raw = message.content[0].text
        scores = json.loads(raw)

    except Exception as exc:
        logger.warning("Evaluator failed for turn %s: %s", qi.turn_id, exc)
        return dict(_ZERO_RESULT)

    # Log to Arize if tracer is available
    if tracer is not None:
        try:
            from opentelemetry import trace
            with tracer.start_as_current_span(SPAN_TURN_EVAL) as span:
                span.set_attribute(ATTR_EVAL_RECALL, scores.get("recall", 0.0))
                span.set_attribute(ATTR_EVAL_PRECISION, scores.get("precision", 0.0))
                span.set_attribute(ATTR_EVAL_EXTRACTION_Q, scores.get("extraction_quality", 0.0))
                span.set_attribute(ATTR_EVAL_LINK_RELEVANCE, scores.get("link_relevance", 0.0))
                span.set_attribute(ATTR_EVAL_GROUNDING, scores.get("grounding", 0.0))
                span.set_attribute(ATTR_EVAL_PIPELINE_Q, scores.get("pipeline_quality", 0.0))
                span.set_attribute(
                    ATTR_EVAL_DETAIL,
                    json.dumps({
                        "missed": scores.get("missed", []),
                        "spurious": scores.get("spurious", []),
                        "bad_links": scores.get("bad_links", []),
                    })
                )
        except Exception as exc:
            logger.warning("Arize span logging failed: %s", exc)

    return scores
