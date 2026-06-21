"""
vaultmind/connector/__init__.py — Heuristic linking + event publish.

Public API:
    link_node(nw: NodeWritten, r: redis.Redis, vault_root: Path) -> LinkResult
    reconcile_orphans(vault_root: Path, r: redis.Redis) -> None

Linking strategy (heuristic-first, vector as enhancement):
  1. Always consider scope anchors (Constraints, ProjectGoal, TechStack).
  2. Keyword overlap between new node title and existing node titles.
  3. Type compatibility (decision↔constraint, question↔decision).
  4. VaultMemory semantic search if available.
  5. Same intent_ref grouping (lower weight).

Invariant: ONLY the `related:` frontmatter field is ever written.
           The body is never touched (tested in test_p3_connector.py).
"""
from __future__ import annotations

import datetime
import json
import logging
import pathlib
import re
from typing import TYPE_CHECKING

from vaultmind.contracts import (
    LinkResult,
    NodeChangedEventType,
    NodeStatus,
    NodeWritten,
)

if TYPE_CHECKING:
    import redis as _redis_module

logger = logging.getLogger(__name__)

CHANNEL_EVENTS = "vaultmind:events"

SCOPE_ANCHORS = ["Constraints", "ProjectGoal", "TechStack"]

# Type-compatibility map: which anchor to prefer per node type
_TYPE_ANCHOR = {
    "decision": ["Constraints"],
    "constraint": ["Constraints"],
    "goal": ["ProjectGoal", "TechStack"],
    "question": ["Constraints"],
}


def _parse_frontmatter(content: str) -> dict:
    """Parse YAML-ish frontmatter into a dict (simple key: value only)."""
    if not content.startswith("---"):
        return {}
    end = content.index("---", 3)
    fm_block = content[3:end].strip()
    result: dict = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _set_related(content: str, related: list[str]) -> str:
    """
    Replace the `related:` block in YAML frontmatter.
    Handles both `related: []` (single line) and multi-line forms.
    Only edits within the first `--- ... ---` block.
    """
    if not related:
        return content

    # Build the new related block
    lines_yaml = "\n".join(f'  - "{r}"' for r in related)
    new_related = f"related:\n{lines_yaml}"

    # Find frontmatter boundaries
    fm_start = content.index("---") + 3
    fm_end = content.index("---", fm_start)
    fm_block = content[fm_start:fm_end]

    # Replace the related field (single-line or multi-line)
    # Match "related:" plus everything until the next top-level key or end
    fm_new = re.sub(
        r"related:.*?(?=\n\w|\Z)",
        new_related,
        fm_block,
        flags=re.DOTALL,
    )
    return content[:fm_start] + fm_new + content[fm_end:]


def _load_existing_nodes(vault_root: pathlib.Path) -> list[dict]:
    """Load all existing nodes, returning list of {id, title, type, intent_ref, path}."""
    nodes_dir = vault_root / "nodes"
    if not nodes_dir.exists():
        return []
    nodes = []
    for md_file in nodes_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            fm = _parse_frontmatter(content)
            nodes.append({
                "id": fm.get("id", md_file.stem),
                "title": fm.get("title", "").strip('"'),
                "type": fm.get("type", ""),
                "intent_ref": fm.get("intent_ref", ""),
                "path": md_file,
            })
        except Exception:
            pass
    return nodes


def _title_keywords(title: str) -> set[str]:
    """Extract meaningful words from a title for overlap scoring."""
    stop = {"use", "the", "a", "an", "for", "to", "of", "in", "and", "or", "is", "it"}
    return {w.lower() for w in re.findall(r"\w+", title)} - stop


