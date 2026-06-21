import os
import pathlib
import sys
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import find_dotenv, load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

load_dotenv(find_dotenv())

# Allow importing vaultmind package from the parent repo directory
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from vaultmind.orchestrator import handle_intent  # noqa: E402

AGENT_SEED = os.getenv("AGENT_SEED_PHRASE")
VAULT_ROOT = pathlib.Path(os.getenv("VAULTMIND_VAULT_ROOT", "../vault"))

agent = Agent(
    name="vault_mind_orchestrate",
    seed=AGENT_SEED,
    port=8000,
    mailbox=True,
    publish_agent_details=True,
)

chat_proto = Protocol(spec=chat_protocol_spec)


def agent_workflow(query: str) -> str:
    return handle_intent(query, VAULT_ROOT)


@chat_proto.on_message(ChatMessage)
async def handle_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(
            timestamp=datetime.now(tz=timezone.utc),
            acknowledged_msg_id=msg.msg_id,
        ),
    )

    text = " ".join(item.text for item in msg.content if isinstance(item, TextContent))
    ctx.logger.info(f"Received: {text!r}")

    answer = agent_workflow(text)

    await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.now(tz=timezone.utc),
            msg_id=uuid4(),
            content=[
                TextContent(type="text", text=answer),
                EndSessionContent(type="end-session"),
            ],
        ),
    )


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(chat_proto, publish_manifest=True)


@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"vault_mind_orchestrate started with address: {agent.address}")


if __name__ == "__main__":
    agent.run()
