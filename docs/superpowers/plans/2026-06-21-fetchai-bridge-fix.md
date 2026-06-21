# Fetch.AI Bridge Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `webapp/agent_bridge.py` so the frontend can reliably send messages to the teammate's Fetch.AI uAgent and receive replies.

**Architecture:** Replace the broken webhook-based approach (`fetchai` package + `register_with_agentverse`) with a proper `uagents.Agent` on port 8002 — exactly as `vaultmind/orchestrator/__init__.py` already does. The uAgent uses an `on_interval` handler to drain a `threading.Queue` of outbound messages; a Flask HTTP API on port 5002 accepts messages from Next.js and exposes the reply. This avoids the cloud-to-localhost webhook delivery problem entirely.

**Tech Stack:** Python `uagents` + `uagents_core` (Chat Protocol), Flask + flask-cors, `threading.Queue` for cross-thread communication, dotenv for config.

---

## Root Cause Summary (read before touching code)

Three distinct problems — all code, not Fetch.AI platform:

| # | Problem | Evidence |
|---|---------|----------|
| 1 | Bridge dependencies not installed | `pip show uagents uagents_core fetchai flask flask-cors` → all missing |
| 2 | Wrong SDK: webhook agent registers `http://localhost:5002/webhook` with Agentverse cloud — Agentverse POSTs replies to that URL but cannot reach `localhost` | `register_with_agentverse(url="http://localhost:5002/webhook")` in `agent_bridge.py` |
| 3 | No mechanism to send via uAgent from a Flask route — Flask and uAgent each need their own event loop | `agent_bridge.py:41-59` — `send_message_to_agent` is called from a synchronous Flask handler with no asyncio bridge |

**Fix:** use `uagents.Agent` (port 8002) + `on_interval` drain loop + `threading.Queue` pair to cross the Flask↔uAgent thread boundary. The uAgent communicates with the teammate's agent peer-to-peer through the Agentverse Almanac; the teammate's reply arrives at `http://localhost:8002/submit` (our endpoint), which IS reachable on the same machine.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `webapp/requirements-bridge.txt` | **Create** | Bridge-specific deps (uagents, uagents-core, fetchai, flask, flask-cors, python-dotenv) |
| `webapp/agent_bridge.py` | **Rewrite** | Proper uAgent on 8002 + Flask HTTP API on 5002 |
| `tests/test_agent_bridge.py` | **Create** | Unit tests for queue mechanics (no live Fetch.AI needed) |

Do **not** touch `vaultmind/orchestrator/__init__.py`, `webapp/src/app/api/agent/route.ts`, or any contract files — those are correct.

---

## Task 1: Add Bridge Dependencies

**Files:**
- Create: `webapp/requirements-bridge.txt`

- [ ] **Step 1: Write the requirements file**

```
# webapp/requirements-bridge.txt
uagents>=0.22.0
uagents-core>=0.4.0
fetchai>=0.6.0
flask>=3.0.0
flask-cors>=4.0.0
python-dotenv>=1.0.0
```

- [ ] **Step 2: Install and verify each package**

Run:
```
pip install uagents uagents-core fetchai flask flask-cors python-dotenv
```

Expected (no errors, versions print):
```
pip show uagents uagents-core flask
```
Each should show `Name:`, `Version:`, `Location:`.

- [ ] **Step 3: Verify the Chat Protocol import works**

Run:
```python
python -c "from uagents import Agent, Context, Protocol; from uagents_core.contrib.protocols.chat import ChatMessage, ChatAcknowledgement, TextContent; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add webapp/requirements-bridge.txt
git commit -m "feat(bridge): add requirements-bridge.txt for Fetch.AI bridge deps"
```

---

## Task 2: Write the Failing Bridge Tests

**Files:**
- Create: `tests/test_agent_bridge.py`

The tests exercise the queue mechanics in isolation — no live Fetch.AI connection needed. We import helper functions that will be extracted in Task 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_agent_bridge.py
import queue
import threading
import pytest

# These imports will fail until Task 3 implements them.
from webapp.agent_bridge import (
    enqueue_send,
    dequeue_send,
    enqueue_reply,
    dequeue_reply,
    clear_reply_queue,
)


def test_enqueue_and_dequeue_send():
    """A message placed in the send queue is immediately retrievable."""
    clear_reply_queue()
    enqueue_send("hello teammate")
    msg = dequeue_send(timeout=0.1)
    assert msg == "hello teammate"


