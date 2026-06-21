"""
vaultmind/orchestrator/__init__.py — Fetch.AI uAgent + 3 ASI:One intents + TurnProgress.

Public API (for testing):
    handle_intent(text: str, vault_root: Path) -> str
    InFlightTracker — in-flight turn table with stuck detection

Entry point:
    run_orchestrator(vault_root, redis_url, seed) -> None   # starts the uAgent

The uAgent uses Chat Protocol (uagents-core) and runs a background thread
that subscribes to Redis pub/sub vaultmind:progress for TurnProgress events.

NOTE: all uagents imports are deferred inside run_orchestrator() so this module
imports cleanly without uagents installed — unit tests of handle_intent and
InFlightTracker work without the package.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import threading
import time
from typing import NamedTuple

logger = logging.getLogger(__name__)

CHANNEL_PROGRESS = "vaultmind:progress"
_DEFAULT_VAULT = pathlib.Path(os.environ.get("VAULTMIND_VAULT_ROOT", "./vault"))

# Terminal stages after which a turn is never stuck
_TERMINAL_STAGES = {"done", "failed"}


# ---------------------------------------------------------------------------
# In-flight tracker (stuck detection — AC-4)
# ---------------------------------------------------------------------------

class _TurnState(NamedTuple):
    stage: str
    ts: float  # monotonic timestamp


class InFlightTracker:
    """
    Thread-safe in-flight table.  A turn at a non-terminal stage past
    stuck_timeout_s is flagged stuck.
    """

    def __init__(self, stuck_timeout_s: float = 300.0) -> None:
        self._table: dict[str, _TurnState] = {}
        self._lock = threading.Lock()
        self._stuck_timeout = stuck_timeout_s

    def update(self, turn_id: str, stage: str, node_ids: list[str]) -> None:
        with self._lock:
            self._table[turn_id] = _TurnState(stage=stage, ts=time.monotonic())
        if stage in _TERMINAL_STAGES:
            logger.debug("Turn %s reached %s", turn_id, stage)
        else:
            logger.debug("Turn %s at stage %s", turn_id, stage)

    def get_stuck(self) -> list[str]:
        """Return turn_ids that have been in a non-terminal stage too long."""
        now = time.monotonic()
        stuck = []
        with self._lock:
            for turn_id, state in self._table.items():
                if state.stage not in _TERMINAL_STAGES:
                    if now - state.ts > self._stuck_timeout:
                        stuck.append(turn_id)
        return stuck


# ---------------------------------------------------------------------------
# Vault readers (shared by intent handlers)
# ---------------------------------------------------------------------------

def _read_file(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _parse_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    try:
        end = content.index("---", 3)
    except ValueError:
        return {}
    fm_block = content[3:end].strip()
    result: dict = {}
    for line in fm_block.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _load_nodes(vault_root: pathlib.Path) -> list[dict]:
    nodes_dir = vault_root / "nodes"
    if not nodes_dir.exists():
        return []
    nodes = []
    for md in sorted(nodes_dir.glob("*.md"), reverse=True):
        content = _read_file(md)
        fm = _parse_frontmatter(content)
        fm["_content"] = content
        fm["_path"] = md
        nodes.append(fm)
    return nodes


def _current_intent(vault_root: pathlib.Path) -> str:
    intentlog = vault_root / "IntentLog.md"
    if not intentlog.exists():
        return "(no intent recorded)"
    for line in intentlog.read_text(encoding="utf-8").splitlines():
        if line.startswith('"') or (line and line[0] in ('"', "'")):
            return line.strip('"').strip("'")
    return "(no intent recorded)"


def _project_name(vault_root: pathlib.Path) -> str:
    goal = _read_file(vault_root / "ProjectGoal.md")
    for line in goal.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return vault_root.parent.name


# ---------------------------------------------------------------------------
# Intent A: project state
# ---------------------------------------------------------------------------

def _intent_a(vault_root: pathlib.Path) -> str:
    project = _project_name(vault_root)
    intent = _current_intent(vault_root)
    nodes = _load_nodes(vault_root)

    scope_goal = _read_file(vault_root / "ProjectGoal.md")
    scope_constraints = _read_file(vault_root / "Constraints.md")
    scope_tech = _read_file(vault_root / "TechStack.md")

    # Extract standing frame
    goal_line = next(
        (l for l in scope_goal.splitlines() if l and not l.startswith("#")), ""
    )
    constraint_lines = [
        l.strip("- ").strip()
        for l in scope_constraints.splitlines()
        if l.startswith("- ") or l.startswith("* ")
    ][:2]
    tech_lines = [
        l.strip("- ").strip()
        for l in scope_tech.splitlines()
        if l.startswith("- ") or l.startswith("* ")
    ][:2]

    recent = nodes[:3]
    recent_text = ""
    for i, n in enumerate(recent, 1):
        ntype = n.get("type", "?")
        title = n.get("title", "").strip('"')
        created = n.get("created", "")[:16]
        recent_text += f"  {i}. [{ntype}]  {title}  — {created}\n"

    compaction_warning = ""
    for n in nodes:
        if "post-compaction" in n.get("flags", ""):
            compaction_warning = "\nContext compacted recently; some nodes may need review."
            break

    return (
        f"{project} — current focus:\n"
        f'  "{intent}"\n'
        f"Standing frame:\n"
        f"  * Goal: {goal_line}\n"
        f"  * Constraints: {'; '.join(constraint_lines) or '(see Constraints.md)'}\n"
        f"  * Stack: {'; '.join(tech_lines) or '(see TechStack.md)'}\n"
        f"Recent nodes ({len(recent)} of {len(nodes)}):\n"
        f"{recent_text}"
        f"{compaction_warning}"
    ).strip()


# ---------------------------------------------------------------------------
# Intent B: handoff readiness
# ---------------------------------------------------------------------------

def _intent_b(vault_root: pathlib.Path) -> str:
    from vaultmind.secrets import scan_for_secrets

    nodes = _load_nodes(vault_root)
    blocked_secrets = []
    pending_nodes = []

    for n in nodes:
        node_path = n.get("_path")
        if node_path:
            content = _read_file(node_path)
            matches = scan_for_secrets(content)
            if matches:
                rel = pathlib.Path(node_path).name
                # matches are SecretMatch dataclass objects with .line and .description attributes
                first = matches[0]
                blocked_secrets.append(
                    f"  vault/nodes/{rel}:{first.line}  pattern: \"{first.description}\""
                )
        if n.get("status", "").strip() == "pending":
            pending_nodes.append(n.get("title", "").strip('"'))

    if blocked_secrets:
        secret_list = "\n".join(blocked_secrets)
        pending_str = (
            f"\n{len(pending_nodes)} node(s) still awaiting review."
            if pending_nodes
            else ""
        )
        return (
            "Not ready — handoff is BLOCKED.\n"
            f"Secret detected (scanned just now):\n{secret_list}{pending_str}\n"
            "I will not expose the vault to a receiving agent while a secret is present.\n"
            "Fix the flagged node in the web app, then ask again."
        )

    if pending_nodes:
        return (
            f"Not ready — {len(pending_nodes)} node(s) awaiting review:\n"
            + "\n".join(f"  * {t}" for t in pending_nodes)
            + "\nApprove them in the web app, then trigger handoff."
        )

    intent = _current_intent(vault_root)
    return (
        f"Ready — {len(nodes)} node(s), all approved, scan clean.\n"
        f'Carry-forward intent: "{intent}" — still current? (yes/no)\n'
        "Receiving agent: read VaultIndex.md -> current IntentLog entry -> nodes/."
    )


# ---------------------------------------------------------------------------
# Intent C: open questions
# ---------------------------------------------------------------------------

def _intent_c(vault_root: pathlib.Path) -> str:
    nodes = _load_nodes(vault_root)
    questions = [n for n in nodes if n.get("type", "").strip() == "question"]

    if not questions:
        return "No open questions recorded in the vault."

    lines = []
    for i, q in enumerate(questions, 1):
        title = q.get("title", "").strip('"')
        created = q.get("created", "")[:16]
        intent_ref = q.get("intent_ref", "")
        entry = f"  {i}. {title}  — {created}"
        if intent_ref:
            entry += f", intent: {intent_ref}"
        lines.append(entry)

    return f"{len(questions)} open question(s):\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Intent dispatcher (pure function — used in tests and by the uAgent handler)
# ---------------------------------------------------------------------------

def handle_intent(text: str, vault_root: pathlib.Path) -> str:
    """
    Route text to the appropriate intent handler.
    Returns a plain-text response string.

    This is a pure function (no Redis, no uAgents) — safe to call in tests.
    Intent detection uses keyword matching on text.lower().
    """
    lower = text.lower()

    if any(k in lower for k in ["project state", "current state", "working on", "what are we"]):
        return _intent_a(vault_root)

    if any(k in lower for k in ["handoff", "hand off", "ready", "trigger"]):
        return _intent_b(vault_root)

    if any(k in lower for k in ["question", "open question", "outstanding"]):
        return _intent_c(vault_root)

    # Default help message
    return (
        "I can help with:\n"
        "  * Project state -- \"What's the current state of this project?\"\n"
        "  * Handoff readiness -- \"Is the vault ready to hand off?\"\n"
        "  * Open questions -- \"What are the open questions?\""
    )


# ---------------------------------------------------------------------------
# TurnProgress subscriber (background thread)
# ---------------------------------------------------------------------------

def _start_progress_subscriber(redis_url: str, tracker: InFlightTracker) -> None:
    """Subscribe to vaultmind:progress and update the in-flight tracker."""

    def _run() -> None:
        import redis as _redis

        while True:
            try:
                r = _redis.from_url(redis_url, decode_responses=True)
                ps = r.pubsub()
                ps.subscribe(CHANNEL_PROGRESS)
                for msg in ps.listen():
                    if msg["type"] != "message":
                        continue
                    try:
                        data = json.loads(msg["data"])
                        tracker.update(
                            data["turn_id"],
                            data["stage"],
                            data.get("node_ids", []),
                        )
                        stuck = tracker.get_stuck()
                        if stuck:
                            logger.warning(
                                "Orchestrator: stuck turn(s) detected: %s", stuck
                            )
                    except Exception as exc:
                        logger.error("TurnProgress parse error: %s", exc)
            except Exception as exc:
                logger.error("Progress subscriber error: %s -- retrying in 5s", exc)
                time.sleep(5)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# uAgent entry point — all uagents imports live here so the module loads
# cleanly without the package installed (unit tests don't need it)
# ---------------------------------------------------------------------------

def run_orchestrator(
    vault_root: pathlib.Path,
    redis_url: str,
    seed: str,
) -> None:
    """
    Start the Fetch.AI uAgent. Blocks until interrupted.

    Requires: uagents, uagents-core packages installed.
    All uagents imports are deferred here so unit tests work without the package.
    """
    try:
        from uagents import Agent, Context, Protocol
        from uagents_core.contrib.protocols.chat import (
            ChatMessage,
            ChatAcknowledgement,
            TextContent,
        )
    except ImportError as e:
        raise RuntimeError(
            "uagents / uagents-core not installed. "
            "Install with: uv add uagents uagents-core fetchai"
        ) from e

    tracker = InFlightTracker(stuck_timeout_s=300.0)
    _start_progress_subscriber(redis_url, tracker)

    agent = Agent(
        name="vaultmind-orchestrator",
        seed=seed,
        port=8001,
        endpoint=["http://localhost:8001/submit"],
    )
    chat_protocol = Protocol(name="AgentChatProtocol", version="0.3.0")

    @chat_protocol.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
        text = " ".join(
            item.text for item in msg.content if hasattr(item, "text")
        )
        logger.info("Orchestrator received: %s", text[:120])
        response_text = handle_intent(text, vault_root)
        reply = ChatMessage(content=[TextContent(text=response_text)])
        await ctx.send(sender, reply)

    @chat_protocol.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
        logger.debug("Orchestrator: ack from %s", sender)

    agent.include(chat_protocol, publish_manifest=True)
    agent.run()
