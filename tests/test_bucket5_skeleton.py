"""
tests/test_bucket5_skeleton.py — Walking skeleton gate (Bucket 5).

Wires the stubs end-to-end using fakeredis (in-process Redis emulation).
Demonstrates all seven Bucket-5 DoD items plus the failure-visibility
secondary check, with no real Redis or network required.

Run: python3 tests/test_bucket5_skeleton.py   (from repo root, with .venv active)

DoD items verified:
  1. Fixture turn → real QueueItem in vaultmind:turns (XRANGE)
  2. Watcher consumes via consumer group and XACKs (XPENDING drains)
  3. Stub Scribe → NoteCreator writes a real vault/nodes/*.md that parses AC-1
  4. NoteCreator → stub Connector populates `related`
  5. Connector publishes node-changed on vaultmind:events
  6. SSE pub/sub contract: a subscriber on vaultmind:events receives the exact
     JSON the Connector published (Next.js SSE runtime verified during live-fire)
  7. Orchestrator in-flight table shows turn reaching `done` via TurnProgress

Secondary (failure-visibility):
  S1. Kill Connector after NoteCreator writes → QueueItem stays in XPENDING
  S2. Orchestrator flags turn `stuck` after timeout (simulated with past timestamp)
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys
import tempfile
import threading
import time

# ---------------------------------------------------------------------------
# fakeredis — requires FakeServer for pub/sub across two clients
# ---------------------------------------------------------------------------
try:
    import fakeredis
    _FAKE_SERVER = fakeredis.FakeServer()
except ImportError:
    print("FATAL: fakeredis not installed. Run: uv pip install fakeredis")
    sys.exit(1)

# ---------------------------------------------------------------------------
# vaultmind imports
# ---------------------------------------------------------------------------
REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from vaultmind.contracts import (
    QueueItem, TurnText, SourceTool, TurnStage,
)
import vaultmind.watcher as watcher_mod
from vaultmind.watcher import (
    STREAM_TURNS, CHANNEL_PROGRESS, CHANNEL_EVENTS, GROUP_NAME,
    _ensure_consumer_group, _process_message,
)
# Legacy aliases so existing test code that references the old names still works.
STREAM_PROGRESS = CHANNEL_PROGRESS
STREAM_EVENTS = CHANNEL_EVENTS

# ---------------------------------------------------------------------------
# Shared FakeServer client factory
# ---------------------------------------------------------------------------

def _r() -> fakeredis.FakeRedis:
    """Return a FakeRedis client connected to the shared FakeServer."""
    return fakeredis.FakeRedis(server=_FAKE_SERVER, decode_responses=True)


def _fresh_server() -> fakeredis.FakeServer:
    """Return a fresh isolated FakeServer for tests that need isolation."""
    return fakeredis.FakeServer()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_fixture_turn(line_no: int = 0) -> QueueItem:
    """Load turn N (0-indexed) from fixtures/transcript.jsonl."""
    transcript = REPO_ROOT / "fixtures" / "transcript.jsonl"
    lines = transcript.read_text().strip().splitlines()
    raw = json.loads(lines[line_no])
    return QueueItem.model_validate(raw)


def _enqueue(r: fakeredis.FakeRedis, qi: QueueItem) -> str:
    """Push a QueueItem onto the vaultmind:turns stream. Returns msg id."""
    return r.xadd(STREAM_TURNS, {"data": qi.model_dump_json()})


def _run_one_turn(server: fakeredis.FakeServer, qi: QueueItem,
                  vault_root: pathlib.Path) -> None:
    """
    Full pipeline for one turn using the given FakeServer:
      1. Enqueue QueueItem
      2. Read via consumer group
      3. _process_message (scribe→notecreator→connector→ack)
    """
    r = fakeredis.FakeRedis(server=server, decode_responses=True)
    _ensure_consumer_group(r)
    _enqueue(r, qi)
    messages = r.xreadgroup(GROUP_NAME, "test-consumer",
                             {STREAM_TURNS: ">"}, count=1)
    assert messages, "No messages delivered to consumer group"
    stream_name, entries = messages[0]
    for msg_id, fields in entries:
        _process_message(r, msg_id, fields, vault_root)


# ---------------------------------------------------------------------------
# In-flight tracker (minimal Orchestrator stub)
# ---------------------------------------------------------------------------

class InFlightTracker:
    """
    Subscribes to vaultmind:progress; records last stage per turn_id.
    Flags turns `stuck` when asked to check.
    Uses a dedicated subscriber client on the same FakeServer.
    """

    def __init__(self, server: fakeredis.FakeServer, stuck_timeout_s: float = 5.0):
        self._table: dict[str, dict] = {}
        self._timeout = stuck_timeout_s
        self._r = fakeredis.FakeRedis(server=server, decode_responses=True)
        self._sub = self._r.pubsub()
        self._sub.subscribe(STREAM_PROGRESS)
        self._running = True
        self._thread = threading.Thread(target=self._consume, daemon=True)
        self._thread.start()

    def _consume(self) -> None:
        for msg in self._sub.listen():
            if not self._running:
                break
            if msg["type"] != "message":
                continue
            try:
                payload = json.loads(msg["data"])
                turn_id = payload["turn_id"]
                stage = payload["stage"]
                prev = self._table.get(turn_id, {})
                # Track: current stage, and whether we've seen `written`
                self._table[turn_id] = {
                    "stage": stage,
                    "ts": payload["ts"],
                    "node_ids": payload.get("node_ids", []),
                    # Remember if we reached `written` — used for stuck detection
                    "reached_written": prev.get("reached_written", False)
                        or stage == TurnStage.written.value,
                    # Timestamp of when `written` was first seen
                    "written_ts": prev.get("written_ts") if prev.get("written_ts")
                        else (payload["ts"] if stage == TurnStage.written.value else None),
                }
            except Exception:
                pass

    def stop(self) -> None:
        self._running = False
        self._sub.unsubscribe()

    def last_stage(self, turn_id: str) -> str | None:
        return self._table.get(turn_id, {}).get("stage")

    def check_stuck(self, now: datetime.datetime | None = None) -> list[str]:
        """
        Flag a turn `stuck` if:
          - it reached `written` stage, AND
          - it never reached `done`, AND
          - it's been more than timeout seconds since `written`
        This catches both: turns stalled at `written`, and turns that went
        written→failed (the Connector crashed — the turn needs retry).
        """
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        stuck = []
        for turn_id, info in self._table.items():
            if not info.get("reached_written"):
                continue
            if info["stage"] == TurnStage.done.value:
                continue  # completed successfully
            written_ts_str = info.get("written_ts")
            if not written_ts_str:
                continue
            written_ts = datetime.datetime.fromisoformat(written_ts_str)
            if (now - written_ts).total_seconds() > self._timeout:
                stuck.append(turn_id)
        return stuck


# ---------------------------------------------------------------------------
# SSE collector stub
# ---------------------------------------------------------------------------

class SSECollector:
    """
    Subscribes to vaultmind:events and collects NodeChangedEvent messages.
    Stands in for the browser SSE connection.
    """

    def __init__(self, server: fakeredis.FakeServer):
        self._events: list[dict] = []
        self._r = fakeredis.FakeRedis(server=server, decode_responses=True)
        self._sub = self._r.pubsub()
        self._sub.subscribe(STREAM_EVENTS)
        self._running = True
        self._thread = threading.Thread(target=self._consume, daemon=True)
        self._thread.start()

    def _consume(self) -> None:
        for msg in self._sub.listen():
            if not self._running:
                break
            if msg["type"] != "message":
                continue
            try:
                self._events.append(json.loads(msg["data"]))
            except Exception:
                pass

    def stop(self) -> None:
        self._running = False
        self._sub.unsubscribe()

    def collected(self) -> list[dict]:
        return list(self._events)


# ---------------------------------------------------------------------------
# DoD tests
# ---------------------------------------------------------------------------

def test_dod_1_queue_item_in_stream() -> None:
    """DoD 1: fixture turn → real QueueItem in vaultmind:turns (XRANGE confirms)."""
    server = _fresh_server()
    r = fakeredis.FakeRedis(server=server, decode_responses=True)

    qi = _load_fixture_turn(0)
    msg_id = _enqueue(r, qi)

    entries = r.xrange(STREAM_TURNS)
    assert len(entries) == 1, f"Expected 1 entry in stream, got {len(entries)}"
    _, fields = entries[0]
    data = json.loads(fields["data"])
    assert data["turn_id"] == qi.turn_id, "turn_id mismatch"
    assert data["source_tool"] == qi.source_tool.value
    print(f"  DoD 1 PASS: QueueItem {qi.turn_id!r} in stream (msg {msg_id})")


def test_dod_2_watcher_consumes_and_acks() -> None:
    """DoD 2: watcher consumes via consumer group and XACKs (XPENDING drains)."""
    server = _fresh_server()
    r = fakeredis.FakeRedis(server=server, decode_responses=True)
    _ensure_consumer_group(r)

    qi = _load_fixture_turn(0)
    _enqueue(r, qi)

    messages = r.xreadgroup(GROUP_NAME, "test-consumer", {STREAM_TURNS: ">"}, count=1)
    assert messages, "No messages delivered to consumer group"

    pending_before = r.xpending(STREAM_TURNS, GROUP_NAME)
    assert pending_before["pending"] == 1, "Expected 1 pending before processing"

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_root = pathlib.Path(tmpdir) / "vault"
        (vault_root / "nodes").mkdir(parents=True)

        stream_name, entries = messages[0]
        for entry_msg_id, fields in entries:
            _process_message(r, entry_msg_id, fields, vault_root)

    pending_after = r.xpending(STREAM_TURNS, GROUP_NAME)
    assert pending_after["pending"] == 0, (
        f"Expected 0 pending after processing, got {pending_after['pending']}"
    )
    print("  DoD 2 PASS: XPENDING drained to 0 after processing")


def test_dod_3_node_written_parses_ac1() -> None:
    """DoD 3: stub Scribe → NoteCreator writes a real .md that parses against AC-1."""
    import yaml

    server = _fresh_server()
    qi = _load_fixture_turn(0)

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_root = pathlib.Path(tmpdir) / "vault"
        (vault_root / "nodes").mkdir(parents=True)
        _run_one_turn(server, qi, vault_root)

        node_files = list((vault_root / "nodes").glob("*.md"))
        assert node_files, "Expected at least one node file written"

        for node_file in node_files:
            content = node_file.read_text()
            assert content.startswith("---"), f"{node_file.name}: missing frontmatter"
            end = content.find("\n---", 3)
            assert end != -1, f"{node_file.name}: frontmatter not closed"
            fm = yaml.safe_load(content[3:end].strip())

            for field in ("id", "type", "title", "created", "source_tool",
                          "source_session", "intent_ref", "status", "related", "flags"):
                assert field in fm, f"{node_file.name}: missing field '{field}'"

            assert fm["id"] == node_file.stem, (
                f"id '{fm['id']}' != stem '{node_file.stem}'"
            )
            assert fm["type"] in ("decision", "constraint", "goal", "question", "scope")
            assert fm["status"] in ("pending", "approved")
            assert isinstance(fm["related"], list)
            assert isinstance(fm["flags"], list)

            body = content[end + 4:].strip()
            assert body, f"{node_file.name}: body is empty"

        # Verify NodeWritten.path is relative (contract: "vault/nodes/<id>.md").
        # Patch NoteCreator to capture NodeWritten objects.
        _orig_nc = watcher_mod.NOTE_CREATOR_FN
        captured_nw: list = []
        def _capturing_nc(sr, vr):
            result = _orig_nc(sr, vr)
            captured_nw.extend(result)
            return result
        watcher_mod.NOTE_CREATOR_FN = _capturing_nc
        try:
            with tempfile.TemporaryDirectory() as tmpdir2:
                vault_root2 = pathlib.Path(tmpdir2) / "vault"
                (vault_root2 / "nodes").mkdir(parents=True)
                qi2 = _load_fixture_turn(0)
                _run_one_turn(server, qi2, vault_root2)
        finally:
            watcher_mod.NOTE_CREATOR_FN = _orig_nc

        for nw in captured_nw:
            p = pathlib.Path(nw.path)
            assert not p.is_absolute(), (
                f"NodeWritten.path must be relative from repo root, got absolute: {nw.path!r}"
            )
            assert nw.path.startswith("vault/nodes/"), (
                f"NodeWritten.path should start with 'vault/nodes/', got: {nw.path!r}"
            )

        print(f"  DoD 3 PASS: {len(node_files)} node(s) written, all AC-1 compliant")


def test_dod_4_connector_populates_related() -> None:
    """DoD 4: NoteCreator → stub Connector populates `related`."""
    import yaml

    server = _fresh_server()
    qi = _load_fixture_turn(0)

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_root = pathlib.Path(tmpdir) / "vault"
        (vault_root / "nodes").mkdir(parents=True)
        _run_one_turn(server, qi, vault_root)

        node_files = list((vault_root / "nodes").glob("*.md"))
        assert node_files, "No node files written"

        for node_file in node_files:
            content = node_file.read_text()
            end = content.find("\n---", 3)
            fm = yaml.safe_load(content[3:end].strip())
            assert isinstance(fm["related"], list), "related must be a list"
            assert len(fm["related"]) >= 1, (
                f"{node_file.name}: Connector must populate related"
            )
            for link in fm["related"]:
                assert link.startswith("[[") and link.endswith("]]"), (
                    f"related entry {link!r} is not a [[wikilink]]"
                )

        print(f"  DoD 4 PASS: Connector populated `related` in {len(node_files)} node(s)")


def test_dod_5_connector_publishes_event() -> None:
    """DoD 5: Connector publishes node-changed on vaultmind:events."""
    server = _fresh_server()
    sse = SSECollector(server)
    time.sleep(0.05)  # let subscriber thread start + subscribe

    qi = _load_fixture_turn(0)

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_root = pathlib.Path(tmpdir) / "vault"
        (vault_root / "nodes").mkdir(parents=True)
        _run_one_turn(server, qi, vault_root)

    time.sleep(0.15)  # let pub/sub deliver
    sse.stop()

    events = sse.collected()
    assert len(events) >= 1, f"Expected ≥1 node-changed event, got {len(events)}"
    evt = events[0]
    assert {"event", "id", "ts"} <= evt.keys(), f"Event missing required fields: {evt}"
    # stub_connector always publishes "linked" — assert the specific type so a
    # regression (e.g. publishing "created" instead) is caught here.
    assert evt["event"] == "linked", (
        f"Expected Connector to publish event type 'linked', got {evt['event']!r}"
    )
    print(f"  DoD 5 PASS: Connector published event {evt['event']!r} for {evt['id']!r}")


def test_dod_6_sse_pubsub_contract() -> None:
    """
    DoD 6: SSE pub/sub contract verified.

    The Next.js SSE route (webapp/src/app/api/events/route.ts) subscribes
    to vaultmind:events and streams data:<json>\\n\\n to the browser.
    We verify here that a subscriber on vaultmind:events receives the exact
    JSON published by the Connector — the structural contract the SSE route
    depends on. Next.js runtime delivery is witnessed during live-fire.
    """
    server = _fresh_server()

    # Subscriber (stands in for the SSE route's Redis subscribe call)
    received: list[dict] = []
    r_sub = fakeredis.FakeRedis(server=server, decode_responses=True)
    sub = r_sub.pubsub()
    sub.subscribe(STREAM_EVENTS)

    def _listen():
        for msg in sub.listen():
            if msg["type"] == "message":
                received.append(json.loads(msg["data"]))
                return  # stop after first message

    t = threading.Thread(target=_listen, daemon=True)
    t.start()
    time.sleep(0.05)

    qi = _load_fixture_turn(0)
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_root = pathlib.Path(tmpdir) / "vault"
        (vault_root / "nodes").mkdir(parents=True)
        _run_one_turn(server, qi, vault_root)

    t.join(timeout=2.0)
    sub.unsubscribe()

    assert received, "SSE subscriber received no events from vaultmind:events"
    payload = received[0]
    assert {"event", "id", "ts"} <= payload.keys(), f"Missing fields: {payload}"
    print(f"  DoD 6 PASS: SSE pub/sub contract verified — event delivered to subscriber")


def test_dod_7_orchestrator_inflight_done() -> None:
    """DoD 7: Orchestrator's in-flight table shows turn reaching `done`."""
    server = _fresh_server()
    tracker = InFlightTracker(server, stuck_timeout_s=999)
    time.sleep(0.05)

    qi = _load_fixture_turn(0)
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_root = pathlib.Path(tmpdir) / "vault"
        (vault_root / "nodes").mkdir(parents=True)
        _run_one_turn(server, qi, vault_root)

    time.sleep(0.15)
    tracker.stop()

    stage = tracker.last_stage(qi.turn_id)
    assert stage == TurnStage.done.value, (
        f"Expected in-flight stage 'done', got {stage!r}"
    )
    print(f"  DoD 7 PASS: Orchestrator in-flight shows turn at 'done'")


