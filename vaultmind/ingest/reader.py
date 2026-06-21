from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from vaultmind.contracts import TurnText


@dataclass
class ParsedTurn:
    turn_text: TurnText
    uuid: str


def _extract_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return ""


def parse(
    transcript_path: str | None,
    last_uuid: str | None,
) -> tuple[list[ParsedTurn], list[str]]:
    if transcript_path is None:
        return [], []

    path = Path(transcript_path)
    if not path.exists():
        return [], []

    entries: list[dict] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return [], []

    # Skip everything up to and including last_uuid
    start = 0
    if last_uuid is not None:
        for i, entry in enumerate(entries):
            if entry.get("uuid") == last_uuid:
                start = i + 1
                break

    new_entries = entries[start:]

    turns: list[ParsedTurn] = []
    flags: list[str] = []
    post_compaction = False

    i = 0
    while i < len(new_entries):
        entry = new_entries[i]

        if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
            post_compaction = True
            i += 1
            continue

        if entry.get("type") == "user" and entry.get("promptSource") == "typed":
            user_text = _extract_text(entry.get("message", {}).get("content", ""))
            user_uuid = entry.get("uuid", "")

            # Find the next assistant entry
            assistant_text = ""
            j = i + 1
            while j < len(new_entries):
                nxt = new_entries[j]
                if nxt.get("type") == "assistant":
                    assistant_text = _extract_text(
                        nxt.get("message", {}).get("content", [])
                    )
                    break
                j += 1

            turns.append(
                ParsedTurn(
                    turn_text=TurnText(user=user_text, assistant=assistant_text),
                    uuid=user_uuid,
                )
            )
            if post_compaction and "post-compaction" not in flags:
                flags.append("post-compaction")

        i += 1

    return turns, flags
