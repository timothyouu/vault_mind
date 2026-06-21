import os
import threading
import pytest
from pathlib import Path
from vaultmind.contracts import (
    Extraction, NodeType, NodeStatus, ScribeResult, SourceTool
)
from vaultmind.notecreator import write_nodes, atomic_write


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "nodes").mkdir()
    return v


SCRIBE_RESULT = ScribeResult(
    turn_id="sess-001-abc",
    source_tool=SourceTool.claude_code,
    source_session="sess-001",
    extractions=[
        Extraction(
            type=NodeType.decision,
            title="Use Supabase RLS for row-level auth",
            slug="supabase-rls-policies",
            body="Decided to enforce per-row access with Supabase RLS.\n\n> \"let's just do RLS\"",
        )
    ],
    intent_shift=None,
)

SCRIBE_RESULT_EMPTY = ScribeResult(
    turn_id="sess-001-abc",
    source_tool=SourceTool.claude_code,
    source_session="sess-001",
    extractions=[],
    intent_shift=None,
)

SCRIBE_RESULT_WITH_INTENT = ScribeResult(
    turn_id="sess-001-def",
    source_tool=SourceTool.claude_code,
    source_session="sess-001",
    extractions=[],
    intent_shift="Help me finish the auth flow",
)

SCRIBE_RESULT_WITH_SECRET = ScribeResult(
    turn_id="sess-001-ghi",
    source_tool=SourceTool.claude_code,
    source_session="sess-001",
    extractions=[
        Extraction(
            type=NodeType.constraint,
            title="Supabase service key",
            slug="supabase-keys",
            body='service_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNlY3JldCIsInJvbGUiOiJzZXJ2aWNlX3JvbGUiLCJpYXQiOjE2NDAxMTkyMDAsImV4cCI6MTk1NTY5NTIwMH0.FAKE_SIGNATURE_FOR_TEST"',
        )
    ],
    intent_shift=None,
)


def test_write_nodes_returns_one_node(vault):
    nodes = write_nodes(SCRIBE_RESULT, vault)
    assert len(nodes) == 1
    nw = nodes[0]
    assert nw.type == NodeType.decision
    assert nw.title == "Use Supabase RLS for row-level auth"
    assert "supabase-rls-policies" in nw.id
    assert nw.status == NodeStatus.approved
    assert nw.flags == []


def test_write_nodes_creates_file(vault):
    nodes = write_nodes(SCRIBE_RESULT, vault)
    node_path = vault.parent / nodes[0].path
    assert node_path.exists()


def test_node_file_has_correct_frontmatter(vault):
    nodes = write_nodes(SCRIBE_RESULT, vault)
    content = (vault.parent / nodes[0].path).read_text()
    assert "id:" in content
    assert "type: decision" in content
    assert "status: approved" in content
    assert "related: []" in content


def test_node_file_body_contains_original_body(vault):
    nodes = write_nodes(SCRIBE_RESULT, vault)
    content = (vault.parent / nodes[0].path).read_text()
    assert "Decided to enforce per-row access" in content


def test_empty_extractions_returns_empty_list(vault):
    nodes = write_nodes(SCRIBE_RESULT_EMPTY, vault)
    assert nodes == []


def test_intent_shift_appends_to_intentlog(vault):
    intentlog_path = vault / "IntentLog.md"
    intentlog_path.write_text(
        "# Session Intent Log\n\n## 2026-06-21 10:15 — Current\n"
        '"Get the database schema finalized"\n— claude-code · developer\n',
        encoding="utf-8",
    )
    write_nodes(SCRIBE_RESULT_WITH_INTENT, vault)
    content = intentlog_path.read_text(encoding="utf-8")
    assert "Help me finish the auth flow" in content
    assert "ai-detected" in content
    assert content.count("— Current") == 1


def test_secret_detected_flag_set(vault):
    nodes = write_nodes(SCRIBE_RESULT_WITH_SECRET, vault)
    assert len(nodes) == 1
    assert "secret-detected" in nodes[0].flags


def test_secret_does_not_block_write(vault):
    nodes = write_nodes(SCRIBE_RESULT_WITH_SECRET, vault)
    node_path = vault.parent / nodes[0].path
    assert node_path.exists()


def test_atomic_write_no_leftover_tmp(tmp_path):
    target = tmp_path / "file.md"
    atomic_write(target, "hello world")
    assert target.exists()
    assert not (tmp_path / "file.md.tmp").exists()
    assert target.read_text() == "hello world"