# ---------------------------------------------------------------------------
# Secondary: failure-visibility (AC-4)
# ---------------------------------------------------------------------------

def test_secondary_s1_crash_leaves_pending() -> None:
    """S1: Connector crash → QueueItem stays in XPENDING (not lost)."""
    server = _fresh_server()
    r = fakeredis.FakeRedis(server=server, decode_responses=True)
    _ensure_consumer_group(r)

    qi = _load_fixture_turn(0)
    _enqueue(r, qi)
    messages = r.xreadgroup(GROUP_NAME, "test-consumer",
                             {STREAM_TURNS: ">"}, count=1)

    # Inject crashing Connector
    original = watcher_mod.CONNECTOR_FN

    def _crash(nw, redis_client, vault_root):
        raise RuntimeError("Connector deliberately crashed (failure-visibility test)")

    watcher_mod.CONNECTOR_FN = _crash

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_root = pathlib.Path(tmpdir) / "vault"
            (vault_root / "nodes").mkdir(parents=True)
            stream_name, entries = messages[0]
            for msg_id, fields in entries:
                _process_message(r, msg_id, fields, vault_root)

        pending = r.xpending(STREAM_TURNS, GROUP_NAME)
        assert pending["pending"] == 1, (
            f"Expected 1 item in XPENDING after Connector crash, got {pending['pending']}"
        )
        print("  S1  PASS: Connector crash → QueueItem stays in XPENDING (not lost)")
    finally:
        watcher_mod.CONNECTOR_FN = original


