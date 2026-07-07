"""Tests for ISNAD × LangChain integration.

Tests the tracer, decorator, registry seeding, and critic adapter
WITHOUT requiring LangChain or network access.
"""

from __future__ import annotations

import pytest

from isnad.integrations.langchain import CriticAdapter, isnad_track, seed_registry
from isnad.registry import Registry
from isnad.types import (
    ContentVerdict,
    NarratorGrade,
)


class TestSeedRegistry:
    def test_creates_registry_from_dict(self) -> None:
        reg = seed_registry(
            {
                "source:my-docs": "reliable",
                "model:gpt-4o": "acceptable",
                "model:gpt-3.5": "weak",
            }
        )
        assert isinstance(reg, Registry)
        assert reg.get_grade("source:my-docs", "general") == NarratorGrade.RELIABLE
        assert reg.get_grade("model:gpt-4o", "general") == NarratorGrade.ACCEPTABLE
        assert reg.get_grade("model:gpt-3.5", "general") == NarratorGrade.WEAK
        assert len(reg) == 3

    def test_unknown_grade_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown grade"):
            seed_registry({"model:x": "supergood"})

    def test_rejected_grade_works(self) -> None:
        reg = seed_registry({"model:bad": "rejected"})
        assert reg.get_grade("model:bad", "general") == NarratorGrade.REJECTED

    def test_multiple_narrators(self) -> None:
        reg = seed_registry(
            {
                "source:docs": "reliable",
                "retriever:v1": "acceptable",
                "tool:calc": "acceptable",
                "model:llm": "acceptable",
            },
            domain="physics",
        )
        assert len(reg) == 4
        for nid in ["source:docs", "retriever:v1", "tool:calc", "model:llm"]:
            assert reg.get(nid, "physics") is not None


class TestIsnadtrackDecorator:
    def test_records_chain_for_function(self) -> None:
        reg = Registry()
        reg.register("my-func", "general", grade=NarratorGrade.ACCEPTABLE)

        @isnad_track(registry=reg, narrator_id="my-func")
        def answer(q: str) -> str:
            return f"Answer to: {q}"

        result = answer("test")
        assert result == "Answer to: test"
        assert hasattr(answer, "_last_grade")
        assert answer._last_grade is not None

    def test_auto_registers_narrator(self) -> None:
        reg = Registry()

        @isnad_track(registry=reg, narrator_id="auto-func")
        def compute(x: str) -> str:
            return x

        compute("hello")
        assert ("auto-func", "general") in reg


class TestCriticAdapter:
    def test_adapter_with_callable(self) -> None:
        def my_critic(claim: str, corpus: list, domain: str) -> ContentVerdict:
            return ContentVerdict.CONSISTENT

        critic = CriticAdapter(my_critic)
        result = critic.evaluate("hello", "hello", [], "general")
        assert result == ContentVerdict.CONSISTENT

    def test_adapter_with_contradiction(self) -> None:
        def my_critic(claim: str, corpus: list, domain: str) -> ContentVerdict:
            if "wrong" in claim:
                return ContentVerdict.CONTRADICTION
            return ContentVerdict.UNVERIFIABLE

        critic = CriticAdapter(my_critic)
        assert critic.evaluate("wrong", "wrong", [], "g") == ContentVerdict.CONTRADICTION
        assert critic.evaluate("ok", "ok", [], "g") == ContentVerdict.UNVERIFIABLE

    def test_adapter_defaults_to_unverifiable(self) -> None:
        def bad_critic(claim: str, corpus: list, domain: str) -> str:
            return "garbage"

        critic = CriticAdapter(bad_critic)
        assert critic.evaluate("x", "x", [], "g") == ContentVerdict.UNVERIFIABLE
