import json
import os
import pytest
from pathlib import Path
from vaultmind.ingest import cursor


@pytest.fixture
def cursors_dir(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("VAULTMIND_VAULT_ROOT", str(vault))
    return tmp_path / ".vaultmind" / "cursors"


def test_load_returns_none_when_no_cursor(cursors_dir):
    assert cursor.load("session-abc") is None


def test_roundtrip(cursors_dir):
    cursor.save("session-abc", "uuid-1234")
    assert cursor.load("session-abc") == "uuid-1234"


def test_save_overwrites(cursors_dir):
    cursor.save("session-abc", "uuid-1")
    cursor.save("session-abc", "uuid-2")
    assert cursor.load("session-abc") == "uuid-2"


def test_load_returns_none_on_corrupt_file(cursors_dir, tmp_path):
    cursors_dir.mkdir(parents=True)
    (cursors_dir / "session-bad.json").write_text("not json")
    assert cursor.load("session-bad") is None


def test_atomic_write_uses_replace(cursors_dir, monkeypatch):
    # Verify no .tmp file is left behind after a successful save
    cursor.save("session-abc", "uuid-xyz")
    assert not (cursors_dir / "session-abc.tmp").exists()
    assert (cursors_dir / "session-abc.json").exists()