def test_dequeue_send_returns_none_when_empty():
    """Draining an empty send queue returns None without blocking."""
    # Drain any leftover
    while dequeue_send(timeout=0) is not None:
        pass
    result = dequeue_send(timeout=0)
    assert result is None


def test_enqueue_reply_and_dequeue():
    """A reply placed in the reply queue is retrievable once."""
    clear_reply_queue()
    enqueue_reply("agent says hi")
    reply = dequeue_reply()
    assert reply == "agent says hi"


def test_dequeue_reply_returns_none_when_empty():
    clear_reply_queue()
    assert dequeue_reply() is None


def test_enqueue_send_clears_old_reply():
    """enqueue_send clears the reply queue so old replies don't leak."""
    enqueue_reply("stale reply")
    enqueue_send("new message")  # should clear the stale reply
    assert dequeue_reply() is None


def test_reply_queue_overwrites_when_full():
    """Filling the reply queue beyond maxsize discards the oldest, not the newest."""
    clear_reply_queue()
    for i in range(12):  # maxsize is 10
        enqueue_reply(f"msg-{i}")
    # Should have 10 messages, newest ones
    replies = []
    while True:
        r = dequeue_reply()
        if r is None:
            break
        replies.append(r)
    assert len(replies) == 10
    assert "msg-11" in replies  # newest retained
```

- [ ] **Step 2: Run tests to confirm they fail with ImportError**

Run:
```
pytest tests/test_agent_bridge.py -v
```
Expected: `ImportError: cannot import name 'enqueue_send' from 'webapp.agent_bridge'`

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_agent_bridge.py
git commit -m "test(bridge): add failing tests for queue mechanics"
```

---

## Task 3: Rewrite agent_bridge.py

**Files:**
- Modify: `webapp/agent_bridge.py`

Replace the webhook-based approach entirely. The new bridge has two layers:
1. **Queue helpers** (pure functions, testable without uAgents) — enqueue/dequeue wrappers around two `threading.Queue` objects
2. **uAgent layer** — reads from send queue via `on_interval`, writes replies into reply queue via `on_message`
3. **Flask layer** — `/send` enqueues a message and clears reply queue; `/response` pops latest reply

- [ ] **Step 1: Write the new agent_bridge.py**

