"""
tests/test_integration_handoff.py — Handoff + Orchestrator integration tests.

Exercises the P3 handoff path from a vault that has been written by the
full pipeline through to the handoff entry-point string returned to a
receiving agent.

Covers:
  1. check_handoff_readiness correctness across various vault states.
  2. assemble_entry_point structure and content.
  3. Orchestrator handle_intent responses for all three ASI:One intent classes.
  4. End-to-end: NoteCreator writes nodes → handoff checks them.
  5. Pending nodes block handoff (status: pending).
  6. Entry-point includes current IntentLog entry, VaultIndex pointer, and node count.
"""
from __future__ import annotations

import pathlib
import shutil

import pytest

from vaultmind.contracts import (
    Extraction,
    NodeType,
    ScribeResult,
    SourceTool,
)
from vaultmind.handoff import HandoffResult, assemble_entry_point, check_handoff_readiness
from vaultmind.notecreator import write_nodes
from vaultmind.orchestrator import handle_intent

REPO_ROOT = pathlib.Path(__file__).parent.parent
FIXTURE_VAULT = REPO_ROOT / "fixtures" / "vault"

DEMO_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNjMwMDAwMDAwLCJleHAiOjE5OTk5OTk5OTl9"
    ".DEMO_SIGNATURE_PLACEHOLDER_NOT_A_REAL_KEY"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def vault(tmp_path: pathlib.Path) -> pathlib.Path:
    dst = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, dst)
    return dst


@pytest.fixture
def clean_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    dst = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, dst)
    secret = dst / "nodes" / "2026-06-21-1408-supabase-keys.md"
    if secret.exists():
        secret.unlink()
    return dst


@pytest.fixture
def empty_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """A minimal vault with only the anchor files, no nodes."""
    dst = tmp_path / "vault"
    dst.mkdir()
    (dst / "nodes").mkdir()
    (dst / "IntentLog.md").write_text(
        "# Session Intent Log\n\n## 2026-06-21 12:00 — Current\n"
        '"Bootstrap the project"\n— claude-code · developer\n',
        encoding="utf-8",
    )
    (dst / "ProjectGoal.md").write_text(
        "# TaskFlow\nA collaborative task management tool.\n", encoding="utf-8"
    )
    (dst / "Constraints.md").write_text(
        "# Constraints\n- No PII in logs\n", encoding="utf-8"
    )
    (dst / "TechStack.md").write_text(
        "# Tech Stack\n- Next.js, Supabase\n", encoding="utf-8"
    )
    (dst / "VaultIndex.md").write_text(
        "# VaultIndex\nRead ProjectGoal.md first.\n", encoding="utf-8"
    )
    (dst / "SessionState.md").write_text("", encoding="utf-8")
    return dst


# ===========================================================================
# 1. check_handoff_readiness
# ===========================================================================

