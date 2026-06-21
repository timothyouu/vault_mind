from __future__ import annotations

import sys
import uuid as _uuid
from datetime import datetime, timezone

import redis as _redis

from vaultmind.contracts import QueueItem, SourceTool, TurnText


def enqueue(
    turn_text: TurnText,
    session_id: str,
    transcript_path: str | None,
    source_tool: SourceTool,
    redis_url: str,
) -> bool:
    try:
        r = _redis.from_url(redis_url, decode_responses=True)
        qi = QueueItem(
            turn_id=f"{session_id}-{_uuid.uuid4().hex[:8]}",
            session_id=session_id,
            source_tool=source_tool,
            transcript_path=transcript_path,
            turn_text=turn_text,
            enqueued_at=datetime.now(timezone.utc).isoformat(),
        )
        r.xadd("vaultmind:turns", {"data": qi.model_dump_json()})
        return True
    except Exception as exc:
        sys.stderr.write(f"producer: failed to enqueue for session {session_id}: {exc}\n")
        return False
