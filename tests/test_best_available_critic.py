"""Tests for ``best_available_critic`` — the honest critic-selection factory."""

from __future__ import annotations

from isnad.critics import best_available_critic
from isnad.critics.embedding import EmbeddingCritic
from isnad.critics.llm import LLMCritic
from isnad.critics.nli import HybridCritic


def _no_llm(monkeypatch) -> None:
    monkeypatch.setattr(LLMCritic, "_has_credentials", lambda self: False)


def test_default_prefers_llm_when_credentials_present(monkeypatch) -> None:
    """The serving gate should use the LLM tier by default when a key is present."""
    monkeypatch.setattr(LLMCritic, "_has_credentials", lambda self: True)
    critic = best_available_critic()
    assert isinstance(critic, LLMCritic)


def test_offline_falls_back_to_embedding(monkeypatch) -> None:
    _no_llm(monkeypatch)
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: False)
    critic = best_available_critic()
    assert isinstance(critic, EmbeddingCritic)


def test_nli_chosen_when_available_and_no_llm(monkeypatch) -> None:
    _no_llm(monkeypatch)
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: True)
    critic = best_available_critic()
    assert isinstance(critic, HybridCritic)


def test_prefer_llm_false_forces_offline(monkeypatch) -> None:
    """Even with an LLM key, prefer_llm=False returns an offline critic."""
    monkeypatch.setattr(LLMCritic, "_has_credentials", lambda self: True)
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: False)
    critic = best_available_critic(prefer_llm=False)
    assert isinstance(critic, EmbeddingCritic)


def test_prefer_llm_true_without_credentials_falls_back(monkeypatch) -> None:
    _no_llm(monkeypatch)
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: False)
    critic = best_available_critic(prefer_llm=True)
    assert isinstance(critic, EmbeddingCritic)