def test_secondary_s2_orchestrator_flags_stuck() -> None:
    """S2: Orchestrator flags turn `stuck` when stuck at `written` past timeout."""
    server = _fresh_server()
    tracker = InFlightTracker(server, stuck_timeout_s=0)
    time.sleep(0.05)

    original = watcher_mod.CONNECTOR_FN

    def _crash(nw, redis_client, vault_root):
        raise RuntimeError("Connector deliberately crashed (stuck-detection test)")

    watcher_mod.CONNECTOR_FN = _crash

    try:
        qi = _load_fixture_turn(0)
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_root = pathlib.Path(tmpdir) / "vault"
            (vault_root / "nodes").mkdir(parents=True)
            _run_one_turn(server, qi, vault_root)

        time.sleep(0.15)
        tracker.stop()

        # Simulate checking after plenty of time has passed
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        stuck_turns = tracker.check_stuck(now=future)
        assert qi.turn_id in stuck_turns, (
            f"Expected {qi.turn_id!r} stuck; last_stage={tracker.last_stage(qi.turn_id)!r}, "
            f"stuck={stuck_turns}"
        )
        print(f"  S2  PASS: Orchestrator flagged turn as 'stuck' after timeout")
    finally:
        watcher_mod.CONNECTOR_FN = original


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

