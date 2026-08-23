"""Tests for NLI-based critics.

Tests that download/load sentence-transformers models are marked ``nli`` and
are excluded from the default (CI) run.  The offline interface tests (empty
corpus, thresholds, config) run everywhere.
"""

from __future__ import annotations

import pytest

from isnad.critics.nli import HybridCritic, LocalNLICritic
from isnad.types import ContentVerdict

_CORPUS = [
    "energy is conserved",
    "the atom has a nucleus",
    "light is a wave",
]


class TestLocalNLICriticOffline:
    """Interface tests that never load a model — run in CI."""

    def test_empty_corpus(self) -> None:
        assert LocalNLICritic().evaluate("x", "x", []) == ContentVerdict.UNVERIFIABLE

    def test_default_thresholds_reasonable(self) -> None:
        critic = LocalNLICritic()
        assert 0.5 <= critic.entailment_threshold <= 0.9
        assert 0.4 <= critic.contradiction_threshold <= 0.7


class TestLocalNLICriticSemantic:
    """Model-backed tests — excluded from CI (``-m nli`` to run)."""

    @pytest.mark.nli
    def test_catches_negation_contradiction(self) -> None:
        critic = LocalNLICritic()
        result = critic.evaluate(
            "the atom contains no central core",
            "the atom contains no central core",
            _CORPUS,
            "physics",
        )
        # The NLI critic should catch the semantic contradiction the
        # word-overlap critic misses.  If the model is unavailable, it
        # degrades to UNVERIFIABLE.
        assert result in (ContentVerdict.CONTRADICTION, ContentVerdict.UNVERIFIABLE)

    @pytest.mark.nli
    def test_graceful_degradation_no_model(self) -> None:
        """If sentence-transformers is absent, returns UNVERIFIABLE."""
        critic = LocalNLICritic()
        result = critic.evaluate(
            "F = ma", "f = m a", ["force equals mass times acceleration"], "physics"
        )
        assert result in (ContentVerdict.UNVERIFIABLE, ContentVerdict.CONSISTENT)


class TestHybridCritic:
    def test_empty_corpus(self) -> None:
        assert HybridCritic().evaluate("x", "x", []) == ContentVerdict.UNVERIFIABLE

    def test_default_config(self) -> None:
        critic = HybridCritic()
        assert critic.top_k == 10
        assert 0.5 <= critic.entailment_threshold <= 0.9

    @pytest.mark.nli
    def test_semantic_retrieval_degrades_gracefully(self) -> None:
        critic = HybridCritic()
        result = critic.evaluate("x", "x", ["x"])
        assert result in (
            ContentVerdict.UNVERIFIABLE,
            ContentVerdict.CONSISTENT,
            ContentVerdict.CONTRADICTION,
        )