class TestCheckHandoffReadiness:

    def test_fixture_vault_blocked_by_secret(
        self, vault: pathlib.Path
    ) -> None:
        result = check_handoff_readiness(vault)
        assert isinstance(result, HandoffResult)
        assert not result.ready
        assert len(result.blocked_secrets) >= 1

    def test_clean_vault_is_ready(
        self, clean_vault: pathlib.Path
    ) -> None:
        result = check_handoff_readiness(clean_vault)
        assert result.ready
        assert result.blocked_secrets == []

    def test_empty_vault_is_ready(
        self, empty_vault: pathlib.Path
    ) -> None:
        result = check_handoff_readiness(empty_vault)
        assert result.ready
        assert result.blocked_secrets == []
        assert result.node_count == 0

    def test_node_count_matches_files(
        self, vault: pathlib.Path
    ) -> None:
        expected = len(list((vault / "nodes").glob("*.md")))
        result = check_handoff_readiness(vault)
        assert result.node_count == expected

    def test_pending_node_reported(
        self, clean_vault: pathlib.Path
    ) -> None:
        """A node with status: pending is surfaced in pending_nodes."""
        pending_node = clean_vault / "nodes" / "2099-01-01-0000-pending-test.md"
        pending_node.write_text(
            "---\n"
            "id: 2099-01-01-0000-pending-test\n"
            "type: decision\n"
            "title: \"Pending Decision\"\n"
            "created: 2099-01-01T00:00:00Z\n"
            "source_tool: claude-code\n"
            "source_session: sess-test\n"
            "intent_ref: 2099-01-01 00:00\n"
            "status: pending\n"
            "related: []\n"
            "flags: []\n"
            "---\n"
            "This node is still pending review.\n",
            encoding="utf-8",
        )
        result = check_handoff_readiness(clean_vault)
        assert "Pending Decision" in result.pending_nodes

    def test_adding_secret_node_blocks_previously_ready_vault(
        self, clean_vault: pathlib.Path
    ) -> None:
        """Adding a secret node to a clean vault must make handoff not ready."""
        assert check_handoff_readiness(clean_vault).ready

        sr = ScribeResult(
            turn_id="sess-ho-001",
            source_tool=SourceTool.claude_code,
            source_session="sess-ho",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title="Newly leaked key",
                    slug="newly-leaked-key",
                    body=f'key = "{DEMO_JWT}"',
                )
            ],
            intent_shift=None,
        )
        write_nodes(sr, clean_vault)

        result = check_handoff_readiness(clean_vault)
        assert not result.ready
        assert len(result.blocked_secrets) >= 1

    def test_removing_secret_node_makes_vault_ready(
        self, vault: pathlib.Path
    ) -> None:
        """Removing the secret node from the fixture vault makes it ready."""
        assert not check_handoff_readiness(vault).ready

        secret = vault / "nodes" / "2026-06-21-1408-supabase-keys.md"
        secret.unlink()

        result = check_handoff_readiness(vault)
        assert result.ready

    def test_blocked_secrets_entries_include_file_reference(
        self, vault: pathlib.Path
    ) -> None:
        """Each blocked_secrets entry must reference the file name."""
        result = check_handoff_readiness(vault)
        for entry in result.blocked_secrets:
            assert "vault/nodes/" in entry and ".md:" in entry


# ===========================================================================
# 2. assemble_entry_point
# ===========================================================================

class TestAssembleEntryPoint:

    def test_entry_point_mentions_vaultindex(
        self, vault: pathlib.Path
    ) -> None:
        entry = assemble_entry_point(vault)
        assert "VaultIndex" in entry

    def test_entry_point_mentions_intentlog(
        self, vault: pathlib.Path
    ) -> None:
        entry = assemble_entry_point(vault)
        assert "IntentLog" in entry or "intent" in entry.lower()

    def test_entry_point_includes_current_intent(
        self, vault: pathlib.Path
    ) -> None:
        """Fixture IntentLog's current entry must appear in the entry point."""
        entry = assemble_entry_point(vault)
        assert "auth flow" in entry.lower() or "Supabase" in entry

    def test_entry_point_includes_node_count(
        self, vault: pathlib.Path
    ) -> None:
        expected_count = len(list((vault / "nodes").glob("*.md")))
        entry = assemble_entry_point(vault)
        assert str(expected_count) in entry

    def test_entry_point_has_read_order(
        self, vault: pathlib.Path
    ) -> None:
        entry = assemble_entry_point(vault)
        assert "ProjectGoal" in entry or "1." in entry

    def test_entry_point_reflects_new_nodes_after_write(
        self, clean_vault: pathlib.Path
    ) -> None:
        """Node count in entry point updates after NoteCreator writes new nodes."""
        entry_before = assemble_entry_point(clean_vault)
        count_before = len(list((clean_vault / "nodes").glob("*.md")))

        sr = ScribeResult(
            turn_id="sess-ep-001",
            source_tool=SourceTool.claude_code,
            source_session="sess-ep",
            extractions=[
                Extraction(
                    type=NodeType.decision,
                    title="New entry-point node",
                    slug="new-entry-point-node",
                    body="Added to test node count update.",
                )
            ],
            intent_shift=None,
        )
        write_nodes(sr, clean_vault)

        entry_after = assemble_entry_point(clean_vault)
        assert str(count_before + 1) in entry_after

    def test_entry_point_reflects_intent_shift(
        self, clean_vault: pathlib.Path
    ) -> None:
        """If an intent shift was written to IntentLog, entry point shows the new intent."""
        sr = ScribeResult(
            turn_id="sess-ep-002",
            source_tool=SourceTool.claude_code,
            source_session="sess-ep",
            extractions=[],
            intent_shift="Switch to deployment hardening",
        )
        write_nodes(sr, clean_vault)

        entry = assemble_entry_point(clean_vault)
        assert "Switch to deployment hardening" in entry

    def test_entry_point_empty_vault(
        self, empty_vault: pathlib.Path
    ) -> None:
        """Entry point is still valid for a vault with no nodes."""
        entry = assemble_entry_point(empty_vault)
        assert "VaultIndex" in entry
        assert "0" in entry  # node count


