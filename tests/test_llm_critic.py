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

from isnad.critics.llm import (
    LLMCritic,
    PROVIDERS,
    _hash_claim,
    list_providers,
    resolve_provider,
)
from isnad.types import ContentVerdict


class TestGracefulDegradation:
    def test_no_credentials_returns_unverifiable(self, monkeypatch):
        # Clear *all* provider keys, not just Anthropic's — a lingering
        # DEEPSEEK_API_KEY (or any other) would otherwise auto-detect and
        # make this test environment-sensitive.
        for key in (
            "ANTHROPIC_API_KEY",
            "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GROQ_API_KEY",
            "TOGETHER_API_KEY",
            "ISNAD_LLM_API_KEY",
            "ISNAD_LLM_PROVIDER",
        ):
            monkeypatch.delenv(key, raising=False)
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

    def test_not_consistent_is_not_misparsed_as_consistent(self, monkeypatch):
        """Substring matching used to mislabel NOT-CONSISTENT as CONSISTENT."""
        critic = self._critic_with("The claim is NOT CONSISTENT with the corpus", monkeypatch)
        assert (
            critic.evaluate("f ≠ ma", "f != ma", ["f = ma"], "physics")
            == ContentVerdict.UNVERIFIABLE
        )

    def test_not_contradiction_is_not_misparsed(self, monkeypatch):
        critic = self._critic_with("NOT CONTRADICTION — they agree", monkeypatch)
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


