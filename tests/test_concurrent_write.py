import threading
import pytest
from pathlib import Path
from vaultmind.notecreator import append_intentlog_entry


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    return v


def test_concurrent_intentlog_appends_no_clobber(vault):
    """
    Two simultaneous appends to IntentLog.md must not clobber each other.
    The atomic-rename + .lock sentinel must hold.
    Exactly N entries must exist after N concurrent writes.
    """
    N = 8
    errors = []

    def do_append(i):
        try:
            append_intentlog_entry(
                vault,
                intent_text=f"intent-{i}",
                tool="claude-code",
                origin="ai-detected",
            )
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=do_append, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Errors: {errors}"
    content = (vault / "IntentLog.md").read_text()
    # Exactly one entry should be marked Current
    assert content.count("— Current") == 1
    # All N intents appear
    for i in range(N):
        assert f"intent-{i}" in content


def test_current_marker_moves_to_newest(vault):
    append_intentlog_entry(vault, "first intent", "claude-code", "developer")
    append_intentlog_entry(vault, "second intent", "claude-code", "developer")

    content = (vault / "IntentLog.md").read_text()
    lines = content.splitlines()

    # The Current marker should be on a heading above the "second intent" line
    current_heading_idx = next(
        (i for i, l in enumerate(lines) if "— Current" in l), -1
    )
    second_content_idx = next(
        (i for i, l in enumerate(lines) if "second intent" in l), -1
    )
    assert current_heading_idx != -1
    assert second_content_idx != -1
    assert current_heading_idx < second_content_idx
