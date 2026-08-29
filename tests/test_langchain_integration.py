"""Tests for ISNAD × LangChain integration.

Tests the tracer, decorator, registry seeding, and critic adapter
WITHOUT requiring LangChain or network access.
"""

from __future__ import annotations

import pytest

from isnad.core.registry import Registry
from isnad.integrations.langchain import CriticAdapter, isnad_track, seed_registry
from isnad.integrations.langchain.tracer import IsnadTracer
from isnad.types import (
    ContentVerdict,
    NarratorGrade,
)


class TestSeedRegistry:
    def test_creates_registry_from_dict(self) -> None:
        reg = seed_registry({
            "source:my-docs": "reliable",
            "model:gpt-4o": "acceptable",
            "model:gpt-3.5": "weak",
        })
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


class TestExtractModelVersion:
    def test_openai_style_invocation_model(self) -> None:
        version = IsnadTracer._extract_model_version(
            {},
            {"invocation_params": {"model": "gpt-4o-2024-08-06"}},
        )
        assert version == "gpt-4o-2024-08-06"

    def test_anthropic_style_invocation_model(self) -> None:
        version = IsnadTracer._extract_model_version(
            {},
            {"invocation_params": {"model": "claude-3-5-sonnet-20241022"}},
        )
        assert version == "claude-3-5-sonnet-20241022"

    def test_metadata_model_version_takes_priority(self) -> None:
        version = IsnadTracer._extract_model_version(
            {},
            {
                "metadata": {"model_version": "2.0"},
                "invocation_params": {"model": "gpt-4o"},
            },
        )
        assert version == "2.0"

    def test_langsmith_ls_model_version(self) -> None:
        version = IsnadTracer._extract_model_version(
            {},
            {"metadata": {"ls_model_version": "2024-08-06"}},
        )
        assert version == "2024-08-06"

    def test_serialized_kwargs_fallback(self) -> None:
        version = IsnadTracer._extract_model_version(
            {"kwargs": {"model_name": "gpt-4o-mini"}},
            {},
        )
        assert version == "gpt-4o-mini"

    def test_skips_empty_values_and_falls_through(self) -> None:
        version = IsnadTracer._extract_model_version(
            {"kwargs": {"model_version": "  ", "model": "gpt-4o"}},
            {"metadata": {"model_version": ""}, "invocation_params": {"model_version": None}},
        )
        assert version == "gpt-4o"

    def test_returns_none_when_no_identity_found(self) -> None:
        assert IsnadTracer._extract_model_version({}, {}) is None


class TestTracerLifecycle:
    """The tracer's callback lifecycle and report methods (no LangChain run needed)."""

    def _tracer(self) -> IsnadTracer:
        reg = seed_registry({"source:docs": "reliable", "model:gpt-4o": "acceptable"})
        return IsnadTracer(registry=reg)

    def test_empty_report(self):
        assert self._tracer().report() == "No claims recorded."

    def test_empty_graded_chains(self):
        assert self._tracer().graded_chains() == []

    def test_chain_start_adds_link(self):
        tracer = self._tracer()
        tracer.on_chain_start({"name": "rag", "id": "rag"}, {})
        assert len(tracer._links) == 1
        assert tracer._links[0].narrator_id == "rag"
        assert tracer._links[0].transform_type.value == "pass_through"

    def test_llm_start_extracts_version(self):
        tracer = self._tracer()
        tracer.on_llm_start(
            {"name": "gpt-4o", "id": "gpt-4o"},
            ["prompt"],
            invocation_params={"model": "gpt-4o-2024-08-06"},
        )
        assert tracer._links[0].narrator_id == "model:gpt-4o"
        assert tracer._links[0].version == "gpt-4o-2024-08-06"
        assert tracer._links[0].transform_type.value == "generative"

    def test_retriever_end_adds_destructive_links(self):
        tracer = self._tracer()

        class Doc:
            metadata = {"source": "openstax.org"}

        tracer.on_retriever_end([Doc(), Doc()], run_id="r1")
        assert len(tracer._links) == 2
        assert all(l.transform_type.value == "destructive" for l in tracer._links)
        assert all(l.narrator_id == "retriever:openstax.org" for l in tracer._links)

    def test_tool_start_adds_destructive_link(self):
        tracer = self._tracer()
        tracer.on_tool_start({"name": "calculator"}, "")
        assert tracer._links[0].narrator_id == "tool:calculator"
        assert tracer._links[0].transform_type.value == "destructive"

    def test_full_flow_produces_graded_claim_and_report(self):
        tracer = self._tracer()
        tracer.on_chain_start({"name": "rag"}, {})
        tracer.on_llm_start({"name": "gpt-4o", "id": "gpt-4o"}, ["p"])
        tracer.on_chain_end({"output": "F = ma"})

        graded = tracer.graded_chains()
        assert len(graded) == 1
        assert graded[0]["claim_text"] == "F = ma"
        assert "chain_grade" in graded[0]
        assert "action" in graded[0]

        report = tracer.report()
        assert "ISNAD Report — 1 claims" in report
        assert "F = ma" in report


class TestTracerContentCriticismCorpus:
    """The tracer must pass its retrieved documents as the critic's corpus,
    so content criticism is real rather than an empty-corpus no-op (#183)."""

    def _build_tracer(self):
        reg = Registry()
        reg.register("source:docs", "physics", grade=NarratorGrade.RELIABLE)
        reg.register("model:gpt-4o", "physics", grade=NarratorGrade.RELIABLE)
        from isnad.matn import DeterministicRuleCritic

        tracer = IsnadTracer(registry=reg, critic=DeterministicRuleCritic(), domain="physics")
        return tracer

    def test_retrieved_texts_become_the_critic_corpus(self):
        tracer = self._build_tracer()
        # Feed a corpus claim the deterministic critic knows, then a claim that
        # contradicts it — the critic can only see the contradiction through the
        # retrieved-text corpus, not through an empty list.
        tracer.on_retriever_end(
            documents=[type("D", (), {"page_content": "p = mv", "metadata": {}})()],
            run_id="r1",
        )
        assert tracer._retrieved_texts == ["p = mv"]

        # A claim that contradicts the retrieved corpus.
        tracer.on_chain_end(outputs={"output": "p = h/lambda"})
        (graded,) = tracer.graded_chains()
        assert graded["content_verdict"] == ContentVerdict.CONTRADICTION
        # The chain is DAIF (retriever:document is ungraded) × CONTRADICTION
        # → QUARANTINE. The point: a real contradiction, not an empty-corpus no-op.
        assert graded["action"].value == "quarantine"

    def test_no_retrieved_docs_means_empty_corpus_still_safe(self):
        tracer = self._build_tracer()
        tracer.on_chain_end(outputs={"output": "p = h/lambda"})
        (graded,) = tracer.graded_chains()
        # No retrieved docs → critic returns UNVERIFIABLE, never a false
        # CONTRADICTION from an empty corpus.
        assert graded["content_verdict"] == ContentVerdict.UNVERIFIABLE
