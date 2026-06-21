"""
vaultmind/notecreator/__init__.py — Write AC-1 vault nodes + atomic IntentLog.

Public API:
    write_nodes(sr: ScribeResult, vault_root: Path) -> list[NodeWritten]
    atomic_write(path: Path, content: str) -> None          # imported by P4
    append_intentlog_entry(vault_root, intent_text, tool, origin) -> None
"""
from __future__ import annotations

import datetime
import logging
import os
import pathlib
import time

from vaultmind.contracts import (
    Extraction,
    NodeStatus,
    NodeType,
    NodeWritten,
    ScribeResult,
)
from vaultmind.secrets import scan_for_secrets

logger = logging.getLogger(__name__)

_LOCK_TIMEOUT = 10.0

_NODE_TEMPLATE = """\
---
id: {id}
type: {type}
title: "{title}"
created: {created}
source_tool: {source_tool}
source_session: {source_session}
intent_ref: {intent_ref}
status: approved
related: []
flags: {flags_yaml}
---
{body}
"""


# ---------------------------------------------------------------------------
# Atomic write utility (exported; P4 imports this)
# ---------------------------------------------------------------------------

def atomic_write(path: pathlib.Path, content: str) -> None:
    """Write content to path atomically via temp-then-rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# IntentLog append (atomic + lock)
# ---------------------------------------------------------------------------

def _lock_path(vault_root: pathlib.Path) -> pathlib.Path:
    return vault_root.parent / ".vaultmind" / "intentlog.lock"


def _acquire_intentlog_lock(vault_root: pathlib.Path) -> None:
    lock = _lock_path(vault_root)
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if time.monotonic() > deadline:
                lock.unlink(missing_ok=True)
            else:
                time.sleep(0.05)


def _release_intentlog_lock(vault_root: pathlib.Path) -> None:
    _lock_path(vault_root).unlink(missing_ok=True)


def append_intentlog_entry(
    vault_root: pathlib.Path,
    intent_text: str,
    tool: str,
    origin: str,
) -> None:
    """
    Prepend a new entry to IntentLog.md and mark it Current.
    Prior Current marker is stripped. Lock guards concurrent writes.

    origin must be 'developer' or 'ai-detected'.
    """
    intentlog = vault_root / "IntentLog.md"
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = f'## {ts} — Current\n"{intent_text}"\n— {tool} · {origin}\n'

    _acquire_intentlog_lock(vault_root)
    try:
        if intentlog.exists():
            existing = intentlog.read_text(encoding="utf-8")
            # Strip the "— Current" marker from the prior first heading
            existing = existing.replace(" — Current", "", 1)
            # Find the "# Session Intent Log" header
            lines = existing.splitlines(keepends=True)
            header_end = 0
            for i, line in enumerate(lines):
                if line.startswith("# Session Intent Log"):
                    header_end = i + 1
                    break
            # Skip blank lines after header
            while header_end < len(lines) and lines[header_end].strip() == "":
                header_end += 1
            rest_part = "".join(lines[header_end:])
            new_content = (
                "# Session Intent Log\n\n"
                + new_entry
                + "\n"
                + rest_part.lstrip("\n")
            )
        else:
            new_content = "# Session Intent Log\n\n" + new_entry

        atomic_write(intentlog, new_content)
        logger.info("IntentLog updated: %s", ts)
    finally:
        _release_intentlog_lock(vault_root)


# ---------------------------------------------------------------------------
# Node writer
# ---------------------------------------------------------------------------

def _current_intent_ref(vault_root: pathlib.Path) -> str:
    """Read the current IntentLog entry key (YYYY-MM-DD HH:MM), or use now."""
    intentlog = vault_root / "IntentLog.md"
    if intentlog.exists():
        content = intentlog.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("## ") and "— Current" in line:
                return line.replace("## ", "").replace(" — Current", "").strip()
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def write_nodes(sr: ScribeResult, vault_root: pathlib.Path) -> list[NodeWritten]:
    """
    Write one .md file per extraction in sr.extractions.
    Run write-time scanForSecrets on each node (flags but does NOT block).
    If sr.intent_shift is non-null, append to IntentLog as ai-detected.
    Returns list[NodeWritten] (empty if sr.extractions == []).
    """
    nodes_dir = vault_root / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    written: list[NodeWritten] = []
    now = datetime.datetime.now(datetime.timezone.utc)
    id_prefix = now.strftime("%Y-%m-%d-%H%M")
    created_iso = now.isoformat()
    intent_ref = _current_intent_ref(vault_root)

    for extraction in sr.extractions:
        node_id = f"{id_prefix}-{extraction.slug}"
        node_path = nodes_dir / f"{node_id}.md"
        safe_title = extraction.title.replace('"', '\\"')
        flags: list[str] = []
        flags_yaml = "[]"

        content = _NODE_TEMPLATE.format(
            id=node_id,
            type=extraction.type.value,
            title=safe_title,
            created=created_iso,
            source_tool=sr.source_tool.value,
            source_session=sr.source_session,
            intent_ref=intent_ref,
            flags_yaml="[]",
            body=extraction.body,
        )

        secret_matches = scan_for_secrets(content)
        if secret_matches:
            flags = ["secret-detected"]
            flags_yaml = '["secret-detected"]'
            content = _NODE_TEMPLATE.format(
                id=node_id,
                type=extraction.type.value,
                title=safe_title,
                created=created_iso,
                source_tool=sr.source_tool.value,
                source_session=sr.source_session,
                intent_ref=intent_ref,
                flags_yaml=flags_yaml,
                body=extraction.body,
            )
            logger.warning("Secret detected in node %s — flagged", node_id)

        atomic_write(node_path, content)
        logger.info("NoteCreator wrote node: %s", node_path)

        relative_path = node_path.relative_to(vault_root.parent)
        written.append(
            NodeWritten(
                id=node_id,
                path=str(relative_path),
                type=extraction.type,
                title=extraction.title,
                status=NodeStatus.approved,
                flags=flags,
                intent_ref=intent_ref,
            )
        )

    if sr.intent_shift:
        try:
            append_intentlog_entry(
                vault_root,
                intent_text=sr.intent_shift,
                tool=sr.source_tool.value,
                origin="ai-detected",
            )
            logger.info("IntentLog updated with ai-detected intent shift")
        except Exception as exc:
            logger.error("Failed to append intent shift to IntentLog: %s", exc)

    return written
