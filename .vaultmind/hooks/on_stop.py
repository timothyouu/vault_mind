"""
.vaultmind/hooks/on_stop.py — Stop hook for Claude Code and Codex.

Called after every turn. Reads new turns from transcript, enqueues
to Redis, updates cursor. Always exits 0 — never blocks the session.
"""
from __future__ import annotations

import json
import os
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id      = payload.get("session_id", "unknown")
    transcript_path = payload.get("transcript_path")   # None on Codex
    redis_url       = os.environ.get("REDIS_URL", "redis://localhost:6379")

    try:
        from vaultmind.ingest import cursor as _cursor
        from vaultmind.ingest import reader as _reader
        from vaultmind.ingest import producer as _producer
        from vaultmind.ingest import session_state as _ss
        from vaultmind.contracts import SourceTool
    except Exception as exc:
        sys.stderr.write(f"on_stop.py: import error: {exc}\n")
        sys.exit(0)

    last_uuid = _cursor.load(session_id)
    turns, flags = _reader.parse(transcript_path, last_uuid)

    for t in turns:
        _producer.enqueue(
            t.turn_text, session_id, transcript_path,
            SourceTool.claude_code, redis_url,
        )

    if turns:
        try:
            _cursor.save(session_id, turns[-1].uuid)
        except Exception as exc:
            sys.stderr.write(f"on_stop.py: cursor save failed: {exc}\n")
        _ss.turn_enqueued(session_id, len(turns), flags)

    sys.exit(0)


if __name__ == "__main__":
    main()
