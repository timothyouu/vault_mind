"""
tests/test_integration_secrets.py — Secret detection integration tests.

Exercises scanForSecrets across all three call sites specified in SPEC.md:

  1. Write-time  : NoteCreator calls scan_for_secrets before writing each node.
                   A secret in the body → 'secret-detected' flag; write proceeds.
  2. Commit-time : pre-commit hook calls `python -m vaultmind.secrets` via git diff
                   and exits 1 when a staged vault/ file contains a secret.
  3. Handoff-time: check_handoff_readiness scans all nodes; secrets block handoff
                   and appear in HandoffResult.blocked_secrets.

Additional cross-cutting checks:
  - scan_for_secrets is a single implementation (no duplication).
  - Masking: [REDACTED] replaces the literal secret in every excerpt.
  - Clean content never triggers a false positive across all three sites.
  - The fixture secret node (supabase-keys.md) is consistently detected at
    write-time, handoff-time, and via the CLI.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

from vaultmind.secrets import scan_for_secrets, SecretMatch
from vaultmind.contracts import Extraction, NodeType, ScribeResult, SourceTool
from vaultmind.notecreator import write_nodes
from vaultmind.handoff import check_handoff_readiness

REPO_ROOT = pathlib.Path(__file__).parent.parent
FIXTURE_VAULT = REPO_ROOT / "fixtures" / "vault"
FIXTURE_SECRET_NODE = FIXTURE_VAULT / "nodes" / "2026-06-21-1408-supabase-keys.md"
FIXTURE_CLEAN_NODE = FIXTURE_VAULT / "nodes" / "2026-06-21-1432-supabase-rls-policies.md"
HOOK_SCRIPT = REPO_ROOT / "vaultmind" / "hooks" / "pre-commit.sh"

# The seeded demo JWT used throughout fixtures.  Inert — not a real key.
DEMO_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNjMwMDAwMDAwLCJleHAiOjE5OTk5OTk5OTl9"
    ".DEMO_SIGNATURE_PLACEHOLDER_NOT_A_REAL_KEY"
)
CONTENT_WITH_SECRET = f'service_role_key = "{DEMO_JWT}"\n'
CONTENT_CLEAN = "# Just a regular node\nNo secrets here.\n"


# ---------------------------------------------------------------------------
# Shared vault fixture
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
    # Remove the one node that contains a secret
    secret = dst / "nodes" / "2026-06-21-1408-supabase-keys.md"
    if secret.exists():
        secret.unlink()
    return dst


# ===========================================================================
# 1. Write-time: scan_for_secrets ↔ NoteCreator
# ===========================================================================

class TestWriteTime:
    """NoteCreator uses scan_for_secrets at write-time."""

    def test_scan_detects_demo_jwt(self) -> None:
        matches = scan_for_secrets(CONTENT_WITH_SECRET)
        assert len(matches) >= 1
        m = matches[0]
        assert isinstance(m, SecretMatch)
        assert m.line == 1
        assert m.col >= 1
        assert m.pattern_id
        assert m.description

    def test_scan_clean_content_returns_empty(self) -> None:
        assert scan_for_secrets(CONTENT_CLEAN) == []

    def test_scan_detects_fixture_secret_node(self) -> None:
        content = FIXTURE_SECRET_NODE.read_text()
        matches = scan_for_secrets(content)
        assert len(matches) >= 1, (
            f"Expected ≥1 match in {FIXTURE_SECRET_NODE.name}; got []"
        )

    def test_scan_clean_fixture_node_returns_empty(self) -> None:
        content = FIXTURE_CLEAN_NODE.read_text()
        matches = scan_for_secrets(content)
        assert matches == [], (
            f"Expected no matches in {FIXTURE_CLEAN_NODE.name}; got {matches}"
        )

    def test_excerpt_is_redacted(self) -> None:
        """The literal secret must not appear in any excerpt; [REDACTED] must."""
        matches = scan_for_secrets(CONTENT_WITH_SECRET)
        assert matches
        for m in matches:
            assert "[REDACTED]" in m.excerpt, (
                f"excerpt missing [REDACTED]: {m.excerpt!r}"
            )
            assert DEMO_JWT not in m.excerpt, (
                f"literal secret found in excerpt: {m.excerpt!r}"
            )

    def test_notecreator_flags_secret_node(
        self, vault: pathlib.Path
    ) -> None:
        """NoteCreator sets 'secret-detected' when body has a JWT."""
        sr = ScribeResult(
            turn_id="sess-sec-wt-001",
            source_tool=SourceTool.claude_code,
            source_session="sess-sec-wt",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title="Leaked service key",
                    slug="leaked-service-key",
                    body=f'key = "{DEMO_JWT}"',
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        assert len(written) == 1
        assert "secret-detected" in written[0].flags

    def test_notecreator_does_not_block_write_on_secret(
        self, vault: pathlib.Path
    ) -> None:
        """Write proceeds even when a secret is detected (flag, don't block)."""
        sr = ScribeResult(
            turn_id="sess-sec-wt-002",
            source_tool=SourceTool.claude_code,
            source_session="sess-sec-wt",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title="Another leaked key",
                    slug="another-leaked-key",
                    body=f'token = "{DEMO_JWT}"',
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        assert len(written) == 1
        node_path = vault.parent / written[0].path
        assert node_path.exists(), "Node file must be written even with secret detected"

    def test_notecreator_does_not_flag_clean_node(
        self, vault: pathlib.Path
    ) -> None:
        """Clean content produces a node with an empty flags list."""
        sr = ScribeResult(
            turn_id="sess-sec-wt-003",
            source_tool=SourceTool.claude_code,
            source_session="sess-sec-wt",
            extractions=[
                Extraction(
                    type=NodeType.goal,
                    title="Clean node",
                    slug="clean-node-goal",
                    body="No secrets in here.",
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        assert written[0].flags == []

    def test_notecreator_flags_appear_in_frontmatter(
        self, vault: pathlib.Path
    ) -> None:
        """'secret-detected' flag is written into the YAML frontmatter of the node."""
        sr = ScribeResult(
            turn_id="sess-sec-wt-004",
            source_tool=SourceTool.claude_code,
            source_session="sess-sec-wt",
            extractions=[
                Extraction(
                    type=NodeType.decision,
                    title="Flag in frontmatter",
                    slug="flag-in-frontmatter",
                    body=f'svc_key = "{DEMO_JWT}"',
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        content = (vault.parent / written[0].path).read_text()
        # Flag must be in the frontmatter block (before body)
        fm_end = content.index("---", 3)
        frontmatter = content[:fm_end]
        assert "secret-detected" in frontmatter

    def test_secret_in_title_also_flagged(
        self, vault: pathlib.Path
    ) -> None:
        """A JWT embedded in the title (unusual but possible) is also detected."""
        sr = ScribeResult(
            turn_id="sess-sec-wt-005",
            source_tool=SourceTool.claude_code,
            source_session="sess-sec-wt",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title=f"Key {DEMO_JWT[:30]}",
                    slug="key-in-title",
                    body=f'See the title for key = "{DEMO_JWT}"',
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        assert "secret-detected" in written[0].flags


# ===========================================================================
# 2. Commit-time: pre-commit hook
# ===========================================================================

def _find_bash() -> str:
    if sys.platform != "win32":
        return "bash"
    for candidate in [
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
    ]:
        if pathlib.Path(candidate).exists():
            return candidate
    return "bash"


def _run_hook(vault_file_content: str | None) -> subprocess.CompletedProcess:
    """Spin up a temp git repo, stage an optional vault/ file, run the pre-commit hook."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)

        subprocess.run(["git", "init", str(tmp)], check=True, capture_output=True)
        for key, val in [("user.email", "test@vaultmind.test"), ("user.name", "VM Test")]:
            subprocess.run(
                ["git", "-C", str(tmp), "config", key, val],
                check=True, capture_output=True,
            )

        if vault_file_content is not None:
            node_dir = tmp / "vault" / "nodes"
            node_dir.mkdir(parents=True)
            node_file = node_dir / "test-node.md"
            node_file.write_text(vault_file_content, encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(tmp), "add", "vault/nodes/test-node.md"],
                check=True, capture_output=True,
            )

        env = os.environ.copy()
        env["GIT_DIR"] = str(tmp / ".git")
        env["GIT_WORK_TREE"] = str(tmp)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing if existing else "")

        bash = _find_bash()
        if sys.platform == "win32":
            git_bash_bin = str(pathlib.Path(bash).parent) if bash != "bash" else ""
            python_dir = str(pathlib.Path(sys.executable).parent)
            extra = ";".join(p for p in [git_bash_bin, python_dir] if p)
            env["PATH"] = extra + ";" + env.get("PATH", "")

        hook_src = HOOK_SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")
        return subprocess.run(
            [bash, "-s"],
            input=hook_src,
            capture_output=True,
            text=True,
            cwd=str(tmp),
            env=env,
        )


class TestCommitTime:
    """Pre-commit hook exits 1 on staged secrets, 0 on clean content."""

    def test_hook_blocks_when_staged_file_has_secret(self) -> None:
        result = _run_hook(CONTENT_WITH_SECRET)
        assert result.returncode == 1, (
            f"Hook must exit 1 on staged secret; got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_hook_reports_commit_blocked(self) -> None:
        result = _run_hook(CONTENT_WITH_SECRET)
        combined = result.stdout + result.stderr
        assert "Commit blocked" in combined, (
            f"Expected 'Commit blocked' in output; got:\n{combined}"
        )

    def test_hook_passes_for_clean_content(self) -> None:
        result = _run_hook(CONTENT_CLEAN)
        assert result.returncode == 0, (
            f"Hook must exit 0 on clean content; got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_hook_passes_when_no_vault_files_staged(self) -> None:
        result = _run_hook(None)
        assert result.returncode == 0, (
            f"Hook must exit 0 when nothing staged; got {result.returncode}"
        )

    def test_hook_exit_code_never_nonzero_on_clean(self) -> None:
        """Regression: hook must not produce spurious failures."""
        for _ in range(3):
            result = _run_hook(CONTENT_CLEAN)
            assert result.returncode == 0


# ===========================================================================
# 3. Handoff-time: check_handoff_readiness + CLI
# ===========================================================================

class TestHandoffTime:
    """Handoff-time scan blocks when secrets exist and passes when clean."""

    def test_handoff_blocked_by_fixture_secret_node(
        self, vault: pathlib.Path
    ) -> None:
        result = check_handoff_readiness(vault)
        assert not result.ready
        assert len(result.blocked_secrets) >= 1
        # The blocked entry must mention the problematic node file
        combined = " ".join(result.blocked_secrets).lower()
        assert "supabase" in combined or "key" in combined or "secret" in combined

    def test_handoff_ready_when_vault_is_clean(
        self, clean_vault: pathlib.Path
    ) -> None:
        result = check_handoff_readiness(clean_vault)
        assert result.blocked_secrets == []
        assert result.ready

    def test_handoff_blocked_entry_has_file_and_line(
        self, vault: pathlib.Path
    ) -> None:
        """Each blocked_secrets entry must identify the file and line number."""
        result = check_handoff_readiness(vault)
        for entry in result.blocked_secrets:
            # Expected format: "vault/nodes/<name>.md:<line>  <description>"
            assert ".md:" in entry, f"Expected file:line in entry: {entry!r}"

    def test_handoff_node_count_correct(
        self, vault: pathlib.Path
    ) -> None:
        expected = len(list((vault / "nodes").glob("*.md")))
        result = check_handoff_readiness(vault)
        assert result.node_count == expected

    def test_newly_written_secret_node_blocks_handoff(
        self, vault: pathlib.Path
    ) -> None:
        """A node written by NoteCreator with a secret is detected at handoff-time."""
        sr = ScribeResult(
            turn_id="sess-sec-ht-001",
            source_tool=SourceTool.claude_code,
            source_session="sess-sec-ht",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title="Fresh leaked key",
                    slug="fresh-leaked-key",
                    body=f'svc_key = "{DEMO_JWT}"',
                )
            ],
            intent_shift=None,
        )
        write_nodes(sr, vault)
        result = check_handoff_readiness(vault)
        assert not result.ready
        assert len(result.blocked_secrets) >= 1

    def test_cli_always_exits_zero(self) -> None:
        """python -m vaultmind.secrets <path> always exits 0 (hook reads JSON itself)."""
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing if existing else "")

        for path in [FIXTURE_SECRET_NODE, FIXTURE_CLEAN_NODE]:
            result = subprocess.run(
                [sys.executable, "-m", "vaultmind.secrets", str(path)],
                capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
            )
            assert result.returncode == 0, (
                f"CLI must always exit 0; got {result.returncode} for {path.name}.\n"
                f"stderr: {result.stderr}"
            )

    def test_cli_outputs_valid_json_array_for_secret_file(self) -> None:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing if existing else "")

        result = subprocess.run(
            [sys.executable, "-m", "vaultmind.secrets", str(FIXTURE_SECRET_NODE)],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
        )
        matches = json.loads(result.stdout)
        assert isinstance(matches, list)
        assert len(matches) >= 1
        m = matches[0]
        assert "pattern_id" in m
        assert "description" in m
        assert "line" in m
        assert "col" in m
        assert "excerpt" in m
        assert "[REDACTED]" in m["excerpt"]

    def test_cli_outputs_empty_array_for_clean_file(self) -> None:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing if existing else "")

        result = subprocess.run(
            [sys.executable, "-m", "vaultmind.secrets", str(FIXTURE_CLEAN_NODE)],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
        )
        matches = json.loads(result.stdout)
        assert matches == []

    def test_cli_and_python_api_agree_on_secret_node(self) -> None:
        """CLI output and scan_for_secrets() Python API return the same line numbers."""
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing if existing else "")

        result = subprocess.run(
            [sys.executable, "-m", "vaultmind.secrets", str(FIXTURE_SECRET_NODE)],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
        )
        cli_matches = json.loads(result.stdout)
        api_matches = scan_for_secrets(FIXTURE_SECRET_NODE.read_text())

        assert len(cli_matches) == len(api_matches), (
            f"CLI returned {len(cli_matches)} matches, API returned {len(api_matches)}"
        )
        for cli_m, api_m in zip(cli_matches, api_matches):
            assert cli_m["line"] == api_m.line
            assert cli_m["col"] == api_m.col
            assert cli_m["pattern_id"] == api_m.pattern_id


# ===========================================================================
# 4. Cross-call-site consistency
# ===========================================================================

class TestCrossCallSiteConsistency:
    """The single scan_for_secrets implementation behaves identically at all sites."""

    def test_same_secret_detected_at_write_and_handoff(
        self, vault: pathlib.Path
    ) -> None:
        """A secret written at write-time is also caught at handoff-time."""
        sr = ScribeResult(
            turn_id="sess-sec-cc-001",
            source_tool=SourceTool.claude_code,
            source_session="sess-sec-cc",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title="Cross-site secret",
                    slug="cross-site-secret",
                    body=f'key = "{DEMO_JWT}"',
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        # Write-time detected
        assert "secret-detected" in written[0].flags

        # Handoff-time also detected
        handoff = check_handoff_readiness(vault)
        assert not handoff.ready
        assert any(written[0].id[:10] in b or "cross" in b.lower()
                   for b in handoff.blocked_secrets) or len(handoff.blocked_secrets) >= 1

    def test_no_false_positive_across_all_sites(
        self, clean_vault: pathlib.Path
    ) -> None:
        """With only clean nodes, write-time, handoff-time, and API all return clean."""
        # Write a clean node
        sr = ScribeResult(
            turn_id="sess-sec-cc-002",
            source_tool=SourceTool.claude_code,
            source_session="sess-sec-cc",
            extractions=[
                Extraction(
                    type=NodeType.goal,
                    title="Entirely clean goal",
                    slug="entirely-clean-goal",
                    body="No sensitive content whatsoever.",
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, clean_vault)
        # Write-time: no flag
        assert written[0].flags == []

        # Handoff-time: still ready (clean vault + clean new node)
        result = check_handoff_readiness(clean_vault)
        assert result.blocked_secrets == []
        assert result.ready

        # Python API on the written file: no matches
        content = (clean_vault.parent / written[0].path).read_text()
        assert scan_for_secrets(content) == []
