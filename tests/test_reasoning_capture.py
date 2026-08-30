"""Tests for reasoning-chain capture (#15).

Reasoning models emit hidden chain-of-thought before their final answer.
These tests pin that the callback handler captures it where the provider
exposes it, hash-by-default (no raw text stored), and marks redaction/absence
honestly.
"""

from __future__ import annotations

import pytest

from isnad.integrations.langchain.callback import IsnadCallbackHandler
from isnad.core.registry import Registry
from isnad.trace.schema import ReasoningCapture


class _Msg:
    """A minimal LangChain-like message stand-in."""

    def __init__(self, content, additional_kwargs=None, content_blocks=None):
        self.content = content
        self.additional_kwargs = additional_kwargs or {}
        self.content_blocks = content_blocks


def _handler() -> IsnadCallbackHandler:
    return IsnadCallbackHandler(registry=Registry(), domain="physics")


class TestExtractReasoning:
    def test_no_reasoning_returns_none(self):
        resp = _Msg("just an answer")
        assert IsnadCallbackHandler._extract_reasoning(resp) is None

    def test_deepseek_additional_kwargs(self):
        resp = _Msg("answer", additional_kwargs={"reasoning_content": "step 1: think hard"})
        rc = IsnadCallbackHandler._extract_reasoning(resp)
        assert rc is not None
        assert rc.content_hash is not None
        assert rc.preview == "step 1: think hard"
        assert rc.source == "additional_kwargs"

    def test_content_blocks_reasoning(self):
        resp = _Msg(
            "answer",
            content_blocks=[{"type": "reasoning", "reasoning": "I reasoned about this"}],
        )
        rc = IsnadCallbackHandler._extract_reasoning(resp)
        assert rc is not None
        assert rc.source == "content_blocks"
        assert rc.content_hash is not None

    def test_redacted_thinking_marks_redacted(self):
        resp = _Msg("answer", content_blocks=[{"type": "redacted_thinking"}])
        rc = IsnadCallbackHandler._extract_reasoning(resp)
        assert rc is not None
        assert rc.redacted is True
        assert rc.content_hash is None
        assert rc.source == "anthropic"

    def test_anthropic_thinking_block(self):
        resp = _Msg(
            "answer",
            content_blocks=[{"type": "thinking", "thinking": "let me consider this"}],
        )
        rc = IsnadCallbackHandler._extract_reasoning(resp)
        assert rc is not None
        assert rc.source == "anthropic"
        assert rc.content_hash is not None


class TestReasoningHashByDefault:
    def test_raw_reasoning_never_stored(self):
        """Only hash + preview — the raw reasoning text must not be persisted."""
        secret = "my api key is sk-12345 and my ssn is 111-22-3333"
        resp = _Msg("answer", additional_kwargs={"reasoning_content": secret})
        rc = IsnadCallbackHandler._extract_reasoning(resp)
        assert rc is not None
        # The ReasoningCapture has no field for raw text.
        assert not hasattr(rc, "reasoning_text")
        assert not hasattr(rc, "raw")
        # The preview truncates, but even it must not contain the full secret.
        assert rc.preview == secret[:120]
        # The hash is present and deterministic (full SHA-256).
        assert len(rc.content_hash) == 64


class TestReasoningOnNode:
    def test_on_llm_end_populates_node_reasoning(self):
        handler = _handler()
        rid = "llm-1"
        handler.on_llm_start(
            serialized={"name": "deepseek-r1", "id": "deepseek"},
            prompts=["question"],
            run_id=rid,
        )
        handler.on_llm_end(
            response=_Msg("final answer", additional_kwargs={"reasoning_content": "thinking..."}),
            run_id=rid,
        )
        node = handler._nodes.get(rid)
        assert node is not None
        assert node.reasoning is not None
        assert node.reasoning.content_hash is not None

    def test_on_llm_end_no_reasoning_leaves_none(self):
        handler = _handler()
        rid = "llm-2"
        handler.on_llm_start(serialized={"name": "gpt-4o"}, prompts=["q"], run_id=rid)
        handler.on_llm_end(response=_Msg("plain answer"), run_id=rid)
        node = handler._nodes.get(rid)
        assert node is not None
        assert node.reasoning is None


class TestSchemaRoundTrip:
    def test_reasoning_capture_round_trips(self):
        rc = ReasoningCapture(
            content_hash="abc123def4567890",
            preview="step 1",
            source="deepseek",
        )
        data = rc.model_dump_json()
        rc2 = ReasoningCapture.model_validate_json(data)
        assert rc2.content_hash == "abc123def4567890"
        assert rc2.preview == "step 1"
        assert rc2.source == "deepseek"

    def test_transmitter_node_accepts_reasoning(self):
        from isnad.trace.schema import TransmitterNode, Grade, Role

        node = TransmitterNode(
            node_id="n1",
            role=Role.SYNTHESIS,
            narrator_id="model:deepseek-r1",
            step=0,
            grade=Grade(narrator_id="model:deepseek-r1", role=Role.SYNTHESIS, domain="physics"),
            reasoning=ReasoningCapture(content_hash="h", preview="p", source="deepseek"),
        )
        assert node.reasoning is not None
        assert node.reasoning.source == "deepseek"
