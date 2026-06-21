from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


_LOCK_TIMEOUT = 10.0


def _vault_root() -> Path:
    return Path(os.environ.get("VAULTMIND_VAULT_ROOT", "./vault"))


def _session_state_path() -> Path:
    return _vault_root() / "SessionState.md"


def _lock_path() -> Path:
    return _vault_root().parent / ".vaultmind" / "session_state.lock"


def _acquire_lock() -> None:
    lock = _lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if time.monotonic() > deadline:
                lock.unlink(missing_ok=True)
                continue
            time.sleep(0.05)


def _release_lock() -> None:
    _lock_path().unlink(missing_ok=True)


def _append(line: str) -> None:
    _acquire_lock()
    try:
        p = _session_state_path()
        current = p.read_text(encoding="utf-8") if p.exists() else ""
        new_content = (current.rstrip("\n") + "\n" + line + "\n").lstrip("\n")
        tmp = p.with_suffix(".tmp")
        tmp.write_text(new_content, encoding="utf-8")
        os.replace(tmp, p)
    finally:
        _release_lock()


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def turn_enqueued(session_id: str, count: int, flags: list[str]) -> None:
    parts = [f"- {_ts()} · claude-code · {count} turn(s) enqueued"]
    if "post-compaction" in flags:
        parts.append("⚠ post-compaction")
    try:
        _append(" ".join(parts))
    except Exception as exc:
        sys.stderr.write(f"session_state: write failed: {exc}\n")


def session_ended(session_id: str, reason: str) -> None:
    try:
        _append(f"- {_ts()} · claude-code · session ended (reason: {reason})")
    except Exception as exc:
        sys.stderr.write(f"session_state: write failed: {exc}\n")


def context_compacted(session_id: str) -> None:
    try:
        _append(f"- {_ts()} · claude-code · ⚠ context compacted")
    except Exception as exc:
        sys.stderr.write(f"session_state: write failed: {exc}\n")