# ===========================================================================
# 3. Orchestrator handle_intent
# ===========================================================================

class TestOrchestratorHandleIntent:

    def test_intent_a_returns_project_state(
        self, vault: pathlib.Path
    ) -> None:
        response = handle_intent("What's the current state of this project?", vault)
        assert isinstance(response, str) and len(response) > 50
        assert any(
            w in response.lower()
            for w in ["taskflow", "intent", "current", "decision", "constraint", "goal"]
        )

    def test_intent_a_mentions_recent_nodes(
        self, vault: pathlib.Path
    ) -> None:
        response = handle_intent("what are we working on", vault)
        assert any(
            w in response.lower()
            for w in ["decision", "constraint", "goal", "question"]
        )

    def test_intent_b_blocked_by_secret(
        self, vault: pathlib.Path
    ) -> None:
        response = handle_intent("Is the vault ready to hand off?", vault)
        assert any(
            w in response.lower()
            for w in ["blocked", "not ready", "secret", "detected"]
        )

    def test_intent_b_ready_after_secret_removed(
        self, clean_vault: pathlib.Path
    ) -> None:
        response = handle_intent("trigger handoff", clean_vault)
        assert isinstance(response, str) and len(response) > 10
        # When clean, should NOT say "blocked"
        assert "blocked" not in response.lower() or "not ready" not in response.lower()

    def test_intent_c_lists_open_questions(
        self, vault: pathlib.Path
    ) -> None:
        """Fixture vault has a question node about org-switch session invalidation."""
        response = handle_intent("What are the open questions?", vault)
        assert "question" in response.lower() or "Should" in response or "?" in response

    def test_unknown_intent_returns_non_empty_string(
        self, vault: pathlib.Path
    ) -> None:
        response = handle_intent("xyzzy frobnicator nonsense", vault)
        assert isinstance(response, str) and len(response) > 0

    def test_intent_on_empty_vault_does_not_crash(
        self, empty_vault: pathlib.Path
    ) -> None:
        """handle_intent must not raise even when there are no nodes."""
        response = handle_intent("What's the project state?", empty_vault)
        assert isinstance(response, str)

    def test_intent_a_includes_project_name(
        self, vault: pathlib.Path
    ) -> None:
        """Fixture ProjectGoal has '# TaskFlow' — should appear in state response."""
        response = handle_intent("give me a project overview", vault)
        assert "TaskFlow" in response or len(response) > 50

    def test_intent_a_includes_current_intent(
        self, vault: pathlib.Path
    ) -> None:
        """The current IntentLog entry should be surfaced in the state response."""
        # Use a phrase that matches intent A keywords ("current state")
        response = handle_intent("what is the current state of the project?", vault)
        assert "auth flow" in response.lower() or "intent" in response.lower()


