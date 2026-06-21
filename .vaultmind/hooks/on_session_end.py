"""
.vaultmind/hooks/on_session_end.py — P1 stub hook (SessionEnd event).

Invoked by Claude Code only (Codex has no SessionEnd hook — see AC-6) after a
session ends. Hook config reference:
  .claude/settings.json  → hooks.SessionEnd[].command  (async: true)

P1 (Ingestion stream) replaces this stub with the real implementation:
  - Append a "session ended" row to vault/SessionState.md (atomic write-temp-rename
    guarded by a .lock sentinel — see AC-2 shared-write handling)
  - The row format: "- YYYY-MM-DD HH:MM · <tool> · session ended (reason: <reason>)"
  - Publish a NodeChangedEvent(event="session-event") to vaultmind:events so the
    web app can trigger a Review Mode checkpoint

AC-6 constraints:
  - Claude Code provides reason ∈ clear|logout|prompt_input_exit|resume|
    bypass_permissions_disabled|other in the hook stdin payload
  - This hook runs async (async:true in .claude/settings.json); it must not block
    the Claude Code UI — it runs as a fire-and-forget side-effect
  - Codex never calls this hook; the idle-timeout heuristic in the watcher covers
    the Codex session-end case (no new Stop within 300 s)
  - Always exit 0

Stdin format (from Claude Code SessionEnd hook protocol):
  JSON object with at least: session_id, reason (str).
  Confirm exact field names at build time against the official hook reference.
"""

from __future__ import annotations

import json
import sys
import datetime


def main() -> None:
    # Read hook payload from stdin.
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.stderr.write("on_session_end.py: failed to parse hook stdin; skipping.\n")
        sys.exit(0)

    # TODO (P1): append "session ended" row to vault/SessionState.md and publish
    # a session-event NodeChangedEvent to vaultmind:events.
    # Skeleton: log the session_id and reason so the hook is exercisable during Bucket 5.
    session_id = payload.get("session_id", "unknown")
    reason = payload.get("reason", "unknown")
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    sys.stderr.write(
        f"on_session_end.py [stub]: session {session_id!r} ended "
        f"(reason={reason!r}) at {ts} — P1 not yet wired\n"
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
