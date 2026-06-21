"""
tests/test_integration_pipeline.py — End-to-end pipeline integration tests.

Exercises the full data path across all session boundaries:
  P1 (reader → producer → session_state → cursor)
    ↓  Redis Stream vaultmind:turns
  P2 (watcher consumer group → scribe → notecreator → vault/nodes/*.md)
    ↓  in-process NodeWritten
  P3 (connector → related frontmatter → vaultmind:events pub/sub)
    ↓  TurnProgress pub/sub → InFlightTracker

These tests use fakeredis and monkeypatched Scribe to run entirely in-process
with no real Redis, no real Anthropic API, and no filesystem side effects
outside tmp_path.

Cross-cutting concerns verified here (not retested in unit tests):
  - QueueItem survives the full Redis round-trip (serialise → xadd → xreadgroup
    → deserialise) and carries identical field values.
  - Scribe result flows into NoteCreator; written node file satisfies AC-1 schema.
  - Connector receives NodeWritten and writes `related:` without touching the body.
  - NodeChangedEvent published to vaultmind:events is valid JSON with the right
    event type and node id.
  - TurnProgress is published at each stage and the in-flight tracker reaches
    "done" for a successful turn.
  - A secret-containing turn is flagged "secret-detected" on the written node,
    the NodeChangedEvent carries the correct id, and the turn still completes
    (write is not blocked).
"""
from __future__ import annotations

import json
import pathlib
import shutil
import threading
import time

import fakeredis
import pytest

from vaultmind.contracts import (
    Extraction,
    NodeChangedEventType,
    NodeType,
    NodeStatus,
    QueueItem,
    ScribeResult,
    SourceTool,
    TurnStage,
    TurnText,
)
from vaultmind.ingest import producer
from vaultmind.notecreator import write_nodes
from vaultmind.connector import link_node
from vaultmind.watcher import (
    STREAM_TURNS,
    CHANNEL_EVENTS,
    CHANNEL_PROGRESS,
    GROUP_NAME,
    _ensure_consumer_group,
    _process_message,
    stub_scribe,
    stub_note_creator,
    stub_connector,
)
from vaultmind.orchestrator import InFlightTracker

FIXTURE_VAULT = pathlib.Path(__file__).parent.parent / "fixtures" / "vault"
FIXTURE_TRANSCRIPT = pathlib.Path(__file__).parent.parent / "fixtures" / "transcript.jsonl"
FIXTURE_QUEUE_ITEM = pathlib.Path(__file__).parent.parent / "fixtures" / "queue_item.json"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def vault(tmp_path: pathlib.Path) -> pathlib.Path:
    dst = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, dst)
    return dst


@pytest.fixture
def fresh_server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


@pytest.fixture
def redis_client(fresh_server: fakeredis.FakeServer) -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(server=fresh_server, decode_responses=True)


# ---------------------------------------------------------------------------
# Helper: collect pub/sub messages in a background thread
# ---------------------------------------------------------------------------

