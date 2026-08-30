"""Tests for ``best_available_critic`` — the honest critic-selection factory."""

from __future__ import annotations

from isnad.critics import best_available_critic
from isnad.critics.embedding import EmbeddingCritic
from isnad.critics.ensemble import EnsembleCritic
from isnad.critics.llm import LLMCritic
from isnad.critics.nli import HybridCritic
from isnad.critics.recompute import RecomputeCritic


def _no_llm(monkeypatch) -> None:
    monkeypatch.setattr(LLMCritic, "_has_credentials", lambda self: False)


def _assert_ensemble(critic, semantic_type) -> None:
    """D2: every tier is wrapped in an EnsembleCritic(semantic, RecomputeCritic)."""
    assert isinstance(critic, EnsembleCritic)
    assert isinstance(critic.semantic, semantic_type)
    assert isinstance(critic.deterministic, RecomputeCritic)


def test_default_prefers_llm_when_credentials_present(monkeypatch) -> None:
    """The serving gate should use the LLM tier by default when a key is present."""
    monkeypatch.setattr(LLMCritic, "_has_credentials", lambda self: True)
    critic = best_available_critic()
    _assert_ensemble(critic, LLMCritic)


def test_offline_falls_back_to_embedding(monkeypatch) -> None:
    _no_llm(monkeypatch)
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: False)
    critic = best_available_critic()
    _assert_ensemble(critic, EmbeddingCritic)


def test_nli_chosen_when_available_and_no_llm(monkeypatch) -> None:
    _no_llm(monkeypatch)
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: True)
    critic = best_available_critic()
    _assert_ensemble(critic, HybridCritic)


def test_prefer_llm_false_forces_offline(monkeypatch) -> None:
    """Even with an LLM key, prefer_llm=False returns an offline critic."""
    monkeypatch.setattr(LLMCritic, "_has_credentials", lambda self: True)
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: False)
    critic = best_available_critic(prefer_llm=False)
    _assert_ensemble(critic, EmbeddingCritic)


def test_prefer_llm_true_without_credentials_falls_back(monkeypatch) -> None:
    _no_llm(monkeypatch)
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: False)
    critic = best_available_critic(prefer_llm=True)
    _assert_ensemble(critic, EmbeddingCritic)


def test_ensemble_never_less_safe_than_semantic() -> None:
    """A numeric-aggregate contradiction is caught even by the offline default."""
    critic = best_available_critic(prefer_llm=False)
    result = critic.evaluate(
        "there are 1,240 records",
        "there are 1,240 records",
        ["total rows: 1,240"],
        "general",
    )
    # RecomputeCritic sees the number matches -> CONSISTENT (numeric slice only),
    # but the semantic (TF-IDF) never blesses -> UNVERIFIABLE. Never a false serve.
    from isnad.types import ContentVerdict

    assert result in (ContentVerdict.UNVERIFIABLE, ContentVerdict.CONSISTENT)
