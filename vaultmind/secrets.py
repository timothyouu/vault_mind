"""
One implementation of scanForSecrets. Never add a second.

Used at:
  - write-time   : Note Creator (hot path) — flags node, does NOT block
  - commit-time  : pre-commit hook reads JSON output, exits 1 itself on match
  - handoff-time : Orchestrator + web app subprocess — blocks handoff

CLI contract:
  python -m vaultmind.secrets <path>
  Always exits 0 (clean or matches); prints a JSON array to stdout.
  The pre-commit hook reads the JSON and exits 1 itself — never change the exit code here.
"""

from __future__ import annotations

import importlib.resources
import json
import re
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SecretMatch:
    pattern_id: str
    description: str
    line: int       # 1-based
    col: int        # 1-based
    excerpt: str    # full line with the matched secret replaced by [REDACTED]


# ---------------------------------------------------------------------------
# Pattern loading — once at module import time
# ---------------------------------------------------------------------------

def _load_patterns() -> list[dict[str, Any]]:
    """Load secret-patterns.json via importlib.resources (bundled, cwd-independent)."""
    pkg = importlib.resources.files("vaultmind")
    data = (pkg / "secret-patterns.json").read_text(encoding="utf-8")
    return json.loads(data)


# Module-level singletons — loaded and compiled exactly once.
_PATTERNS: list[dict[str, Any]] = _load_patterns()

# Map pattern_id → compiled regex.  Compiled once; reused on every call.
_COMPILED: dict[str, re.Pattern[str]] = {
    p["pattern_id"]: re.compile(p["regex"])
    for p in _PATTERNS
}


# ---------------------------------------------------------------------------
# Excerpt masking
# ---------------------------------------------------------------------------

def _mask_excerpt(line_text: str, match: re.Match[str]) -> str:
    """Return the line with the matched secret replaced by [REDACTED]."""
    start, end = match.start(), match.end()
    return line_text[:start] + "[REDACTED]" + line_text[end:]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_for_secrets(content: str) -> list[SecretMatch]:
    """
    Scan *content* for known secret patterns.

    Returns an empty list when clean.
    No LLM calls; no I/O beyond the one-time pattern load at import.
    """
    matches: list[SecretMatch] = []

    lines = content.splitlines()

    for line_no, line_text in enumerate(lines, start=1):
        for pattern in _PATTERNS:
            pid = pattern["pattern_id"]
            regex = _COMPILED[pid]
            for m in regex.finditer(line_text):
                col = m.start() + 1  # 1-based
                excerpt = _mask_excerpt(line_text, m)
                matches.append(
                    SecretMatch(
                        pattern_id=pid,
                        description=pattern["description"],
                        line=line_no,
                        col=col,
                        excerpt=excerpt,
                    )
                )

    return matches


# ---------------------------------------------------------------------------
# CLI — python -m vaultmind.secrets <path>
# ALWAYS exits 0.  The pre-commit hook reads the JSON and exits 1 itself.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import pathlib

    if len(sys.argv) != 2:
        print("Usage: python -m vaultmind.secrets <path>", file=sys.stderr)
        sys.exit(0)  # always 0 per spec

    path = pathlib.Path(sys.argv[1])
    content = path.read_text(encoding="utf-8", errors="replace")
    found = scan_for_secrets(content)
    print(
        json.dumps(
            [
                {
                    "pattern_id": m.pattern_id,
                    "description": m.description,
                    "line": m.line,
                    "col": m.col,
                    "excerpt": m.excerpt,
                }
                for m in found
            ]
        )
    )
    sys.exit(0)  # ALWAYS 0 — the hook reads JSON and exits 1 itself
