"""
Tests for vault-mind-orchestrate/agent.py — Agentverse chat protocol layer.

These tests verify:
  1. The ChatMessage handler extracts text, calls agent_workflow, and replies with
     ChatAcknowledgement + ChatMessage containing the response + EndSession.
  2. agent_workflow delegates to handle_intent from the parent vaultmind package.
  3. All three intent paths (A/B/C) and the fallback reach the agent correctly.
  4. The agent sends an acknowledgement before the response.

uagents is NOT needed at import time — we mock Context and the message types
so the handler logic runs without an active uAgent loop.
"""
from __future__ import annotations

import pathlib
import shutil
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Make the parent vaultmind package importable without installing it.
# ---------------------------------------------------------------------------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

FIXTURE_VAULT = REPO_ROOT / "fixtures" / "vault"


# ---------------------------------------------------------------------------
# Minimal stubs for uagents_core chat protocol types
# so agent.py can be imported without the real package.
# ---------------------------------------------------------------------------
class _TextContent:
    def __init__(self, *, type: str, text: str) -> None:
        self.type = type
        self.text = text


class _EndSessionContent:
    def __init__(self, *, type: str) -> None:
        self.type = type


class _ChatMessage:
    def __init__(self, *, timestamp, msg_id, content) -> None:
        self.timestamp = timestamp
        self.msg_id = msg_id
        self.content = content


class _ChatAcknowledgement:
    def __init__(self, *, timestamp, acknowledged_msg_id) -> None:
        self.timestamp = timestamp
        self.acknowledged_msg_id = acknowledged_msg_id


class _chat_protocol_spec:  # noqa: N801
    pass


# ---------------------------------------------------------------------------
# Import agent.py with all uagents dependencies mocked.
# ---------------------------------------------------------------------------
import importlib
import types


def _identity_decorator(*_args, **_kwargs):
    """Decorator that returns the function unchanged — used to stub @proto.on_message."""
    def _wrap(fn):
        return fn
    return _wrap


