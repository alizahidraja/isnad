"""Tests for NLI-based critics — graceful degradation, interface compliance."""

import pytest

from isnad.critics.nli import HybridCritic, LocalNLICritic
from isnad.types import ContentVerdict


class TestLocalNLICritic:
    def test_graceful_degradation_no_model(self) -> None:
        """Without sentence-transformers, returns UNVERIFIABLE."""
        critic = LocalNLICritic()
        result = critic.evaluate(
            "F = ma", "f = m a",
            ["force equals mass times acceleration"], "physics",
        )
        assert result == ContentVerdict.UNVERIFIABLE

    def test_empty_corpus(self) -> None:
        critic = LocalNLICritic()
        assert critic.evaluate("x", "x", []) == ContentVerdict.UNVERIFIABLE

    def test_default_thresholds_reasonable(self) -> None:
        critic = LocalNLICritic()
        assert 0.5 <= critic.entailment_threshold <= 0.9
        assert 0.4 <= critic.contradiction_threshold <= 0.7


class TestHybridCritic:
    def test_graceful_degradation(self) -> None:
        critic = HybridCritic()
        result = critic.evaluate("x", "x", ["x"])
        assert result == ContentVerdict.UNVERIFIABLE

    def test_empty_corpus(self) -> None:
        assert HybridCritic().evaluate("x", "x", []) == ContentVerdict.UNVERIFIABLE

    def test_default_config(self) -> None:
        critic = HybridCritic()
        assert critic.top_k == 10
        assert 0.5 <= critic.entailment_threshold <= 0.9