class TestProviderResolution:
    def _clear_keys(self, monkeypatch) -> None:
        for name in (
            "ANTHROPIC_API_KEY",
            "DEEPSEEK_API_KEY",
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GROQ_API_KEY",
            "TOGETHER_API_KEY",
            "ISNAD_LLM_PROVIDER",
            "ISNAD_LLM_MODEL",
            "ISNAD_LLM_API_KEY",
            "ISNAD_LLM_BASE_URL",
        ):
            monkeypatch.delenv(name, raising=False)

    def test_openrouter_env_var(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
        monkeypatch.setenv("ISNAD_LLM_MODEL", "openai/gpt-4o-mini")
        critic = LLMCritic()
        assert critic.provider == "openrouter"
        assert critic.base_url == "https://openrouter.ai/api/v1"
        assert critic.api_key == "sk-or"
        assert critic.model == "openai/gpt-4o-mini"
        assert critic._has_credentials() is True

    def test_openrouter_without_model_is_not_ready(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
        critic = LLMCritic()
        assert critic.provider == "openrouter"
        assert critic._has_credentials() is False  # requires an explicit model

    def test_anthropic_provider(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        critic = LLMCritic()
        assert critic.provider == "anthropic"
        assert critic.api_key == "sk-ant"
        assert critic._has_credentials() is True

    def test_openai_provider(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        monkeypatch.setenv("ISNAD_LLM_MODEL", "gpt-4o")
        critic = LLMCritic()
        assert critic.provider == "openai"
        assert critic.base_url == "https://api.openai.com/v1"
        assert critic.model == "gpt-4o"

    def test_gemini_provider(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("GEMINI_API_KEY", "sk-gem")
        monkeypatch.setenv("ISNAD_LLM_MODEL", "gemini-2.5-flash")
        critic = LLMCritic()
        assert critic.provider == "gemini"
        assert critic.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"

    def test_ollama_no_key_needed(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        critic = LLMCritic(provider="ollama", model="llama3.1")
        assert critic.base_url == "http://localhost:11434/v1"
        assert critic.api_key == ""
        assert critic._has_credentials() is True

    def test_explicit_provider_arg_beats_env(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
        critic = LLMCritic(provider="openrouter", model="openai/gpt-4o", api_key="sk-or")
        assert critic.provider == "openrouter"
        assert critic.api_key == "sk-or"

    def test_unknown_provider_raises(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        import pytest

        with pytest.raises(ValueError):
            LLMCritic(provider="not-a-real-provider")

    def test_llm_provider_env_disambiguates(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        monkeypatch.setenv("ISNAD_LLM_PROVIDER", "openai")
        monkeypatch.setenv("ISNAD_LLM_MODEL", "gpt-4o")
        critic = LLMCritic()
        assert critic.provider == "openai"

    def test_generic_custom_endpoint(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("ISNAD_LLM_BASE_URL", "https://llm.internal/v1")
        monkeypatch.setenv("ISNAD_LLM_API_KEY", "sk-internal")
        monkeypatch.setenv("ISNAD_LLM_MODEL", "my-model")
        critic = LLMCritic()
        assert critic.provider == "custom"
        assert critic.base_url == "https://llm.internal/v1"
        assert critic.api_key == "sk-internal"
        assert critic.model == "my-model"
        assert critic._has_credentials() is True

    def test_list_providers_is_superset(self) -> None:
        names = list_providers()
        for expected in (
            "deepseek",
            "openrouter",
            "openai",
            "anthropic",
            "gemini",
            "groq",
            "together",
            "ollama",
            "custom",
        ):
            assert expected in names
        assert set(names) == set(PROVIDERS)

    def test_resolve_provider_none_when_unconfigured(self, monkeypatch) -> None:
        self._clear_keys(monkeypatch)
        assert resolve_provider(None, None) is None


class TestOpenAICompatCall:
    def _fake_httpx(self, monkeypatch, response_text: str) -> dict:
        import sys
        import types

        captured: dict = {}

        class FakeResp:
            def raise_for_status(self) -> None:
                pass

            def json(self):
                return {"choices": [{"message": {"content": response_text}}]}

        class FakeHttpx:
            @staticmethod
            def post(url, headers, json, timeout):
                captured["url"] = url
                captured["headers"] = headers
                captured["json"] = json
                captured["timeout"] = timeout
                return FakeResp()

        fake_module = types.ModuleType("httpx")
        fake_module.post = FakeHttpx.post
        monkeypatch.setitem(sys.modules, "httpx", fake_module)
        return captured

    def test_openai_compat_call_shape(self, monkeypatch) -> None:
        captured = self._fake_httpx(monkeypatch, "CONTRADICTION")
        critic = LLMCritic(provider="openrouter", api_key="sk-or", model="openai/gpt-4o")
        result = critic._call_openai_compat("test prompt")
        assert result == "CONTRADICTION"
        assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
        assert captured["headers"]["Authorization"] == "Bearer sk-or"
        assert captured["json"]["model"] == "openai/gpt-4o"
        assert captured["json"]["temperature"] == 0.0

    def test_openrouter_attribution_headers(self, monkeypatch) -> None:
        monkeypatch.setenv("ISNAD_LLM_REFERER", "https://example.com")
        monkeypatch.setenv("ISNAD_LLM_TITLE", "my-app")
        captured = self._fake_httpx(monkeypatch, "CONSISTENT")
        critic = LLMCritic(provider="openrouter", api_key="sk-or", model="openai/gpt-4o")
        critic._call_openai_compat("test prompt")
        assert captured["headers"]["HTTP-Referer"] == "https://example.com"
        assert captured["headers"]["X-OpenRouter-Title"] == "my-app"

    def test_missing_model_raises(self) -> None:
        import pytest

        critic = LLMCritic(provider="openrouter", api_key="sk-or")
        with pytest.raises(RuntimeError):
            critic._call_openai_compat("test prompt")

    def test_ollama_no_key_call_shape(self, monkeypatch) -> None:
        """Local Ollama serves without an API key — the call must not require one."""
        captured = self._fake_httpx(monkeypatch, "CONSISTENT")
        critic = LLMCritic(provider="ollama", model="llama3.1")
        result = critic._call_openai_compat("test prompt")
        assert result == "CONSISTENT"
        assert captured["url"] == "http://localhost:11434/v1/chat/completions"
        assert "Authorization" not in captured["headers"]  # no key needed
        assert captured["json"]["model"] == "llama3.1"

    def test_ollama_full_evaluate_path(self, monkeypatch) -> None:
        """End-to-end: Ollama (no key) reaches the LLM call and parses the verdict."""
        captured = self._fake_httpx(monkeypatch, "CONTRADICTION")
        critic = LLMCritic(provider="ollama", model="llama3.1")
        result = critic.evaluate("F = a/m", "f = a/m", ["f = ma"], "physics")
        assert result == ContentVerdict.CONTRADICTION
        assert "Authorization" not in captured["headers"]