def _score_overlap(title_a: str, title_b: str) -> float:
    """Jaccard similarity of keyword sets."""
    a = _title_keywords(title_a)
    b = _title_keywords(title_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _find_related(
    nw: NodeWritten,
    vault_root: pathlib.Path,
) -> list[str]:
    """
    Heuristic: find related wikilinks for a new node.
    Returns a list of [[wikilink]] strings, max 5.
    """
    candidates: list[tuple[float, str]] = []

    # 1. Scope anchors by type
    for anchor in _TYPE_ANCHOR.get(nw.type.value, []):
        anchor_path = vault_root / f"{anchor}.md"
        if anchor_path.exists():
            candidates.append((0.8, f"[[{anchor}]]"))

    # 2. Existing nodes — keyword overlap
    existing = _load_existing_nodes(vault_root)
    for node in existing:
        if node["id"] == nw.id:
            continue
        score = _score_overlap(nw.title, node["title"])
        if score > 0.2:
            candidates.append((score, f"[[{node['id']}]]"))

        # Type compatibility bonus
        if nw.type.value == "decision" and node["type"] == "constraint":
            candidates.append((0.5, f"[[{node['id']}]]"))
        elif nw.type.value == "question" and node["type"] == "decision":
            candidates.append((0.4, f"[[{node['id']}]]"))

    # 3. VaultMemory semantic search (enhancement — graceful if unavailable)
    try:
        from vaultmind.memory import VaultMemory
        mem = VaultMemory()
        results = mem.search(f"{nw.title}\n{nw.type.value}", k=3)
        for r in results:
            if r.node_id != nw.id and r.score > 0.5:
                candidates.append((r.score, f"[[{r.node_id}]]"))
    except Exception:
        pass

    # Deduplicate, sort by score, take top 5
    seen: set[str] = set()
    unique: list[tuple[float, str]] = []
    for score, link in sorted(candidates, reverse=True):
        if link not in seen:
            seen.add(link)
            unique.append((score, link))

    return [link for _, link in unique[:5]]


def link_node(
    nw: NodeWritten,
    r: "redis.Redis",
    vault_root: pathlib.Path,
) -> LinkResult:
    """
    Find related nodes for nw and write them to its frontmatter.
    Publishes NodeChangedEvent('linked') to vaultmind:events.
    Returns LinkResult.

    Invariant: only `related:` frontmatter is modified. Body is never touched.
    """
    # Resolve node file path
    _p = pathlib.Path(nw.path)
    node_path = _p if _p.is_absolute() else vault_root.parent / _p
    content = node_path.read_text(encoding="utf-8")

    related = _find_related(nw, vault_root)

    if related:
        new_content = _set_related(content, related)
        # Verify body invariant before writing
        body_start_orig = content.index("---", 3) + 3
        body_start_new = new_content.index("---", 3) + 3
        if content[body_start_orig:] != new_content[body_start_new:]:
            logger.error(
                "Connector: body changed for %s — aborting link write (BUG!)", nw.id
            )
        else:
            pathlib.Path(node_path).write_text(new_content, encoding="utf-8")
            logger.info("Connector linked %d nodes for %s", len(related), nw.id)
    else:
        logger.info("Connector: no related nodes found for %s", nw.id)

    # Publish event
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    r.publish(
        CHANNEL_EVENTS,
        json.dumps({"event": "linked", "id": nw.id, "ts": ts}),
    )

    return LinkResult(
        id=nw.id,
        related=related,
        status=nw.status,
        linked_at=ts,
    )


def reconcile_orphans(vault_root: pathlib.Path, r: "redis.Redis") -> None:
    """
    On startup: find any nodes with related: [] and attempt to link them.
    Handles crash-before-link scenarios (AC-4 backstop).
    """
    nodes_dir = vault_root / "nodes"
    if not nodes_dir.exists():
        return

    for md_file in nodes_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            fm = _parse_frontmatter(content)
            if fm.get("related", "").strip() in ("[]", ""):
                node_id = fm.get("id", md_file.stem)
                nw = NodeWritten(
                    id=node_id,
                    path=str(md_file.relative_to(vault_root.parent)),
                    type=fm.get("type", "decision"),
                    title=fm.get("title", "").strip('"'),
                    status=NodeStatus.approved,
                    flags=[],
                    intent_ref=fm.get("intent_ref", ""),
                )
                link_node(nw, r, vault_root)
                logger.info("Reconciled orphan: %s", node_id)
        except Exception as exc:
            logger.warning("reconcile_orphans: skipping %s: %s", md_file, exc)
