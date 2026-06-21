from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _cursors_dir() -> Path:
    vault_root = Path(os.environ.get("VAULTMIND_VAULT_ROOT", "./vault"))
    return vault_root.parent / ".vaultmind" / "cursors"


def load(session_id: str) -> str | None:
    path = _cursors_dir() / f"{session_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("last_uuid")
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def save(session_id: str, last_uuid: str) -> None:
    d = _cursors_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{session_id}.json"
    tmp = d / f"{session_id}.tmp"
    payload = {
        "last_uuid": last_uuid,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)
