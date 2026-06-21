import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from uagents_core.identity import Identity
from uagents_core.contrib.protocols.chat import ChatMessage, TextContent
from fetchai.communication import send_message_to_agent, parse_message_from_agent
from fetchai.registration import register_with_agentverse
from dotenv import load_dotenv

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Teammate's Orchestrator uAgent address
AGENT_ADDRESS = "agent1qvlz2wl73xpgz4hxhrq03ptt7px6utjm7pjkhm3exazfk3ljvmam5vnkyy8"
client_identity = None
latest_response = None


def init():
    global client_identity
    # Deterministic seed so the bridge keeps the same Agentverse address across restarts
    client_identity = Identity.from_seed(
        os.getenv("AGENT_SECRET_KEY", "vaultmind-bridge-seed-phrase-01"), 0
    )
    logger.info(f"Bridge agent address: {client_identity.address}")
    register_with_agentverse(
        identity=client_identity,
        url="http://localhost:5002/webhook",
        agentverse_token=os.getenv("AGENTVERSE_API_KEY"),
        agent_title="VaultMind Bridge",
        readme="VaultMind bridge agent for Fetch.ai integration.",
    )


@app.route("/send", methods=["POST"])
def send():
    global latest_response
    latest_response = None
    body = request.json or {}
    message = body.get("message", "").strip()
    if not message:
        return jsonify({"error": "message required"}), 400
    try:
        # Wrap in Chat Protocol so the Orchestrator's ChatMessage handler receives it
        payload = ChatMessage(content=[TextContent(text=message)])
        send_message_to_agent(
            client_identity,
            AGENT_ADDRESS,
            payload.model_dump(),
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/webhook", methods=["POST"])
def webhook():
    global latest_response
    try:
        data = parse_message_from_agent(request.get_data().decode())
        payload = data.payload
        # Handle Chat Protocol ChatMessage (content array) or plain {"message": ...}
        if isinstance(payload, dict) and "content" in payload:
            text = ""
            for item in payload.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    text += item.get("text", "")
            latest_response = text or str(payload)
        else:
            latest_response = payload.get("message", str(payload))
        logger.info(f"Agent replied: {latest_response}")
    except Exception as e:
        logger.error(f"Webhook parse error: {e}")
    return jsonify({"ok": True})


@app.route("/response", methods=["GET"])
def get_response():
    return jsonify({"reply": latest_response})


if __name__ == "__main__":
    init()
    app.run(port=5002)
