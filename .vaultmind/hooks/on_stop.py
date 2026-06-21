"""
.vaultmind/hooks/on_stop.py — P1 stub hook (Stop event).

Invoked by Claude Code and Codex after every turn via the Stop hook.
Hook config references:
  .claude/settings.json  → hooks.Stop[].command
  .codex/hooks.json      → hooks.Stop[].command

P1 (Ingestion stream) replaces this stub with the real implementation:
  - Read turn_text from hook stdin (JSON: {session_id, turn_id, transcript_path, ...})
  - Produce a QueueItem to Redis Stream vaultmind:turns via XADD
  - Must stay minimal and always succeed (even if Redis is unavailable) so the
    developer's tool is never blocked by a watcher failure.

AC-6 constraints:
  - transcript_path may be null on Codex — handle gracefully
  - This hook runs synchronously on Codex (async:true is ignored there)
  - Never create the vaultmind-workers consumer group — that is the watcher's job
  - Always exit 0; a non-zero exit blocks the developer's tool turn

Stdin format (from Claude Code / Codex hook protocol):
  JSON object with at least: session_id, turn_id, transcript_path (str|null),
  user_text, assistant_text (or equivalent turn fields — confirm at build time).
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
        # Malformed stdin — log and exit cleanly so the tool isn't blocked.
        sys.stderr.write("on_stop.py: failed to parse hook stdin; skipping.\n")
        sys.exit(0)

    # TODO (P1): extract turn fields and enqueue a QueueItem to vaultmind:turns.
    # Skeleton: just log the turn_id so the hook is exercisable during Bucket 5.
    turn_id = payload.get("turn_id", "unknown")
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    sys.stderr.write(f"on_stop.py [stub]: turn {turn_id!r} at {ts} — P1 not yet wired\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