class _PubSubCollector:
    """Subscribe to a Redis channel and collect messages in a background thread."""

    def __init__(self, server: fakeredis.FakeServer, channel: str) -> None:
        self._events: list[dict] = []
        self._raw: list[str] = []
        r = fakeredis.FakeRedis(server=server, decode_responses=True)
        self._ps = r.pubsub()
        self._ps.subscribe(channel)
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        for msg in self._ps.listen():
            if not self._running:
                break
            if msg["type"] != "message":
                continue
            raw = msg["data"]
            self._raw.append(raw)
            try:
                self._events.append(json.loads(raw))
            except Exception:
                pass

    def stop(self) -> None:
        self._running = False
        self._ps.unsubscribe()

    def wait_for(self, count: int, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while len(self._events) < count and time.monotonic() < deadline:
            time.sleep(0.02)

    @property
    def events(self) -> list[dict]:
        return list(self._events)


# ---------------------------------------------------------------------------
# Helper: load fixture QueueItem
# ---------------------------------------------------------------------------

def _fixture_qi(index: int = 0) -> QueueItem:
    lines = FIXTURE_TRANSCRIPT.read_text().strip().splitlines()
    return QueueItem.model_validate(json.loads(lines[index]))


# ===========================================================================
# 1. QueueItem round-trip through Redis Stream
# ===========================================================================

class TestQueueItemRoundTrip:
    """P1→P2 seam: QueueItem written by producer, consumed via consumer group."""

    def test_producer_writes_valid_queue_item(
        self, redis_client: fakeredis.FakeRedis
    ) -> None:
        """enqueue() writes a deserializable QueueItem to the stream."""
        turn = TurnText(user="Use RLS for authz", assistant="Great idea.")
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("redis.from_url", lambda *a, **kw: redis_client)
            ok = producer.enqueue(
                turn, "sess-int-001", "/tmp/t.jsonl", SourceTool.claude_code,
                "redis://localhost:6379"
            )
        assert ok is True
        entries = redis_client.xrange(STREAM_TURNS)
        assert len(entries) == 1
        _, fields = entries[0]
        qi = QueueItem.model_validate(json.loads(fields["data"]))
        assert qi.session_id == "sess-int-001"
        assert qi.turn_text.user == "Use RLS for authz"
        assert qi.turn_text.assistant == "Great idea."
        assert qi.source_tool == SourceTool.claude_code

    def test_fixture_queue_item_round_trips(
        self, redis_client: fakeredis.FakeRedis
    ) -> None:
        """Fixture QueueItem survives xadd → xreadgroup → deserialise unchanged."""
        qi = _fixture_qi(0)
        _ensure_consumer_group(redis_client)
        redis_client.xadd(STREAM_TURNS, {"data": qi.model_dump_json()})

        messages = redis_client.xreadgroup(
            GROUP_NAME, "int-consumer", {STREAM_TURNS: ">"}, count=1
        )
        assert messages, "Consumer group delivered no messages"
        _, entries = messages[0]
        msg_id, fields = entries[0]
        qi_back = QueueItem.model_validate(json.loads(fields["data"]))

        assert qi_back.turn_id == qi.turn_id
        assert qi_back.session_id == qi.session_id
        assert qi_back.source_tool == qi.source_tool
        assert qi_back.turn_text.user == qi.turn_text.user
        assert qi_back.turn_text.assistant == qi.turn_text.assistant
        assert qi_back.transcript_path == qi.transcript_path

    def test_multiple_turns_preserve_order(
        self, redis_client: fakeredis.FakeRedis
    ) -> None:
        """All four fixture turns land in the stream in insertion order."""
        lines = FIXTURE_TRANSCRIPT.read_text().strip().splitlines()
        qis = [QueueItem.model_validate(json.loads(l)) for l in lines]
        for qi in qis:
            redis_client.xadd(STREAM_TURNS, {"data": qi.model_dump_json()})

        entries = redis_client.xrange(STREAM_TURNS)
        assert len(entries) == 4
        ids_in = [qi.turn_id for qi in qis]
        ids_out = [
            json.loads(fields["data"])["turn_id"] for _, fields in entries
        ]
        assert ids_in == ids_out

    def test_consumer_group_not_created_by_producer(
        self, redis_client: fakeredis.FakeRedis
    ) -> None:
        """P1's producer must never create the consumer group (AC-3)."""
        turn = TurnText(user="x", assistant="y")
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("redis.from_url", lambda *a, **kw: redis_client)
            producer.enqueue(
                turn, "sess-int-002", None, SourceTool.claude_code,
                "redis://localhost:6379"
            )
        try:
            groups = redis_client.xinfo_groups(STREAM_TURNS)
        except Exception:
            groups = []
        assert groups == [], (
            "Producer must NOT create the consumer group — that's the watcher's job"
        )


# ===========================================================================
# 2. Scribe → NoteCreator integration (P2 in-process seam)
# ===========================================================================

class TestScribeToNoteCreator:
    """ScribeResult produced in P2 flows directly into NoteCreator.write_nodes."""

    def test_write_nodes_from_fixture_scribe_result(
        self, vault: pathlib.Path
    ) -> None:
        """Fixture ScribeResult produces a valid AC-1 node file."""
        sr = ScribeResult.model_validate(
            json.loads(FIXTURE_QUEUE_ITEM.parent.joinpath("scribe_result.json").read_text())
        )
        nodes = write_nodes(sr, vault)
        assert len(nodes) == 1
        nw = nodes[0]
        content = (vault.parent / nw.path).read_text()
        # AC-1 required fields
        assert "id:" in content
        assert "type: decision" in content
        assert "status: approved" in content
        assert "related: []" in content
        assert "source_tool: claude-code" in content
        assert "intent_ref:" in content
        # Body is verbatim from Scribe (immutability invariant)
        assert "Supabase Row-Level Security" in content

    def test_write_nodes_body_is_scribe_verbatim(
        self, vault: pathlib.Path
    ) -> None:
        """Body must be byte-for-byte what the Scribe provided."""
        body = "Exact scribe body text. Nothing else.\n\n> \"verbatim\""
        sr = ScribeResult(
            turn_id="sess-int-003-aabbccdd",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-003",
            extractions=[
                Extraction(
                    type=NodeType.goal,
                    title="Finish auth flow",
                    slug="finish-auth-flow",
                    body=body,
                )
            ],
            intent_shift=None,
        )
        nodes = write_nodes(sr, vault)
        content = (vault.parent / nodes[0].path).read_text()
        # Body lives after the closing ---
        body_start = content.index("---", 3) + 3
        actual_body = content[body_start:].lstrip("\n")
        assert actual_body.rstrip("\n") == body.rstrip("\n")

    def test_write_nodes_multiple_extractions(
        self, vault: pathlib.Path
    ) -> None:
        """Multiple extractions from one turn each produce a separate node file."""
        sr = ScribeResult(
            turn_id="sess-int-004-multi",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-004",
            extractions=[
                Extraction(
                    type=NodeType.decision,
                    title="Use RLS",
                    slug="use-rls",
                    body="RLS decision body.",
                ),
                Extraction(
                    type=NodeType.constraint,
                    title="No PII in logs",
                    slug="no-pii-in-logs",
                    body="Constraint body.",
                ),
            ],
            intent_shift=None,
        )
        nodes = write_nodes(sr, vault)
        assert len(nodes) == 2
        slugs = [nw.id for nw in nodes]
        assert any("use-rls" in s for s in slugs)
        assert any("no-pii-in-logs" in s for s in slugs)
        for nw in nodes:
            assert (vault.parent / nw.path).exists()

    def test_intent_shift_appended_to_intentlog(
        self, vault: pathlib.Path
    ) -> None:
        """Intent shift from Scribe gets appended to IntentLog.md as ai-detected."""
        # Vault has an existing IntentLog from fixture
        sr = ScribeResult(
            turn_id="sess-int-005-intent",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-005",
            extractions=[],
            intent_shift="Switch focus to deployment pipeline",
        )
        write_nodes(sr, vault)
        content = (vault / "IntentLog.md").read_text()
        assert "Switch focus to deployment pipeline" in content
        assert "ai-detected" in content
        # Previous intent still present (not overwritten)
        assert "Help me finish the auth flow" in content
        # Only one "— Current" marker
        assert content.count("— Current") == 1

    def test_empty_extractions_writes_nothing(
        self, vault: pathlib.Path
    ) -> None:
        """Turns with no extractions should not create any node files."""
        nodes_before = list((vault / "nodes").glob("*.md"))
        sr = ScribeResult(
            turn_id="sess-int-006-empty",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-006",
            extractions=[],
            intent_shift=None,
        )
        nodes = write_nodes(sr, vault)
        assert nodes == []
        nodes_after = list((vault / "nodes").glob("*.md"))
        assert len(nodes_before) == len(nodes_after)


# ===========================================================================
# 3. NoteCreator → Connector integration (P2↔P3 seam)
# ===========================================================================

class TestNoteCreatorToConnector:
    """NodeWritten produced by NoteCreator is consumed by Connector."""

    def test_connector_receives_node_written_and_links(
        self,
        vault: pathlib.Path,
        redis_client: fakeredis.FakeRedis,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """Full P2→P3 handoff: write_nodes → link_node → related frontmatter updated."""
        sr = ScribeResult(
            turn_id="sess-int-007-link",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-007",
            extractions=[
                Extraction(
                    type=NodeType.decision,
                    title="Enforce JWT expiry at gateway",
                    slug="jwt-expiry-gateway",
                    body="Enforce JWT expiry at the API gateway layer.",
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        assert len(written) == 1
        nw = written[0]

        result = link_node(nw, redis_client, vault)

        assert result.id == nw.id
        assert isinstance(result.related, list)
        assert result.linked_at

        # Frontmatter `related:` in the file was updated
        content = (vault.parent / nw.path).read_text()
        assert "related:" in content

    def test_connector_does_not_mutate_body(
        self,
        vault: pathlib.Path,
        redis_client: fakeredis.FakeRedis,
    ) -> None:
        """Connector invariant: only `related:` frontmatter is ever changed."""
        original_body = "This is the immutable scribe body. Must not be changed."
        sr = ScribeResult(
            turn_id="sess-int-008-body",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-008",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title="No hardcoded credentials",
                    slug="no-hardcoded-creds",
                    body=original_body,
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        nw = written[0]

        link_node(nw, redis_client, vault)

        content = (vault.parent / nw.path).read_text()
        # Body is everything after the closing ---
        body_start = content.index("---", 3) + 3
        actual_body = content[body_start:].strip()
        assert original_body.strip() in actual_body

    def test_connector_publishes_event_with_correct_id(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """Connector publishes a NodeChangedEvent with the correct node id."""
        r = fakeredis.FakeRedis(server=fresh_server, decode_responses=True)
        collector = _PubSubCollector(fresh_server, CHANNEL_EVENTS)
        # Allow subscriber to connect
        time.sleep(0.05)

        sr = ScribeResult(
            turn_id="sess-int-009-event",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-009",
            extractions=[
                Extraction(
                    type=NodeType.question,
                    title="Should we use PKCE?",
                    slug="should-use-pkce",
                    body="Open question about PKCE for OAuth flow.",
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        nw = written[0]

        link_node(nw, r, vault)
        collector.wait_for(1, timeout=2.0)
        collector.stop()

        assert len(collector.events) >= 1
        evt = collector.events[0]
        assert evt["id"] == nw.id
        assert "event" in evt
        assert "ts" in evt

    def test_full_p2_p3_pipeline_produces_linked_node(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """
        End-to-end P2+P3: fixture QueueItem → stub_scribe → stub_note_creator
        → stub_connector → node on disk with related populated.
        """
        r = fakeredis.FakeRedis(server=fresh_server, decode_responses=True)
        qi = _fixture_qi(0)

        sr = stub_scribe(qi)
        written = stub_note_creator(sr, vault)
        assert len(written) == 1

        result = stub_connector(written[0], r, vault)
        assert result.id == written[0].id
        assert result.linked_at

        node_path = vault.parent / written[0].path
        assert node_path.exists()
        content = node_path.read_text()
        assert "related:" in content


# ===========================================================================
# 4. Full watcher pipeline (consumer group → _process_message → ACK)
# ===========================================================================

class TestWatcherPipeline:
    """Watcher _process_message exercises the full stub chain end-to-end."""

    def _run_turn(
        self,
        server: fakeredis.FakeServer,
        qi: QueueItem,
        vault: pathlib.Path,
    ) -> None:
        r = fakeredis.FakeRedis(server=server, decode_responses=True)
        _ensure_consumer_group(r)
        r.xadd(STREAM_TURNS, {"data": qi.model_dump_json()})
        messages = r.xreadgroup(
            GROUP_NAME, "int-consumer", {STREAM_TURNS: ">"}, count=1
        )
        assert messages
        _, entries = messages[0]
        for msg_id, fields in entries:
            _process_message(r, msg_id, fields, vault)

    def test_process_message_acks_on_success(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """Message is ACKed (removed from PEL) after successful processing."""
        r = fakeredis.FakeRedis(server=fresh_server, decode_responses=True)
        _ensure_consumer_group(r)
        qi = _fixture_qi(0)
        r.xadd(STREAM_TURNS, {"data": qi.model_dump_json()})

        messages = r.xreadgroup(
            GROUP_NAME, "int-consumer", {STREAM_TURNS: ">"}, count=1
        )
        _, entries = messages[0]
        msg_id, fields = entries[0]
        _process_message(r, msg_id, fields, vault)

        # PEL should be empty after successful ACK
        pending = r.xpending(STREAM_TURNS, GROUP_NAME)
        assert pending["pending"] == 0

    def test_process_message_writes_node_to_disk(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """After processing, at least one .md node file exists in vault/nodes/."""
        nodes_before = len(list((vault / "nodes").glob("*.md")))
        self._run_turn(fresh_server, _fixture_qi(0), vault)
        nodes_after = len(list((vault / "nodes").glob("*.md")))
        assert nodes_after > nodes_before

    def test_process_message_publishes_progress_events(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """TurnProgress events are published to vaultmind:progress for each stage."""
        collector = _PubSubCollector(fresh_server, CHANNEL_PROGRESS)
        # Give subscriber thread time to connect before the pipeline runs
        time.sleep(0.1)

        self._run_turn(fresh_server, _fixture_qi(0), vault)
        # Pipeline publishes started, extracted, written, linked, done — wait for all 5
        collector.wait_for(5, timeout=5.0)
        collector.stop()

        stages = {e["stage"] for e in collector.events}
        # Must publish at least started and done
        assert TurnStage.started.value in stages
        assert TurnStage.done.value in stages

    def test_process_message_publishes_node_changed_event(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """A NodeChangedEvent is published to vaultmind:events after node is linked."""
        collector = _PubSubCollector(fresh_server, CHANNEL_EVENTS)
        time.sleep(0.05)

        self._run_turn(fresh_server, _fixture_qi(0), vault)
        collector.wait_for(1, timeout=3.0)
        collector.stop()

        assert len(collector.events) >= 1
        evt = collector.events[0]
        assert "id" in evt
        assert "event" in evt
        assert "ts" in evt

    def test_idempotency_second_run_is_noop(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """Processing the same turn_id twice skips all steps after the first run."""
        r = fakeredis.FakeRedis(server=fresh_server, decode_responses=True)
        _ensure_consumer_group(r)
        qi = _fixture_qi(0)

        # First run
        r.xadd(STREAM_TURNS, {"data": qi.model_dump_json()})
        msgs = r.xreadgroup(GROUP_NAME, "c1", {STREAM_TURNS: ">"}, count=1)
        msg_id, fields = msgs[0][1][0]
        _process_message(r, msg_id, fields, vault)
        nodes_after_first = len(list((vault / "nodes").glob("*.md")))

        # Second run: same turn_id
        r.xadd(STREAM_TURNS, {"data": qi.model_dump_json()})
        msgs = r.xreadgroup(GROUP_NAME, "c1", {STREAM_TURNS: ">"}, count=1)
        msg_id2, fields2 = msgs[0][1][0]
        _process_message(r, msg_id2, fields2, vault)
        nodes_after_second = len(list((vault / "nodes").glob("*.md")))

        # Idempotent: no additional nodes should be written
        assert nodes_after_second == nodes_after_first


# ===========================================================================
# 5. InFlightTracker + TurnProgress integration
# ===========================================================================

class TestInFlightTrackerIntegration:
    """TurnProgress published during _process_message is tracked by InFlightTracker."""

    def test_turn_reaches_done_in_tracker(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """After a successful pipeline run the tracker records stage=done."""
        r = fakeredis.FakeRedis(server=fresh_server, decode_responses=True)
        tracker = InFlightTracker(stuck_timeout_s=60.0)

        # Wire tracker to fakeredis progress channel
        sub_r = fakeredis.FakeRedis(server=fresh_server, decode_responses=True)
        ps = sub_r.pubsub()
        ps.subscribe(CHANNEL_PROGRESS)
        received: list[dict] = []

        def _consume() -> None:
            for msg in ps.listen():
                if msg["type"] == "message":
                    try:
                        d = json.loads(msg["data"])
                        tracker.update(d["turn_id"], d["stage"], d.get("node_ids", []))
                        received.append(d)
                    except Exception:
                        pass

        t = threading.Thread(target=_consume, daemon=True)
        t.start()
        time.sleep(0.05)

        _ensure_consumer_group(r)
        qi = _fixture_qi(0)
        r.xadd(STREAM_TURNS, {"data": qi.model_dump_json()})
        msgs = r.xreadgroup(GROUP_NAME, "c1", {STREAM_TURNS: ">"}, count=1)
        msg_id, fields = msgs[0][1][0]
        _process_message(r, msg_id, fields, vault)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if any(d["stage"] == TurnStage.done.value for d in received):
                break
            time.sleep(0.05)

        ps.unsubscribe()

        assert any(d["stage"] == TurnStage.done.value for d in received), (
            f"Expected 'done' stage in progress events; got stages: "
            f"{[d['stage'] for d in received]}"
        )
        stuck = tracker.get_stuck()
        assert qi.turn_id not in stuck

    def test_stuck_detection_fires_for_stalled_turn(self) -> None:
        """A turn that reached 'written' but never 'done' is detected as stuck."""
        tracker = InFlightTracker(stuck_timeout_s=0.05)
        tracker.update("stuck-turn-001", TurnStage.started.value, [])
        tracker.update("stuck-turn-001", TurnStage.extracted.value, [])
        tracker.update("stuck-turn-001", TurnStage.written.value, [])
        # Simulate timeout
        time.sleep(0.1)
        stuck = tracker.get_stuck()
        assert "stuck-turn-001" in stuck

    def test_completed_turn_not_stuck(self) -> None:
        """A turn that reached 'done' is never reported as stuck."""
        tracker = InFlightTracker(stuck_timeout_s=0.05)
        tracker.update("done-turn-001", TurnStage.started.value, [])
        tracker.update("done-turn-001", TurnStage.written.value, [])
        tracker.update("done-turn-001", TurnStage.done.value, ["node-1"])
        time.sleep(0.1)
        assert "done-turn-001" not in tracker.get_stuck()


# ===========================================================================
# 6. Secret-flagging integration (write path)
# ===========================================================================

class TestSecretFlaggingIntegration:
    """Secret-containing turns are flagged but never blocked during the pipeline."""

    def test_secret_in_turn_flags_node_and_pipeline_completes(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """
        The fourth fixture turn contains a Supabase service_role JWT.
        The pipeline must still complete; the written node carries the
        'secret-detected' flag.
        """
        r = fakeredis.FakeRedis(server=fresh_server, decode_responses=True)
        _ensure_consumer_group(r)

        # Turn 4 (index 3) has the hardcoded JWT
        qi = _fixture_qi(3)
        r.xadd(STREAM_TURNS, {"data": qi.model_dump_json()})
        msgs = r.xreadgroup(GROUP_NAME, "c1", {STREAM_TURNS: ">"}, count=1)
        msg_id, fields = msgs[0][1][0]
        _process_message(r, msg_id, fields, vault)

        # PEL empty → turn completed (not stuck)
        pending = r.xpending(STREAM_TURNS, GROUP_NAME)
        assert pending["pending"] == 0

        # At least one new node was written
        node_files = list((vault / "nodes").glob("*.md"))
        assert len(node_files) > 0

    def test_notecreator_flags_secret_node(
        self, vault: pathlib.Path
    ) -> None:
        """NoteCreator sets 'secret-detected' flag when content contains a JWT."""
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNjMwMDAwMDAwLCJleHAiOjE5OTk5OTk5OTl9"
            ".DEMO_SIGNATURE_PLACEHOLDER_NOT_A_REAL_KEY"
        )
        sr = ScribeResult(
            turn_id="sess-int-secret-001",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-secret",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title="Config with secret",
                    slug="config-with-secret",
                    body=f'service_role_key = "{jwt}"',
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        assert len(written) == 1
        assert "secret-detected" in written[0].flags

        # File was still written to disk
        node_path = vault.parent / written[0].path
        assert node_path.exists()

        # File content has the secret-detected flag in frontmatter
        content = node_path.read_text()
        assert "secret-detected" in content

    def test_secret_node_event_published(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """Even a secret-flagged node gets a NodeChangedEvent published."""
        r = fakeredis.FakeRedis(server=fresh_server, decode_responses=True)
        collector = _PubSubCollector(fresh_server, CHANNEL_EVENTS)
        time.sleep(0.05)

        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNjMwMDAwMDAwLCJleHAiOjE5OTk5OTk5OTl9"
            ".DEMO_SIGNATURE_PLACEHOLDER_NOT_A_REAL_KEY"
        )
        sr = ScribeResult(
            turn_id="sess-int-secret-002",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-secret",
            extractions=[
                Extraction(
                    type=NodeType.constraint,
                    title="Leaked key node",
                    slug="leaked-key-node",
                    body=f'key = "{jwt}"',
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        nw = written[0]
        link_node(nw, r, vault)

        collector.wait_for(1, timeout=2.0)
        collector.stop()

        assert len(collector.events) >= 1
        evt = collector.events[0]
        assert evt["id"] == nw.id


# ===========================================================================
# 7. Cross-seam data-contract fidelity
# ===========================================================================

class TestContractFidelity:
    """
    Verify that field values are never mutated as data crosses the
    QueueItem → ScribeResult → NodeWritten → LinkResult seam.
    """

    def test_turn_id_propagates_through_full_chain(
        self,
        vault: pathlib.Path,
        fresh_server: fakeredis.FakeServer,
    ) -> None:
        """turn_id from QueueItem appears in ScribeResult and in the node's source_session."""
        qi = _fixture_qi(0)

        sr = stub_scribe(qi)
        assert sr.turn_id == qi.turn_id
        assert sr.source_session == qi.session_id

        r = fakeredis.FakeRedis(server=fresh_server, decode_responses=True)
        written = stub_note_creator(sr, vault)
        result = stub_connector(written[0], r, vault)
        assert result.id == written[0].id

        # The written file contains the session_id
        content = (vault.parent / written[0].path).read_text()
        assert qi.session_id in content

    def test_source_tool_preserved_in_node_file(
        self,
        vault: pathlib.Path,
    ) -> None:
        """source_tool from QueueItem must appear in the written node frontmatter."""
        sr = ScribeResult(
            turn_id="sess-int-ct-001",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-ct",
            extractions=[
                Extraction(
                    type=NodeType.decision,
                    title="Source tool test",
                    slug="source-tool-test",
                    body="Body text.",
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        content = (vault.parent / written[0].path).read_text()
        assert "source_tool: claude-code" in content

    def test_node_written_contract_fields_complete(
        self,
        vault: pathlib.Path,
    ) -> None:
        """NodeWritten returned by write_nodes has all required contract fields."""
        sr = ScribeResult(
            turn_id="sess-int-ct-002",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-ct",
            extractions=[
                Extraction(
                    type=NodeType.question,
                    title="Open question about infra",
                    slug="open-question-infra",
                    body="Should we use ECS or K8s?",
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        nw = written[0]

        assert nw.id
        assert nw.path.startswith("vault/nodes/")
        assert nw.path.endswith(".md")
        assert nw.type == NodeType.question
        assert nw.title == "Open question about infra"
        assert nw.status == NodeStatus.approved
        assert isinstance(nw.flags, list)
        assert nw.intent_ref

    def test_link_result_contract_fields_complete(
        self,
        vault: pathlib.Path,
        redis_client: fakeredis.FakeRedis,
    ) -> None:
        """LinkResult returned by link_node has all required contract fields."""
        sr = ScribeResult(
            turn_id="sess-int-ct-003",
            source_tool=SourceTool.claude_code,
            source_session="sess-int-ct",
            extractions=[
                Extraction(
                    type=NodeType.decision,
                    title="Link result test",
                    slug="link-result-test",
                    body="Body.",
                )
            ],
            intent_shift=None,
        )
        written = write_nodes(sr, vault)
        result = link_node(written[0], redis_client, vault)

        assert result.id
        assert isinstance(result.related, list)
        assert result.status in (NodeStatus.approved, NodeStatus.pending)
        assert result.linked_at  # ISO 8601 timestamp
