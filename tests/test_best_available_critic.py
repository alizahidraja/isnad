"""Tests for ``best_available_critic`` — the honest critic-selection factory."""

from __future__ import annotations

from isnad.critics import best_available_critic
from isnad.critics.embedding import EmbeddingCritic
from isnad.critics.llm import LLMCritic
from isnad.critics.nli import HybridCritic


def test_offline_falls_back_to_embedding(monkeypatch):
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: False)
    critic = best_available_critic()
    assert isinstance(critic, EmbeddingCritic)


def test_nli_chosen_when_available(monkeypatch):
    # HybridCritic constructs lazily (models load in evaluate), so this is safe.
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: True)
    critic = best_available_critic()
    assert isinstance(critic, HybridCritic)


def test_prefer_llm_without_credentials_falls_back(monkeypatch):
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: False)
    monkeypatch.setattr(LLMCritic, "_has_credentials", lambda self: False)
    critic = best_available_critic(prefer_llm=True)
    assert isinstance(critic, EmbeddingCritic)


def test_prefer_llm_with_credentials_returns_llm(monkeypatch):
    monkeypatch.setattr("isnad.critics._sentence_transformers_available", lambda: False)
    monkeypatch.setattr(LLMCritic, "_has_credentials", lambda self: True)
    critic = best_available_critic(prefer_llm=True)
    assert isinstance(critic, LLMCritic)
