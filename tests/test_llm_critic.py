"""Tests for LLMCritic — provider-agnostic, gracefully degrading content critic.

The critical, testable behaviours without any API key:
- no credentials → UNVERIFIABLE (graceful degradation, never crashes)
- no corpus → UNVERIFIABLE
- verdict parsing (CONSISTENT / CONTRADICTION / fallback to UNVERIFIABLE)
- on-disk caching keyed by claim+context hash

The actual HTTP/LLM calls are mocked via ``_call_llm`` so no network or API
key is needed — matching the framework's "no data → no penalty" pattern.
"""

from __future__ import annotations

from isnad.critics.llm import LLMCritic, _hash_claim
from isnad.types import ContentVerdict


class TestGracefulDegradation:
    def test_no_credentials_returns_unverifiable(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        critic = LLMCritic()  # no base_url, no api_key
        assert (
            critic.evaluate("F = ma", "f = ma", ["F = ma"], "physics")
            == ContentVerdict.UNVERIFIABLE
        )

    def test_empty_corpus_returns_unverifiable(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
        critic = LLMCritic()  # has anthropic key but no corpus
        assert critic.evaluate("F = ma", "f = ma", [], "physics") == ContentVerdict.UNVERIFIABLE


class TestVerdictParsing:
    def _critic_with(self, llm_response: str, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
        critic = LLMCritic()

        def fake_call(prompt):
            return llm_response

        monkeypatch.setattr(critic, "_call_llm", fake_call)
        # Give it a populated retriever so it reaches the LLM call.
        critic._retriever.evaluate("f = ma", "f = ma", ["f = ma"])
        return critic

    def test_contradiction_parsed(self, monkeypatch):
        critic = self._critic_with("CONTRADICTION", monkeypatch)
        assert (
            critic.evaluate("f ≠ ma", "f != ma", ["f = ma"], "physics")
            == ContentVerdict.CONTRADICTION
        )

    def test_consistent_parsed(self, monkeypatch):
        critic = self._critic_with("CONSISTENT", monkeypatch)
        assert (
            critic.evaluate("F = ma", "f = ma", ["f = ma"], "physics") == ContentVerdict.CONSISTENT
        )

    def test_garbage_falls_back_to_unverifiable(self, monkeypatch):
        critic = self._critic_with("SOME RANDOM GIBBERISH", monkeypatch)
        assert (
            critic.evaluate("F = ma", "f = ma", ["f = ma"], "physics")
            == ContentVerdict.UNVERIFIABLE
        )


class TestCaching:
    def test_cache_round_trips(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
        critic = LLMCritic(cache_dir=str(tmp_path))

        def fake_call(prompt):
            return "CONSISTENT"

        monkeypatch.setattr(critic, "_call_llm", fake_call)
        critic._retriever.evaluate("f = ma", "f = ma", ["f = ma"])

        v1 = critic.evaluate("F = ma", "f = ma", ["f = ma"], "physics")
        assert v1 == ContentVerdict.CONSISTENT

        # Second call hits the cache; a changed fake response would not matter.
        def fake_call2(prompt):
            return "CONTRADICTION"

        monkeypatch.setattr(critic, "_call_llm", fake_call2)
        v2 = critic.evaluate("F = ma", "f = ma", ["f = ma"], "physics")
        assert v2 == ContentVerdict.CONSISTENT  # served from cache


def test_hash_claim_stable():
    assert _hash_claim("hello") == _hash_claim("hello")
    assert len(_hash_claim("hello")) == 16
    assert _hash_claim("hello") != _hash_claim("world")


class TestDeepSeekConvenience:
    def test_deepseek_env_var_sets_defaults(self, monkeypatch) -> None:
        """DEEPSEEK_API_KEY defaults to the DeepSeek endpoint + model."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        critic = LLMCritic()
        assert critic.api_key == "sk-test"
        assert critic.base_url == "https://api.deepseek.com/v1"
        assert critic.model == "deepseek-chat"
        assert critic._has_credentials() is True

    def test_explicit_args_override_deepseek_env(self, monkeypatch) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
        critic = LLMCritic(base_url="https://custom.example/v1", api_key="sk-explicit")
        assert critic.base_url == "https://custom.example/v1"
        assert critic.api_key == "sk-explicit"
