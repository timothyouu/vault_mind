import os
import threading
import time
import pytest
from pathlib import Path
from vaultmind.ingest import session_state


@pytest.fixture
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    v.mkdir()
    monkeypatch.setenv("VAULTMIND_VAULT_ROOT", str(v))
    return v


def _read_state(vault: Path) -> str:
    p = vault / "SessionState.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_turn_enqueued_appends_line(vault):
    session_state.turn_enqueued("sess-1", 2, [])
    content = _read_state(vault)
    assert "2 turn(s) enqueued" in content


def test_turn_enqueued_with_compaction_flag(vault):
    session_state.turn_enqueued("sess-1", 1, ["post-compaction"])
    content = _read_state(vault)
    assert "post-compaction" in content


def test_session_ended_appends_line(vault):
    session_state.session_ended("sess-1", "clear")
    content = _read_state(vault)
    assert "session ended" in content
    assert "clear" in content


def test_context_compacted_appends_line(vault):
    session_state.context_compacted("sess-1")
    content = _read_state(vault)
    assert "context compacted" in content


def test_multiple_appends_produce_multiple_lines(vault):
    session_state.turn_enqueued("sess-1", 1, [])
    session_state.session_ended("sess-1", "logout")
    lines = [l for l in _read_state(vault).strip().splitlines() if l.strip()]
    assert len(lines) == 2


def test_creates_file_if_absent(vault):
    assert not (vault / "SessionState.md").exists()
    session_state.turn_enqueued("sess-1", 1, [])
    assert (vault / "SessionState.md").exists()


def test_concurrent_appends_no_corruption(vault):
    errors = []

    def append(n):
        try:
            session_state.turn_enqueued(f"sess-{n}", 1, [])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=append, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    lines = [l for l in _read_state(vault).strip().splitlines() if l.strip()]
    assert len(lines) == 8


def test_stale_lock_is_stolen(vault, monkeypatch):
    # Write a lock file with a timestamp far in the past
    lock = vault.parent / ".vaultmind" / "session_state.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("stale", encoding="utf-8")

    # Patch time so the lock appears older than the timeout
    original_monotonic = time.monotonic
    call_count = [0]

    def fast_monotonic():
        call_count[0] += 1
        # Return a time well past the deadline on the second call
        return original_monotonic() + (11 if call_count[0] > 1 else 0)

    monkeypatch.setattr(time, "monotonic", fast_monotonic)

    # Should succeed (steal the lock) without raising
    session_state.turn_enqueued("sess-1", 1, [])
    assert "turn(s) enqueued" in _read_state(vault)