ALL_TESTS = [
    ("DoD 1 — QueueItem in stream",          test_dod_1_queue_item_in_stream),
    ("DoD 2 — Watcher consumes + XACKs",     test_dod_2_watcher_consumes_and_acks),
    ("DoD 3 — Node written, AC-1 compliant", test_dod_3_node_written_parses_ac1),
    ("DoD 4 — Connector populates related",  test_dod_4_connector_populates_related),
    ("DoD 5 — Connector publishes event",    test_dod_5_connector_publishes_event),
    ("DoD 6 — SSE pub/sub contract",         test_dod_6_sse_pubsub_contract),
    ("DoD 7 — Orchestrator in-flight=done",  test_dod_7_orchestrator_inflight_done),
    ("S1  — Crash leaves XPENDING",          test_secondary_s1_crash_leaves_pending),
    ("S2  — Orchestrator flags stuck",       test_secondary_s2_orchestrator_flags_stuck),
]


def main() -> int:
    print("=== Bucket 5 Walking Skeleton Gate ===")
    print()
    failed = 0
    for name, fn in ALL_TESTS:
        print(f"--- {name}")
        try:
            fn()
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
        print()

    if failed:
        print(f"RESULT: {failed} failure(s) — Bucket 5 gate FAILED")
        return 1

    print("RESULT: all 9 checks passed — Bucket 5 gate PASSED ✓")
    print()
    print("Seams verified (end-to-end, no real Redis):")
    print("  vaultmind:turns → consumer group → watcher → AC-1 node")
    print("  → Connector (related populated) → vaultmind:events → SSE subscriber")
    print("  → TurnProgress → Orchestrator in-flight (done)")
    print("  Crash-before-ACK → XPENDING (item not lost)")
    print("  Stuck detection: written+timeout → flagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
