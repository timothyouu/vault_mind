"""
vaultmind/handoff/__init__.py — Handoff-time secret scan + entry-point assembly.

Public API:
    check_handoff_readiness(vault_root: Path) -> HandoffResult
    assemble_entry_point(vault_root: Path) -> str
"""
from __future__ import annotations

import datetime
import pathlib
from dataclasses import dataclass, field

from vaultmind.secrets import scan_for_secrets


@dataclass
class HandoffResult:
    ready: bool
    blocked_secrets: list[str] = field(default_factory=list)
    pending_nodes: list[str] = field(default_factory=list)
    node_count: int = 0


def _parse_frontmatter_simple(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    try:
        end = content.index("---", 3)
    except ValueError:
        return {}
    result: dict = {}
    for line in content[3:end].strip().splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def check_handoff_readiness(vault_root: pathlib.Path) -> HandoffResult:
    """
    Run handoff-time scanForSecrets on all vault/nodes/*.md.
    Returns HandoffResult with ready=True only when no secrets and no pending nodes.
    """
    nodes_dir = vault_root / "nodes"
    blocked = []
    pending = []
    count = 0

    if nodes_dir.exists():
        for md in nodes_dir.glob("*.md"):
            count += 1
            content = md.read_text(encoding="utf-8")
            matches = scan_for_secrets(content)
            if matches:
                rel = f"vault/nodes/{md.name}"
                blocked.append(f"{rel}:{matches[0].line}  {matches[0].description}")
            fm = _parse_frontmatter_simple(content)
            if fm.get("status", "").strip() == "pending":
                pending.append(fm.get("title", md.stem).strip('"'))

    return HandoffResult(
        ready=len(blocked) == 0,
        blocked_secrets=blocked,
        pending_nodes=pending,
        node_count=count,
    )


def assemble_entry_point(vault_root: pathlib.Path) -> str:
    """
    Build the entry-point text for a receiving agent.
    Format: VaultIndex pointer + current intent + node count + timestamp.
    """
    intentlog = vault_root / "IntentLog.md"
    current_intent = "(no intent recorded)"
    if intentlog.exists():
        for line in intentlog.read_text(encoding="utf-8").splitlines():
            if line.startswith('"') or (line and line[0] == '"'):
                current_intent = line.strip('"')
                break

    node_count = len(list((vault_root / "nodes").glob("*.md"))) if (vault_root / "nodes").exists() else 0
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    return (
        f"# VaultMind Handoff — {ts}\n\n"
        f"## Entry Point\n"
        f"Start at: `VaultIndex.md` → current IntentLog entry → `nodes/`\n\n"
        f"## Current Intent\n"
        f'"{current_intent}"\n\n'
        f"## Vault Stats\n"
        f"- Nodes: {node_count}\n"
        f"- Vault root: {vault_root}\n\n"
        f"## Read Order (from VaultIndex.md)\n"
        f"1. ProjectGoal.md, Constraints.md, TechStack.md — standing frame\n"
        f"2. Current entry in IntentLog.md (top, marked Current)\n"
        f"3. SessionState.md — compaction flags\n"
        f"4. nodes/ — atomic decisions/constraints/goals/questions\n"
    )