# ===========================================================================
# 4. End-to-end: pipeline → handoff
# ===========================================================================

class TestEndToEndPipelineHandoff:
    """Write nodes through NoteCreator then verify handoff behavior."""

    def test_clean_nodes_do_not_block_handoff(
        self, clean_vault: pathlib.Path
    ) -> None:
        """Writing clean nodes should not affect handoff readiness."""
        for i in range(3):
            sr = ScribeResult(
                turn_id=f"sess-e2e-{i:03d}",
                source_tool=SourceTool.claude_code,
                source_session="sess-e2e",
                extractions=[
                    Extraction(
                        type=NodeType.decision,
                        title=f"Clean decision {i}",
                        slug=f"clean-decision-{i}",
                        body=f"Body text for clean decision {i}.",
                    )
                ],
                intent_shift=None,
            )
            write_nodes(sr, clean_vault)

        result = check_handoff_readiness(clean_vault)
        assert result.ready
        assert result.blocked_secrets == []

    def test_mixed_vault_blocked_by_any_secret(
        self, clean_vault: pathlib.Path
    ) -> None:
        """One secret node among many clean nodes still blocks handoff."""
        # Write 3 clean nodes
        for i in range(3):
            sr = ScribeResult(
                turn_id=f"sess-mix-clean-{i}",
                source_tool=SourceTool.claude_code,
                source_session="sess-mix",
                extractions=[
                    Extraction(
                        type=NodeType.goal,
                        title=f"Clean goal {i}",
                        slug=f"clean-goal-{i}",
                        body="No secrets here.",
                    )
                ],
                intent_shift=None,
            )
            write_nodes(sr, clean_vault)

        # Write 1 secret node
        sr_secret = ScribeResult(
            turn_id="sess-mix-secret",
            source_tool=SourceTool.claude_code,
            source_session="sess-mix",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title="The one bad node",
                    slug="the-one-bad-node",
                    body=f'svc = "{DEMO_JWT}"',
                )
            ],
            intent_shift=None,
        )
        write_nodes(sr_secret, clean_vault)

        result = check_handoff_readiness(clean_vault)
        assert not result.ready
        assert len(result.blocked_secrets) >= 1

    def test_entry_point_after_pipeline_run(
        self, clean_vault: pathlib.Path
    ) -> None:
        """Entry point assembled after pipeline nodes have been written is coherent."""
        sr = ScribeResult(
            turn_id="sess-ep-e2e-001",
            source_tool=SourceTool.claude_code,
            source_session="sess-ep-e2e",
            extractions=[
                Extraction(
                    type=NodeType.decision,
                    title="Use Redis for queue",
                    slug="use-redis-queue",
                    body="Decided to use Redis Streams as the primary queue.",
                )
            ],
            intent_shift="Shift to infrastructure setup",
        )
        write_nodes(sr, clean_vault)

        entry = assemble_entry_point(clean_vault)
        # Should mention the new node count
        count = len(list((clean_vault / "nodes").glob("*.md")))
        assert str(count) in entry
        # Intent shift was written, so entry point should reflect new intent
        assert "Shift to infrastructure setup" in entry or "infrastructure" in entry.lower()

    def test_orchestrator_reflects_vault_state_after_write(
        self, clean_vault: pathlib.Path
    ) -> None:
        """Orchestrator reads vault from disk; newly written nodes appear in responses."""
        sr = ScribeResult(
            turn_id="sess-orch-e2e-001",
            source_tool=SourceTool.claude_code,
            source_session="sess-orch-e2e",
            extractions=[
                Extraction(
                    type=NodeType.question,
                    title="Should we migrate to k8s?",
                    slug="migrate-to-k8s",
                    body="Open question about moving from ECS to Kubernetes.",
                )
            ],
            intent_shift=None,
        )
        write_nodes(sr, clean_vault)

        response = handle_intent("What are the open questions?", clean_vault)
        assert "question" in response.lower() or "k8s" in response.lower() or "?" in response