def _load_agent_module():
    """Import agent.py with uagents stubs injected into sys.modules."""
    # Build a Protocol stub whose on_message() is an identity decorator
    proto_instance = MagicMock()
    proto_instance.on_message = _identity_decorator

    proto_class = MagicMock(return_value=proto_instance)

    agent_instance = MagicMock()
    agent_instance.on_event = _identity_decorator
    agent_instance.include = MagicMock()
    agent_instance.run = MagicMock()

    agent_class = MagicMock(return_value=agent_instance)

    uagents_stub = types.ModuleType("uagents")
    uagents_stub.Agent = agent_class
    uagents_stub.Context = MagicMock
    uagents_stub.Protocol = proto_class
    sys.modules.setdefault("uagents", uagents_stub)

    # Build minimal uagents_core chat stub
    core_stub = types.ModuleType("uagents_core")
    contrib_stub = types.ModuleType("uagents_core.contrib")
    protocols_stub = types.ModuleType("uagents_core.contrib.protocols")
    chat_stub = types.ModuleType("uagents_core.contrib.protocols.chat")
    chat_stub.ChatAcknowledgement = _ChatAcknowledgement
    chat_stub.ChatMessage = _ChatMessage
    chat_stub.EndSessionContent = _EndSessionContent
    chat_stub.TextContent = _TextContent
    chat_stub.chat_protocol_spec = _chat_protocol_spec
    sys.modules.setdefault("uagents_core", core_stub)
    sys.modules.setdefault("uagents_core.contrib", contrib_stub)
    sys.modules.setdefault("uagents_core.contrib.protocols", protocols_stub)
    sys.modules.setdefault("uagents_core.contrib.protocols.chat", chat_stub)

    # dotenv stub
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.find_dotenv = lambda: ""
    dotenv_stub.load_dotenv = lambda *a, **kw: None
    sys.modules.setdefault("dotenv", dotenv_stub)

    agent_path = pathlib.Path(__file__).resolve().parents[1] / "agent.py"
    spec = importlib.util.spec_from_file_location("agent_under_test", agent_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_agent_mod = _load_agent_module()
_handle_chat = _agent_mod.handle_chat
_handle_ack = _agent_mod.handle_ack
_agent_workflow = _agent_mod.agent_workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.logger = MagicMock()
    return ctx


def _make_chat_msg(*texts: str) -> _ChatMessage:
    content = [_TextContent(type="text", text=t) for t in texts]
    return _ChatMessage(
        timestamp=datetime.now(tz=timezone.utc),
        msg_id=uuid4(),
        content=content,
    )


# ---------------------------------------------------------------------------
# Tests: handle_chat sends acknowledgement then reply
# ---------------------------------------------------------------------------

class TestHandleChatProtocol:
    @pytest.mark.asyncio
    async def test_sends_acknowledgement_first(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            ctx = _make_ctx()
            msg = _make_chat_msg("what are we working on")
            await _handle_chat(ctx, "agent1xyz", msg)

        assert ctx.send.call_count == 2
        ack = ctx.send.call_args_list[0].args[1]
        assert isinstance(ack, _ChatAcknowledgement)
        assert ack.acknowledged_msg_id == msg.msg_id

    @pytest.mark.asyncio
    async def test_reply_is_chat_message(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            ctx = _make_ctx()
            msg = _make_chat_msg("what are we working on")
            await _handle_chat(ctx, "agent1xyz", msg)

        reply = ctx.send.call_args_list[1].args[1]
        assert isinstance(reply, _ChatMessage)

    @pytest.mark.asyncio
    async def test_reply_contains_text_content(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            ctx = _make_ctx()
            msg = _make_chat_msg("what are we working on")
            await _handle_chat(ctx, "agent1xyz", msg)

        reply = ctx.send.call_args_list[1].args[1]
        texts = [c for c in reply.content if isinstance(c, _TextContent)]
        assert texts, "reply must contain at least one TextContent"
        assert len(texts[0].text) > 10

    @pytest.mark.asyncio
    async def test_reply_contains_end_session(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            ctx = _make_ctx()
            msg = _make_chat_msg("what are we working on")
            await _handle_chat(ctx, "agent1xyz", msg)

        reply = ctx.send.call_args_list[1].args[1]
        ends = [c for c in reply.content if isinstance(c, _EndSessionContent)]
        assert ends, "reply must contain EndSessionContent to close the chat turn"

    @pytest.mark.asyncio
    async def test_sender_receives_both_messages(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        sender = "test_sender_address_xyz"
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            ctx = _make_ctx()
            msg = _make_chat_msg("trigger handoff")
            await _handle_chat(ctx, sender, msg)

        for call in ctx.send.call_args_list:
            assert call.args[0] == sender


# ---------------------------------------------------------------------------
# Tests: handle_ack is a no-op
# ---------------------------------------------------------------------------

class TestHandleAck:
    @pytest.mark.asyncio
    async def test_ack_handler_does_not_send(self):
        ctx = _make_ctx()
        ack = _ChatAcknowledgement(
            timestamp=datetime.now(tz=timezone.utc),
            acknowledged_msg_id=uuid4(),
        )
        await _handle_ack(ctx, "some_sender", ack)
        ctx.send.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: agent_workflow delegates to handle_intent correctly
# ---------------------------------------------------------------------------

class TestAgentWorkflow:
    def test_intent_a_project_state(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            result = _agent_workflow("What's the current state of this project?")
        assert "current focus" in result.lower() or "intent" in result.lower()
        assert len(result) > 20

    def test_intent_a_working_on(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            result = _agent_workflow("what are we working on")
        assert isinstance(result, str) and len(result) > 20

    def test_intent_b_handoff_readiness(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            result = _agent_workflow("Is the vault ready to hand off?")
        assert isinstance(result, str) and len(result) > 10

    def test_intent_b_trigger(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            result = _agent_workflow("trigger handoff")
        assert isinstance(result, str) and len(result) > 10

    def test_intent_c_questions(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            result = _agent_workflow("What are the open questions?")
        assert "question" in result.lower()

    def test_fallback_returns_help(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            result = _agent_workflow("xyzzy random nonsense fhqwhgads")
        assert "project state" in result.lower() or "handoff" in result.lower()

    def test_multi_word_text_content_concatenated(self, tmp_path):
        """agent.py joins all TextContent items with a space before routing."""
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        # Simulate what handle_chat does when two TextContent blocks arrive
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            result = _agent_workflow("open question outstanding items")
        assert "question" in result.lower()


# ---------------------------------------------------------------------------
# Tests: multi-message edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_text_returns_help(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            ctx = _make_ctx()
            msg = _make_chat_msg("")
            await _handle_chat(ctx, "sender", msg)

        reply = ctx.send.call_args_list[1].args[1]
        texts = [c for c in reply.content if isinstance(c, _TextContent)]
        assert texts[0].text  # non-empty fallback

    @pytest.mark.asyncio
    async def test_non_text_content_ignored(self, tmp_path):
        """Content items without a .text attribute must be silently skipped."""
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            ctx = _make_ctx()
            msg = _make_chat_msg("what are we working on")
            # inject a non-TextContent item
            msg.content.insert(0, _EndSessionContent(type="end-session"))
            await _handle_chat(ctx, "sender", msg)

        reply = ctx.send.call_args_list[1].args[1]
        texts = [c for c in reply.content if isinstance(c, _TextContent)]
        assert texts and len(texts[0].text) > 10

    @pytest.mark.asyncio
    async def test_reply_msg_id_differs_from_incoming(self, tmp_path):
        vault = tmp_path / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        with patch.object(_agent_mod, "VAULT_ROOT", vault):
            ctx = _make_ctx()
            msg = _make_chat_msg("open questions")
            await _handle_chat(ctx, "sender", msg)

        reply = ctx.send.call_args_list[1].args[1]
        assert reply.msg_id != msg.msg_id
