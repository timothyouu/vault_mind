import shutil
import pytest
from pathlib import Path
from vaultmind.handoff import check_handoff_readiness, assemble_entry_point

FIXTURE_VAULT = Path(__file__).parent.parent / "fixtures" / "vault"


@pytest.fixture
def vault(tmp_path):
    dst = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, dst)
    return dst


@pytest.fixture
def clean_vault(tmp_path):
    dst = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, dst)
    # Remove the secret-detected node
    secret = dst / "nodes" / "2026-06-21-1408-supabase-keys.md"
    if secret.exists():
        secret.unlink()
    return dst


def test_blocked_when_secret_present(vault):
    result = check_handoff_readiness(vault)
    assert not result.ready
    assert len(result.blocked_secrets) > 0
    assert "supabase" in result.blocked_secrets[0].lower() or "secret" in result.blocked_secrets[0].lower() or "line" in result.blocked_secrets[0].lower()


def test_ready_when_no_secrets(clean_vault):
    result = check_handoff_readiness(clean_vault)
    assert result.blocked_secrets == []


def test_entry_point_mentions_intentlog(vault):
    entry = assemble_entry_point(vault)
    assert "IntentLog" in entry or "intent" in entry.lower()


def test_entry_point_mentions_vaultindex(vault):
    entry = assemble_entry_point(vault)
    assert "VaultIndex" in entry or "vault" in entry.lower()


def test_entry_point_includes_current_intent(vault):
    entry = assemble_entry_point(vault)
    # The fixture IntentLog has "Help me finish the auth flow"
    assert "auth flow" in entry or "intent" in entry.lower()
