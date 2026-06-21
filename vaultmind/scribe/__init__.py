"""
vaultmind/scribe/__init__.py — LLM-powered extraction of knowledge nodes.

Public API:
    extract(queue_item: QueueItem) -> ScribeResult

Uses claude-sonnet-4-6 via the Anthropic SDK. Reads ANTHROPIC_API_KEY from env.
Loads the system prompt from vaultmind/scribe/prompt.md via importlib.resources.
Returns ScribeResult with extractions=[] when nothing noteworthy is found.
"""
from __future__ import annotations

import importlib.resources
import json
import logging
import os
from typing import Any

from vaultmind.contracts import (
    Extraction,
    NodeType,
    QueueItem,
    ScribeResult,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1024
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set — required for the Scribe. "
            "Set it in your environment or .env.local file."
        )
    import anthropic
    _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _load_prompt() -> str:
    ref = importlib.resources.files("vaultmind.scribe").joinpath("prompt.md")
    return ref.read_text(encoding="utf-8")


def _parse_response(raw: str, turn_id: str, session_id: str, source_tool) -> ScribeResult:
    try:
        data = json.loads(raw)
        extractions = [
            Extraction(
                type=NodeType(e["type"]),
                title=e["title"],
                slug=e["slug"],
                body=e["body"],
            )
            for e in data.get("extractions", [])
        ]
        intent_shift = data.get("intent_shift") or None
        return ScribeResult(
            turn_id=turn_id,
            source_tool=source_tool,
            source_session=session_id,
            extractions=extractions,
            intent_shift=intent_shift,
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("Scribe: failed to parse LLM response (%s); returning empty result.", exc)
        return ScribeResult(
            turn_id=turn_id,
            source_tool=source_tool,
            source_session=session_id,
            extractions=[],
            intent_shift=None,
        )


def extract(qi: QueueItem) -> ScribeResult:
    """
    Extract knowledge nodes from a QueueItem's turn_text using Claude.

    Returns ScribeResult with extractions=[] if nothing noteworthy is found,
    or if the API call fails (logged as warning, never raises in the hot path).
    """
    client = _get_client()
    prompt = _load_prompt()

    user_content = json.dumps({
        "user": qi.turn_text.user,
        "assistant": qi.turn_text.assistant,
    })

    try:
        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = message.content[0].text
        return _parse_response(raw, qi.turn_id, qi.session_id, qi.source_tool)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("Scribe: API call failed for turn %s: %s", qi.turn_id, exc)
        return ScribeResult(
            turn_id=qi.turn_id,
            source_tool=qi.source_tool,
            source_session=qi.session_id,
            extractions=[],
            intent_shift=None,
        )
