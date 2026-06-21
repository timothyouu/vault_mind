"""
.vaultmind/hooks/on_session_end.py — SessionEnd hook for Claude Code.

Called when the Claude Code session ends. Logs the event to
SessionState.md. Always exits 0.
"""
from __future__ import annotations

import json
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id = payload.get("session_id", "unknown")
    reason     = payload.get("reason", "other")

    try:
        from vaultmind.ingest import session_state as _ss
        _ss.session_ended(session_id, reason)
    except Exception as exc:
        sys.stderr.write(f"on_session_end.py: unexpected error: {exc}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