```python
"""
webapp/agent_bridge.py

Fetch.AI bridge: Next.js frontend → uAgent → teammate's Orchestrator → reply → Next.js.

Two-layer design:
  Flask HTTP API (port 5002)  ←→  threading.Queue pair  ←→  uAgent (port 8002)

The uAgent uses on_interval to drain the send queue every 0.5 s, so Flask routes
never need to touch asyncio.  Replies arrive via the uAgent's Chat Protocol handler
and are placed in the reply queue for Flask to read.

Usage:
    pip install -r webapp/requirements-bridge.txt
    python webapp/agent_bridge.py
"""
import os
import queue
import threading
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

AGENT_ADDRESS = os.getenv(
    "TEAMMATE_AGENT_ADDRESS",
    "agent1qvlz2wl73xpgz4hxhrq03ptt7px6utjm7pjkhm3exazfk3ljvmam5vnkyy8",
)
BRIDGE_SEED = os.getenv("AGENT_SECRET_KEY", "vaultmind-bridge-seed-phrase-01")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8002"))
FLASK_PORT = int(os.getenv("FLASK_PORT", "5002"))
_REPLY_MAXSIZE = 10

# ── Queue pair (cross-thread communication) ───────────────────────────────────

_send_q: queue.Queue[str] = queue.Queue()
_reply_q: queue.Queue[str] = queue.Queue(maxsize=_REPLY_MAXSIZE)


def enqueue_send(message: str) -> None:
    """Flask → uAgent: put a message in the outbound queue and clear any stale reply."""
    clear_reply_queue()
    _send_q.put_nowait(message)


def dequeue_send(timeout: float = 0) -> str | None:
    """uAgent interval handler: non-blocking drain of the send queue."""
    try:
        return _send_q.get(timeout=timeout) if timeout > 0 else _send_q.get_nowait()
    except queue.Empty:
        return None


def enqueue_reply(text: str) -> None:
    """uAgent reply handler: put reply in the reply queue, evicting oldest if full."""
    if _reply_q.full():
        try:
            _reply_q.get_nowait()
        except queue.Empty:
            pass
    try:
        _reply_q.put_nowait(text)
    except queue.Full:
        pass  # race condition safety


def dequeue_reply() -> str | None:
    """Flask /response: pop the latest reply (non-blocking)."""
    try:
        return _reply_q.get_nowait()
    except queue.Empty:
        return None


def clear_reply_queue() -> None:
    """Discard all queued replies (called before each new send)."""
    while True:
        try:
            _reply_q.get_nowait()
        except queue.Empty:
            break


# ── Flask HTTP API ────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)


@app.route("/send", methods=["POST"])
def send():
    body = request.json or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message required"}), 400
    enqueue_send(message)
    logger.info("Queued outbound message: %s", message[:80])
    return jsonify({"ok": True})


@app.route("/response", methods=["GET"])
def get_response():
    return jsonify({"reply": dequeue_reply()})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "bridge_port": BRIDGE_PORT})


# ── uAgent (runs in background thread) ───────────────────────────────────────

def _run_agent() -> None:
    """
    Start the uAgent.  Blocks until process exits.
    All uagents imports are deferred here so the module loads without the package
    installed (same pattern as vaultmind/orchestrator/__init__.py).
    """
    try:
        from uagents import Agent, Context, Protocol
        from uagents_core.contrib.protocols.chat import (
            ChatMessage,
            ChatAcknowledgement,
            TextContent,
        )
    except ImportError as exc:
        logger.error(
            "uagents/uagents-core not installed. "
            "Run: pip install -r webapp/requirements-bridge.txt\n%s",
            exc,
        )
        return

    bridge = Agent(
        name="vaultmind-bridge",
        seed=BRIDGE_SEED,
        port=BRIDGE_PORT,
        endpoint=[f"http://localhost:{BRIDGE_PORT}/submit"],
    )
    logger.info("Bridge agent address: %s", bridge.address)

    chat_proto = Protocol(name="AgentChatProtocol", version="0.3.0")

    @bridge.on_interval(period=0.5)
    async def _drain_send_queue(ctx: Context) -> None:
        """Poll the send queue every 0.5 s and forward any pending message."""
        msg = dequeue_send()
        if msg is None:
            return
        payload = ChatMessage(content=[TextContent(text=msg)])
        await ctx.send(AGENT_ADDRESS, payload)
        logger.info("Bridge → agent: %s", msg[:80])

    @chat_proto.on_message(ChatMessage)
    async def _on_reply(ctx: Context, sender: str, msg: ChatMessage) -> None:
        text = " ".join(
            item.text for item in msg.content if hasattr(item, "text")
        )
        logger.info("Bridge ← agent reply: %s", text[:120])
        enqueue_reply(text)
        ack = ChatAcknowledgement(acknowledged=True)
        await ctx.send(sender, ack)

    @chat_proto.on_message(ChatAcknowledgement)
    async def _on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
        logger.debug("Bridge: ack from %s", sender)

    bridge.include(chat_proto, publish_manifest=True)
    bridge.run()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    agent_thread = threading.Thread(target=_run_agent, daemon=True)
    agent_thread.start()
    logger.info("Bridge Flask API starting on port %d", FLASK_PORT)
    app.run(port=FLASK_PORT, threaded=True)
```

- [ ] **Step 2: Make `webapp` importable as a package (needed for tests)**

Check if `webapp/__init__.py` exists:
```bash
ls webapp/__init__.py 2>/dev/null || echo "missing"
```

If missing, create it:
```bash
touch webapp/__init__.py
```

- [ ] **Step 3: Run the failing tests — they should now pass**

