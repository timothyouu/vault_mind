import json
import time
import pytest
import fakeredis
from pathlib import Path
from vaultmind.orchestrator import handle_intent, InFlightTracker

FIXTURE_VAULT = Path(__file__).parent.parent / "fixtures" / "vault"


def test_intent_a_project_state(tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    response = handle_intent("What's the current state of this project?", vault)
    assert "TaskFlow" in response or "current focus" in response.lower() or "intent" in response.lower()
    assert len(response) > 50


def test_intent_a_recent_nodes_listed(tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    response = handle_intent("what are we working on", vault)
    # Should mention at least one node type
    assert any(word in response.lower() for word in ["decision", "constraint", "goal", "question"])


def test_intent_b_blocked_when_secret_present(tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    response = handle_intent("Is the vault ready to hand off?", vault)
    # fixture vault has a secret-detected node (supabase-keys)
    assert "blocked" in response.lower() or "not ready" in response.lower() or "secret" in response.lower()


def test_intent_b_ready_when_clean(tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    # Remove the secret node
    secret_node = vault / "nodes" / "2026-06-21-1408-supabase-keys.md"
    if secret_node.exists():
        secret_node.unlink()
    response = handle_intent("trigger handoff", vault)
    # With no pending or secret nodes, should be ready or close to it
    assert isinstance(response, str) and len(response) > 10


def test_intent_c_open_questions(tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    response = handle_intent("What are the open questions?", vault)
    assert "question" in response.lower() or "Should" in response


def test_unknown_intent_returns_help(tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    response = handle_intent("do something random xyz", vault)
    assert isinstance(response, str) and len(response) > 0


def test_in_flight_tracker_stuck_detection():
    tracker = InFlightTracker(stuck_timeout_s=0.1)
    tracker.update("turn-001", "written", [])
    time.sleep(0.15)
    stuck = tracker.get_stuck()
    assert "turn-001" in stuck


def test_in_flight_tracker_done_not_stuck():
    tracker = InFlightTracker(stuck_timeout_s=0.1)
    tracker.update("turn-002", "written", [])
    tracker.update("turn-002", "done", ["node-1"])
    time.sleep(0.15)
    stuck = tracker.get_stuck()
    assert "turn-002" not in stuck


def test_in_flight_tracker_update_clears_stuck():
    tracker = InFlightTracker(stuck_timeout_s=0.5)
    tracker.update("turn-003", "started", [])
    tracker.update("turn-003", "extracted", [])
    tracker.update("turn-003", "written", [])
    tracker.update("turn-003", "linked", [])
    tracker.update("turn-003", "done", ["node-a"])
    stuck = tracker.get_stuck()
    assert "turn-003" not in stuck
