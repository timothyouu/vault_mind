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