Run:
```
pytest tests/test_agent_bridge.py -v
```
Expected: All 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add webapp/agent_bridge.py webapp/__init__.py
git commit -m "feat(bridge): rewrite as proper uAgent (port 8002) + Flask API (port 5002)"
```

---

## Task 4: Verify End-to-End Connectivity

This task is a manual smoke test — no automated test can cover a live Fetch.AI network connection without running agents.

**Pre-requisite:** The teammate's Orchestrator uAgent must be running (they start it with `python -m vaultmind.orchestrator` or equivalent).

- [ ] **Step 1: Start the bridge**

In one terminal:
```
cd webapp && python agent_bridge.py
```
Expected log lines:
```
INFO  Bridge agent address: agent1q...
INFO  Bridge Flask API starting on port 5002
```

Confirm the Flask API is up:
```
curl http://localhost:5002/health
```
Expected: `{"ok": true, "bridge_port": 8002}`

- [ ] **Step 2: Send a test message**

```
curl -s -X POST http://localhost:5002/send \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current state of this project?"}'
```
Expected: `{"ok": true}`

Watch the bridge log for:
```
INFO  Bridge → agent: What is the current state of this project?
```

- [ ] **Step 3: Poll for reply**

```
# Poll every 2s for up to 30s
for i in $(seq 1 15); do
  reply=$(curl -s http://localhost:5002/response)
  echo "$reply"
  echo "$reply" | python -c "import sys,json; d=json.load(sys.stdin); exit(0 if d['reply'] else 1)" && break
  sleep 2
done
```

Expected when teammate's agent replies: `{"reply": "TaskFlow — current focus: ..."}` (or similar intent-A response).

**If the reply never arrives after 30 s, diagnose:**
- Check the bridge log for `Bridge ← agent reply:` — if absent, the teammate's agent did not reply OR the reply was delivered to the wrong address
- Check the teammate's side: did they receive the message? (they should see `Orchestrator received:` in their log)
- If messages aren't reaching the teammate: their agent may be offline, or the address in `AGENT_ADDRESS` may be wrong — confirm the address with the teammate

- [ ] **Step 4: Test via Next.js API**

With the bridge running, start Next.js dev server (`npm run dev` from `webapp/`), then:
```
curl -s -X POST http://localhost:3000/api/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the open questions?"}'
```
Expected: `{"reply": "..."}` within 30 s.

- [ ] **Step 5: Commit smoke-test confirmation**

```bash
git commit --allow-empty -m "chore: confirm end-to-end Fetch.AI bridge smoke test passes"
```

---

## Task 5: Fix Missing .env.local Keys

**Files:**
- Modify: `webapp/.env.local` (add missing keys if absent)

- [ ] **Step 1: Check current .env.local**

Read `webapp/.env.local` and confirm these keys are present. If any are missing, add them:

```
# Fetch.AI bridge config
AGENT_SECRET_KEY=vaultmind-bridge-seed-phrase-01
TEAMMATE_AGENT_ADDRESS=agent1qvlz2wl73xpgz4hxhrq03ptt7px6utjm7pjkhm3exazfk3ljvmam5vnkyy8
BRIDGE_PORT=8002
FLASK_PORT=5002
AGENT_BRIDGE_URL=http://localhost:5002
```

`AGENTVERSE_API_KEY` is only needed if you later want to register the bridge in the Agentverse directory — leave it out for now.

- [ ] **Step 2: Verify Next.js picks up AGENT_BRIDGE_URL**

`webapp/src/app/api/agent/route.ts:3` already reads:
```typescript
const BRIDGE_URL = process.env.AGENT_BRIDGE_URL ?? "http://localhost:5002";
```
So this key is optional (defaults correctly). No change needed to the TypeScript route.

- [ ] **Step 3: Commit if .env.local was modified**

```bash
git add webapp/.env.local
git commit -m "chore(bridge): add Fetch.AI env keys to .env.local"
```

---

## Self-Review

### Spec coverage check

| Requirement | Covered by |
|---|---|
| Bridge can send to teammate's agent | Task 3: `_drain_send_queue` on_interval, Task 4 smoke test |
| Bridge receives teammate's reply | Task 3: `_on_reply` Chat Protocol handler |
| Flask `/send` endpoint | Task 3: `send()` Flask route |
| Flask `/response` endpoint | Task 3: `get_response()` Flask route |
| Next.js API route continues to work unchanged | Task 4 Step 4 |
| Missing packages installed | Task 1 |
| Queue isolation (old replies don't leak) | Task 2: `test_enqueue_send_clears_old_reply`, Task 3: `enqueue_send` calls `clear_reply_queue` |
| Thread safety | `threading.Queue` is thread-safe by design |

### Placeholder scan: none found — all steps have concrete code.

### Type consistency

- `enqueue_send(message: str)` → Task 2 `enqueue_send("hello teammate")` ✓
- `dequeue_send(timeout: float = 0) -> str | None` → Task 2 `dequeue_send(timeout=0.1)` ✓
- `enqueue_reply(text: str)` → Task 2 `enqueue_reply("agent says hi")` ✓
- `dequeue_reply() -> str | None` → Task 2 `dequeue_reply()` ✓
- `clear_reply_queue()` → Task 2 `clear_reply_queue()` ✓
- All consistent across Task 2 (tests) and Task 3 (implementation).
