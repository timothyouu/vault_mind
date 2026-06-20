"""
tests/test_bucket2_parity.py

Bucket-2 deterministic gate — two checks that must pass before Bucket 5 live-fire:

  1. contracts.py ↔ types.ts field parity
     Every field on every Pydantic model in contracts.py must appear (by name)
     as a property in the mirrored TypeScript interface in webapp/types.ts.

  2. Fixture vault nodes parse against AC-1
     Every .md file under fixtures/vault/nodes/ must have valid frontmatter
     with all required fields and correctly-typed values per AC-1.

No external dependencies — pure stdlib (ast, re, json, pathlib) + yaml
(available in Ubuntu system Python 3).
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import pathlib
import re
import sys
import yaml

REPO_ROOT = pathlib.Path(__file__).parent.parent

CONTRACTS_PY = REPO_ROOT / "vaultmind" / "contracts.py"
TYPES_TS = REPO_ROOT / "webapp" / "types.ts"
FIXTURE_VAULT_NODES = REPO_ROOT / "fixtures" / "vault" / "nodes"
FIXTURE_VAULT = REPO_ROOT / "fixtures" / "vault"
FIXTURE_TRANSCRIPT = REPO_ROOT / "fixtures" / "transcript.jsonl"

# ---------------------------------------------------------------------------
# AC-1 required frontmatter fields and their expected Python types
# ---------------------------------------------------------------------------
REQUIRED_FM_FIELDS: dict[str, type | tuple[type, ...]] = {
    "id": str,
    "type": str,
    "title": str,
    # YAML parses ISO 8601 timestamps as datetime.datetime — accept both
    "created": (str, dt.datetime),
    "source_tool": str,
    "source_session": str,
    "intent_ref": str,
    "status": str,
    "related": list,
    "flags": list,
}

VALID_NODE_TYPES = {"decision", "constraint", "goal", "question", "scope"}
VALID_STATUSES = {"pending", "approved"}
VALID_SOURCE_TOOLS = {"claude-code", "codex"}


# ---------------------------------------------------------------------------
# Helper: extract Pydantic model fields from contracts.py
# ---------------------------------------------------------------------------

def extract_pydantic_fields(source: str) -> dict[str, list[str]]:
    """
    Returns {ClassName: [field_name, ...]} for every class that inherits
    from BaseModel in the source.
    """
    tree = ast.parse(source)
    models: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # Check if it inherits from BaseModel (directly or as a dotted name)
        bases = [
            (b.id if isinstance(b, ast.Name) else
             b.attr if isinstance(b, ast.Attribute) else None)
            for b in node.bases
        ]
        if "BaseModel" not in bases:
            continue
        fields = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.append(item.target.id)
        models[node.name] = fields
    return models


# ---------------------------------------------------------------------------
# Helper: extract TypeScript interface fields from types.ts
# ---------------------------------------------------------------------------

def extract_ts_interface_fields(source: str) -> dict[str, list[str]]:
    """
    Returns {InterfaceName: [field_name, ...]} for every `interface` in source.
    Also returns type alias names (but not their fields) so we can confirm presence.
    """
    interfaces: dict[str, list[str]] = {}
    # Match interface blocks
    interface_pattern = re.compile(
        r'export\s+interface\s+(\w+)\s*\{([^}]+)\}', re.DOTALL
    )
    field_pattern = re.compile(r'^\s*(?:readonly\s+)?(\w+)\??:', re.MULTILINE)
    for m in interface_pattern.finditer(source):
        name = m.group(1)
        body = m.group(2)
        fields = field_pattern.findall(body)
        interfaces[name] = fields
    return interfaces


# ---------------------------------------------------------------------------
# Check 1: contracts.py ↔ types.ts field parity
# ---------------------------------------------------------------------------

def check_parity() -> list[str]:
    """
    Returns a list of error strings. Empty = parity confirmed.

    Strategy: for each Pydantic model in contracts.py, find the corresponding
    TypeScript interface (by name) in types.ts and assert all Python field names
    appear as TS interface fields.

    Some models (TurnText, Extraction) are nested — they must also appear.
    Enum classes are skipped (they don't inherit BaseModel).
    """
    errors: list[str] = []
    py_source = CONTRACTS_PY.read_text()
    ts_source = TYPES_TS.read_text()

    py_models = extract_pydantic_fields(py_source)
    ts_interfaces = extract_ts_interface_fields(ts_source)

    for model_name, py_fields in py_models.items():
        if model_name not in ts_interfaces:
            errors.append(
                f"MISSING TS interface: '{model_name}' is a Pydantic model in "
                f"contracts.py but has no matching TypeScript interface in types.ts"
            )
            continue
        ts_fields = ts_interfaces[model_name]
        for field in py_fields:
            if field not in ts_fields:
                errors.append(
                    f"MISSING TS field: '{model_name}.{field}' exists in contracts.py "
                    f"but not in the TypeScript interface 'webapp/types.ts'"
                )

    return errors


# ---------------------------------------------------------------------------
# Check 2: fixture vault nodes parse against AC-1
# ---------------------------------------------------------------------------

def parse_frontmatter(md_content: str) -> dict | None:
    """
    Parse YAML frontmatter from a markdown file.
    Returns the frontmatter dict or None if not present.
    """
    if not md_content.startswith("---"):
        return None
    end = md_content.find("\n---", 3)
    if end == -1:
        return None
    fm_text = md_content[3:end].strip()
    return yaml.safe_load(fm_text)


def check_fixture_nodes() -> list[str]:
    """
    Returns a list of error strings. Empty = all fixture nodes are AC-1 compliant.
    """
    errors: list[str] = []

    node_files = list(FIXTURE_VAULT_NODES.glob("*.md"))
    if not node_files:
        errors.append("No fixture node files found in fixtures/vault/nodes/")
        return errors

    for md_file in sorted(node_files):
        content = md_file.read_text()
        fm = parse_frontmatter(content)
        if fm is None:
            errors.append(f"{md_file.name}: missing or malformed YAML frontmatter")
            continue

        # Required fields present and correct type
        for field, expected_type in REQUIRED_FM_FIELDS.items():
            if field not in fm:
                errors.append(f"{md_file.name}: missing required field '{field}'")
            elif not isinstance(fm[field], expected_type):
                errors.append(
                    f"{md_file.name}: field '{field}' should be {expected_type.__name__} "
                    f"but got {type(fm[field]).__name__}"
                )

        # Enum checks
        if "type" in fm and fm["type"] not in VALID_NODE_TYPES:
            errors.append(
                f"{md_file.name}: invalid type '{fm['type']}' (must be one of {VALID_NODE_TYPES})"
            )
        if "status" in fm and fm["status"] not in VALID_STATUSES:
            errors.append(
                f"{md_file.name}: invalid status '{fm['status']}' (must be pending|approved)"
            )
        if "source_tool" in fm and fm["source_tool"] not in VALID_SOURCE_TOOLS:
            errors.append(
                f"{md_file.name}: invalid source_tool '{fm['source_tool']}'"
            )

        # id == basename without .md
        if "id" in fm and fm["id"] != md_file.stem:
            errors.append(
                f"{md_file.name}: frontmatter id '{fm['id']}' != filename stem '{md_file.stem}'"
            )

        # related must be a list of strings that look like wikilinks
        if "related" in fm and isinstance(fm["related"], list):
            for link in fm["related"]:
                if not isinstance(link, str):
                    errors.append(f"{md_file.name}: related entry {link!r} is not a string")
                elif not (link.startswith("[[") and link.endswith("]]")):
                    errors.append(
                        f"{md_file.name}: related entry {link!r} is not a [[wikilink]]"
                    )

        # body must not be empty
        body_start = content.find("\n---", 3)
        if body_start != -1:
            body = content[body_start + 4:].strip()
            if not body:
                errors.append(f"{md_file.name}: body is empty")

    return errors


# ---------------------------------------------------------------------------
# Check 3: scope anchor files exist and parse
# ---------------------------------------------------------------------------

def check_scope_anchors() -> list[str]:
    errors: list[str] = []
    for anchor in ("ProjectGoal.md", "Constraints.md", "TechStack.md"):
        p = FIXTURE_VAULT / anchor
        if not p.exists():
            errors.append(f"Missing scope anchor: fixtures/vault/{anchor}")
            continue
        fm = parse_frontmatter(p.read_text())
        if fm is None:
            errors.append(f"{anchor}: missing frontmatter")
            continue
        if fm.get("type") != "scope":
            errors.append(f"{anchor}: expected type=scope, got {fm.get('type')!r}")

    for fname in ("IntentLog.md", "VaultIndex.md", "SessionState.md"):
        p = FIXTURE_VAULT / fname
        if not p.exists():
            errors.append(f"Missing fixture file: fixtures/vault/{fname}")

    return errors


# ---------------------------------------------------------------------------
# Check 4: fixture transcript.jsonl has 4 lines each valid QueueItem shape
# ---------------------------------------------------------------------------

def check_fixture_transcript() -> list[str]:
    errors: list[str] = []
    lines = FIXTURE_TRANSCRIPT.read_text().strip().splitlines()
    if len(lines) != 4:
        errors.append(
            f"fixtures/transcript.jsonl: expected 4 lines (turns), got {len(lines)}"
        )

    required_qi_fields = {
        "turn_id", "source_tool", "session_id",
        "transcript_path", "turn_text", "enqueued_at"
    }
    for i, line in enumerate(lines, 1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"transcript.jsonl line {i}: JSON parse error: {e}")
            continue
        for field in required_qi_fields:
            if field not in obj:
                errors.append(f"transcript.jsonl line {i}: missing field '{field}'")
        if "turn_text" in obj:
            tt = obj["turn_text"]
            if not isinstance(tt, dict):
                errors.append(f"transcript.jsonl line {i}: turn_text must be a dict")
            else:
                for sub in ("user", "assistant"):
                    if sub not in tt:
                        errors.append(
                            f"transcript.jsonl line {i}: turn_text missing '{sub}'"
                        )

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    all_errors: list[str] = []

    print("=== Check 1: contracts.py ↔ types.ts field parity ===")
    errs = check_parity()
    if errs:
        all_errors.extend(errs)
        for e in errs:
            print(f"  FAIL: {e}")
    else:
        print("  PASS: all Pydantic model fields mirrored in TypeScript interfaces")

    print()
    print("=== Check 2: fixture vault nodes parse against AC-1 ===")
    errs = check_fixture_nodes()
    if errs:
        all_errors.extend(errs)
        for e in errs:
            print(f"  FAIL: {e}")
    else:
        print(f"  PASS: all fixture nodes are AC-1 compliant")

    print()
    print("=== Check 3: scope anchors + required vault files ===")
    errs = check_scope_anchors()
    if errs:
        all_errors.extend(errs)
        for e in errs:
            print(f"  FAIL: {e}")
    else:
        print("  PASS: all scope anchors and required vault files present")

    print()
    print("=== Check 4: fixture transcript.jsonl shape ===")
    errs = check_fixture_transcript()
    if errs:
        all_errors.extend(errs)
        for e in errs:
            print(f"  FAIL: {e}")
    else:
        print("  PASS: transcript.jsonl has 4 well-formed QueueItem lines")

    print()
    if all_errors:
        print(f"RESULT: {len(all_errors)} error(s) — Bucket 2 gate FAILED")
        return 1
    else:
        print("RESULT: all checks passed — Bucket 2 gate PASSED ✓")
        return 0


if __name__ == "__main__":
    sys.exit(main())
