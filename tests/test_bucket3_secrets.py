"""
tests/test_bucket3_secrets.py

Bucket-3 Track B gate — tests for all three call-site behaviors of scanForSecrets:

  1. write-time  : scan_for_secrets(content) returns SecretMatch list; clean → []
  2. commit-time : pre-commit hook exits 1 on staged vault/ secret; exits 0 when clean
  3. handoff-time: python -m vaultmind.secrets <path> always exits 0, prints JSON array

Additional checks:
  - masking: excerpt contains [REDACTED], never the literal secret value
  - pattern coverage: the seeded demo JWT is detected

No external dependencies — pure stdlib only.
Runner: python3 tests/test_bucket3_secrets.py
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap

REPO_ROOT = pathlib.Path(__file__).parent.parent

# The seeded demo JWT — a real-looking but entirely inert fixture value.
# This is NOT a real key and will never be used to access any service.
DEMO_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNjMwMDAwMDAwLCJleHAiOjE5OTk5OTk5OTl9"
    ".DEMO_SIGNATURE_PLACEHOLDER_NOT_A_REAL_KEY"
)

CONTENT_WITH_JWT = f'service_role_key = "{DEMO_JWT}"\n'
CONTENT_CLEAN = "# This file has no secrets.\nsome_value = 42\n"

# Path to the pre-commit shell script (committed copy).
HOOK_SCRIPT = REPO_ROOT / "vaultmind" / "hooks" / "pre-commit.sh"

# Path to the seeded fixture node that must be detected.
FIXTURE_SECRET_NODE = (
    REPO_ROOT / "fixtures" / "vault" / "nodes" / "2026-06-21-1408-supabase-keys.md"
)
FIXTURE_CLEAN_NODE = (
    REPO_ROOT / "fixtures" / "vault" / "nodes" / "2026-06-21-1432-supabase-rls-policies.md"
)


# ---------------------------------------------------------------------------
# Lazy import helper — Track A may not be finished when this file is written,
# so we import at call-time inside each test, not at module load, so that a
# missing vaultmind.secrets doesn't prevent the file from being parsed.
# ---------------------------------------------------------------------------

def _import_secrets():
    """Import scan_for_secrets and SecretMatch from vaultmind.secrets."""
    # Make sure repo root is on sys.path so `vaultmind` package is importable.
    repo_str = str(REPO_ROOT)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
    from vaultmind.secrets import scan_for_secrets, SecretMatch  # noqa: PLC0415
    return scan_for_secrets, SecretMatch


# ---------------------------------------------------------------------------
# 1. Write-time behavior
# ---------------------------------------------------------------------------

def test_write_time_match() -> None:
    """scan_for_secrets on content containing the demo JWT returns ≥1 SecretMatch."""
    scan_for_secrets, SecretMatch = _import_secrets()
    matches = scan_for_secrets(CONTENT_WITH_JWT)
    assert len(matches) > 0, (
        f"Expected at least one SecretMatch for content containing the demo JWT, got []"
    )
    m = matches[0]
    assert isinstance(m, SecretMatch), f"Expected SecretMatch instance, got {type(m)}"
    assert m.line == 1, f"Expected match on line 1, got line {m.line}"
    assert m.col >= 1, f"Expected col >= 1, got {m.col}"
    assert m.pattern_id, f"pattern_id must be a non-empty string"
    assert m.description, f"description must be a non-empty string"


def test_write_time_clean() -> None:
    """scan_for_secrets on clean content returns an empty list."""
    scan_for_secrets, _SecretMatch = _import_secrets()
    matches = scan_for_secrets(CONTENT_CLEAN)
    assert matches == [], f"Expected [] for clean content, got {matches}"


# ---------------------------------------------------------------------------
# 2. Commit-time behavior (pre-commit hook)
# ---------------------------------------------------------------------------

def _run_hook_in_temp_repo(vault_file_content: str | None) -> subprocess.CompletedProcess:
    """
    Create a temp git repo with a vault/ file, stage it, and run the pre-commit hook.

    If vault_file_content is None, no vault/ file is staged (hook should exit 0).
    Returns the CompletedProcess for the hook run.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)

        # Initialise a bare git repo in the temp directory.
        subprocess.run(
            ["git", "init", str(tmp)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp), "config", "user.email", "test@vaultmind.test"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp), "config", "user.name", "VaultMind Test"],
            check=True, capture_output=True,
        )

        if vault_file_content is not None:
            vault_dir = tmp / "vault" / "nodes"
            vault_dir.mkdir(parents=True)
            secret_file = vault_dir / "test-node.md"
            secret_file.write_text(vault_file_content, encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(tmp), "add", "vault/nodes/test-node.md"],
                check=True, capture_output=True,
            )

        # Run the pre-commit hook script directly (not via git commit) so we
        # don't need a committed tree.  Set GIT_DIR so git commands inside the
        # script resolve to our temp repo, and set the working directory to tmp
        # so relative `vault/` paths resolve correctly.
        env = os.environ.copy()
        env["GIT_DIR"] = str(tmp / ".git")
        env["GIT_WORK_TREE"] = str(tmp)
        # Ensure the vaultmind package is importable from within the hook.
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(REPO_ROOT) + (":" + existing_pythonpath if existing_pythonpath else "")
        )

        result = subprocess.run(
            ["bash", str(HOOK_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(tmp),
            env=env,
        )
        return result


def test_commit_hook_blocks() -> None:
    """Pre-commit hook exits 1 when a staged vault/ file contains the demo JWT."""
    result = _run_hook_in_temp_repo(CONTENT_WITH_JWT)
    assert result.returncode == 1, (
        f"Expected hook to exit 1 (blocked) but got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "Commit blocked" in combined, (
        f"Expected 'Commit blocked' message in hook output, got:\n{combined}"
    )


def test_commit_hook_passes() -> None:
    """Pre-commit hook exits 0 when staged vault/ file contains no secrets."""
    result = _run_hook_in_temp_repo(CONTENT_CLEAN)
    assert result.returncode == 0, (
        f"Expected hook to exit 0 (pass) but got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# 3. Handoff-time behavior (CLI: python -m vaultmind.secrets <path>)
# ---------------------------------------------------------------------------

def _run_cli(path: pathlib.Path) -> subprocess.CompletedProcess:
    """Run `python3 -m vaultmind.secrets <path>` and return the result."""
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) + (":" + existing_pythonpath if existing_pythonpath else "")
    )
    return subprocess.run(
        [sys.executable, "-m", "vaultmind.secrets", str(path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )


def test_cli_exit_code() -> None:
    """python -m vaultmind.secrets always exits 0 regardless of whether secrets are found."""
    # Test with the seeded secret fixture (has a secret → must still exit 0).
    result = _run_cli(FIXTURE_SECRET_NODE)
    assert result.returncode == 0, (
        f"CLI must always exit 0 (AC-5 invariant) but exited {result.returncode}.\n"
        f"stderr: {result.stderr}"
    )
    # Also verify exit 0 on a clean file.
    result_clean = _run_cli(FIXTURE_CLEAN_NODE)
    assert result_clean.returncode == 0, (
        f"CLI must always exit 0 on clean file but exited {result_clean.returncode}.\n"
        f"stderr: {result_clean.stderr}"
    )


def test_cli_json_output() -> None:
    """CLI prints a valid JSON array; array is non-empty for the seeded secret node."""
    # Secret file → non-empty JSON array.
    result = _run_cli(FIXTURE_SECRET_NODE)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"CLI stdout is not valid JSON: {e}\nstdout: {result.stdout!r}"
        ) from e
    assert isinstance(data, list), f"CLI must print a JSON array, got {type(data)}"
    assert len(data) > 0, (
        f"Expected non-empty JSON array for the seeded secret fixture, got []"
    )
    # Verify each element has the required SecretMatch fields.
    required_fields = {"pattern_id", "description", "line", "col", "excerpt"}
    for i, item in enumerate(data):
        missing = required_fields - set(item.keys())
        assert not missing, (
            f"Match[{i}] is missing fields {missing}. Got keys: {set(item.keys())}"
        )

    # Clean file → empty JSON array [].
    result_clean = _run_cli(FIXTURE_CLEAN_NODE)
    try:
        data_clean = json.loads(result_clean.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"CLI stdout for clean file is not valid JSON: {e}\nstdout: {result_clean.stdout!r}"
        ) from e
    assert data_clean == [], (
        f"Expected [] for clean fixture node, got {data_clean}"
    )


# ---------------------------------------------------------------------------
# 4. Masking — excerpt must never contain the literal secret value
# ---------------------------------------------------------------------------

def test_masking() -> None:
    """The excerpt field in every SecretMatch contains [REDACTED], not the literal secret."""
    scan_for_secrets, _SecretMatch = _import_secrets()
    matches = scan_for_secrets(CONTENT_WITH_JWT)
    assert len(matches) > 0, "Need at least one match to test masking"
    for m in matches:
        assert DEMO_JWT not in m.excerpt, (
            f"excerpt must not contain the literal secret value.\n"
            f"excerpt: {m.excerpt!r}"
        )
        assert "[REDACTED]" in m.excerpt, (
            f"excerpt must contain [REDACTED].\nexcerpt: {m.excerpt!r}"
        )


# ---------------------------------------------------------------------------
# 5. Pattern coverage — demo JWT is detected
# ---------------------------------------------------------------------------

def test_pattern_coverage_demo_jwt() -> None:
    """The seeded demo JWT string is detected by scan_for_secrets."""
    scan_for_secrets, _SecretMatch = _import_secrets()
    # Test both inline and as a value in a config-style line.
    for content in [
        DEMO_JWT,
        CONTENT_WITH_JWT,
        f"# Some markdown\n{CONTENT_WITH_JWT}\nmore text\n",
    ]:
        matches = scan_for_secrets(content)
        assert len(matches) > 0, (
            f"Expected the demo JWT to be detected in content:\n{content!r}\nGot no matches."
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> None:
    tests = [
        test_write_time_match,
        test_write_time_clean,
        test_cli_exit_code,
        test_cli_json_output,
        test_masking,
        test_commit_hook_blocks,
        test_commit_hook_passes,
        test_pattern_coverage_demo_jwt,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS: {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR: {t.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print()
    if failed:
        print(f"RESULT: {failed} failure(s) — Bucket 3 gate FAILED")
        sys.exit(1)
    else:
        print("RESULT: all checks passed — Bucket 3 gate PASSED ✓")
        sys.exit(0)


if __name__ == "__main__":
    run_all()
