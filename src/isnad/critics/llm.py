"""LLM-backed content critic for ISNAD — provider-agnostic.

Higher-quality content criticism using an LLM with retrieved corpus context.
Works with any OpenAI-compatible endpoint (OpenRouter, OpenAI, DeepSeek,
Gemini, Groq, Together, Ollama) and Anthropic via its SDK.

Pick a provider by name, or just set the right environment variable:

    critic = LLMCritic(provider="openrouter", model="openai/gpt-4o-mini")
    critic = LLMCritic(provider="openai", model="gpt-4o")
    critic = LLMCritic(provider="anthropic", model="claude-sonnet-4-20250514")
    critic = LLMCritic()  # auto-detects from the environment

Environment variables (all optional; explicit constructor args win):
- ISNAD_LLM_PROVIDER  — provider name (disambiguates when several keys are set)
- ISNAD_LLM_MODEL     — model name (required for providers with no default)
- ISNAD_LLM_API_KEY   — generic key for custom endpoints
- ISNAD_LLM_BASE_URL  — generic base URL for custom OpenAI-compatible endpoints
- Provider-specific keys: OPENROUTER_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY,
  ANTHROPIC_API_KEY, GEMINI_API_KEY / GOOGLE_API_KEY, GROQ_API_KEY,
  TOGETHER_API_KEY.

Features:
- Cached on disk (keyed by claim + context hash) — re-runs are free
- Graceful degradation: returns UNVERIFIABLE if not configured
- Domain-agnostic prompt

Honesty note: provider base URLs are recorded from public docs (verified
2026-08). The HTTP path is tested with a mock; live calls require the
provider's own key and are the user's responsibility to verify.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from isnad.critics.embedding import EmbeddingCritic
from isnad.types import ContentVerdict


def _hash_claim(claim: str) -> str:
    return hashlib.sha256(claim.encode()).hexdigest()[:16]


# =========================================================================
# Provider catalog
# =========================================================================


@dataclass(frozen=True)
class ProviderSpec:
    """A named LLM provider: base URL, credential env vars, default model.

    ``base_url=None`` marks a non-OpenAI-compatible backend (Anthropic's
    Messages API, called through its own SDK).
    """

    name: str
    base_url: str | None
    env_vars: tuple[str, ...]
    default_model: str | None
    requires_model: bool = False
    needs_key: bool = True
    doc: str = ""


# Base URLs are recorded from each provider's public documentation (verified
# 2026-08). ``openrouter``/``openai``/``gemini``/``groq``/``together``/
# ``ollama`` have no single default model, so they require an explicit model
# name (``requires_model=True``).
PROVIDERS: dict[str, ProviderSpec] = {
    "deepseek": ProviderSpec(
        "deepseek",
        "https://api.deepseek.com/v1",
        ("DEEPSEEK_API_KEY",),
        "deepseek-chat",
        doc="DeepSeek's OpenAI-compatible endpoint.",
    ),
    "openrouter": ProviderSpec(
        "openrouter",
        "https://openrouter.ai/api/v1",
        ("OPENROUTER_API_KEY",),
        None,
        requires_model=True,
        doc="OpenRouter — one key, many models (use a full slug, e.g. 'openai/gpt-4o').",
    ),
    "openai": ProviderSpec(
        "openai",
        "https://api.openai.com/v1",
        ("OPENAI_API_KEY",),
        None,
        requires_model=True,
        doc="OpenAI's native endpoint.",
    ),
    "anthropic": ProviderSpec(
        "anthropic",
        None,
        ("ANTHROPIC_API_KEY",),
        None,
        doc="Anthropic Messages API via the anthropic SDK (not OpenAI-compatible).",
    ),
    "gemini": ProviderSpec(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        None,
        requires_model=True,
        doc="Google Gemini via its OpenAI-compatibility layer.",
    ),
    "groq": ProviderSpec(
        "groq",
        "https://api.groq.com/openai/v1",
        ("GROQ_API_KEY",),
        None,
        requires_model=True,
        doc="Groq's OpenAI-compatible endpoint.",
    ),
    "together": ProviderSpec(
        "together",
        "https://api.together.xyz/v1",
        ("TOGETHER_API_KEY",),
        None,
        requires_model=True,
        doc="Together AI's OpenAI-compatible endpoint.",
    ),
    "ollama": ProviderSpec(
        "ollama",
        "http://localhost:11434/v1",
        (),
        None,
        requires_model=True,
        needs_key=False,
        doc="Local Ollama server (no API key).",
    ),
    "custom": ProviderSpec(
        "custom",
        None,
        (),
        None,
        requires_model=True,
        doc="Any OpenAI-compatible endpoint: pass base_url + api_key + model.",
    ),
}


def _first_env(*names: str) -> str:
    """First non-empty value among the given env var names."""
    for name in names:
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


# Detection order when no provider is named explicitly. deepseek/anthropic
# first for backward compatibility with the v2.4.3 defaults.
_DETECT_ORDER = ("deepseek", "anthropic", "openai", "openrouter", "gemini", "groq", "together")


def resolve_provider(provider: str | None, base_url: str | None) -> ProviderSpec | None:
    """Resolve the active provider from explicit args and the environment.

    Precedence:
    1. explicit ``provider`` name
    2. ``ISNAD_LLM_PROVIDER`` env var
    3. explicit ``base_url`` (any OpenAI-compatible endpoint)
    4. ``ISNAD_LLM_BASE_URL`` env var
    5. provider-specific API-key env vars (documented order)
    6. none -> not configured (graceful UNVERIFIABLE)
    """
    name = (provider or os.environ.get("ISNAD_LLM_PROVIDER", "") or "").strip().lower()
    if name:
        if name not in PROVIDERS:
            raise ValueError(
                f"Unknown LLM provider {name!r}. Known providers: {', '.join(PROVIDERS)}."
            )
        return PROVIDERS[name]
    if base_url or os.environ.get("ISNAD_LLM_BASE_URL", ""):
        return PROVIDERS["custom"]
    for candidate in _DETECT_ORDER:
        spec = PROVIDERS[candidate]
        if _first_env(*spec.env_vars):
            return spec
    return None


def list_providers() -> list[str]:
    """Names of the known providers, for help text and discovery."""
    return list(PROVIDERS)


class LLMCritic:
    """LLM-backed content critic with retrieval-augmented context.

    Provider-agnostic: name a provider (``openrouter``, ``openai``,
    ``deepseek``, ``anthropic``, ``gemini``, ``groq``, ``together``,
    ``ollama``) or pass a raw OpenAI-compatible ``base_url``. When no
    provider is named, the constructor auto-detects one from the
    environment (see module docstring).

    Args:
        provider: Named provider (see ``list_providers()``). Default: auto-detect.
        base_url: OpenAI-compatible API base URL (overrides the provider default).
        api_key: API key for the provider (overrides env vars).
        model: Model name to use (required for providers with no default).
        top_k: Number of similar corpus claims to retrieve as context.
        cache_dir: Directory for on-disk cache (None = no caching).
    """

    def __init__(
        self,
        provider: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        top_k: int = 5,
        cache_dir: str | None = None,
    ):
        self._spec = resolve_provider(provider, base_url)
        self.provider = self._spec.name if self._spec else None

        # Credentials: explicit args > provider env var(s) > generic env var.
        key = api_key or ""
        if not key and self._spec:
            key = _first_env(*self._spec.env_vars)
        if not key:
            key = os.environ.get("ISNAD_LLM_API_KEY", "")
        self.api_key = key

        # Base URL: explicit arg > provider default > generic env var.
        url = base_url or ""
        if not url and self._spec:
            url = self._spec.base_url or ""
        if not url:
            url = os.environ.get("ISNAD_LLM_BASE_URL", "")
        self.base_url = url

        # Model: explicit arg > generic env var > provider default.
        model_name = model or os.environ.get("ISNAD_LLM_MODEL", "") or ""
        if not model_name and self._spec:
            model_name = self._spec.default_model or ""
        self.model = model_name

        self.top_k = top_k
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._retriever = EmbeddingCritic()

    def _has_credentials(self) -> bool:
        """True if a real LLM call is possible (not just "a key exists").

        A provider that requires an explicit model name (OpenRouter, OpenAI,
        Gemini, ...) with no model set is treated as "not configured" rather
        than silently sending an empty model — the framework's no-data →
        no-penalty pattern.
        """
        if self._spec is None:
            return False
        if self._spec.requires_model and not self.model:
            return False
        if not self._spec.needs_key:
            return bool(self.base_url)
        if self.provider == "anthropic":
            return bool(self.api_key)
        return bool(self.base_url and self.api_key)

    def _call_llm(self, prompt: str) -> str:
        """Dispatch to the resolved provider backend."""
        if self.provider == "anthropic":
            return self._call_anthropic(prompt)
        return self._call_openai_compat(prompt)

    def _call_openai_compat(self, prompt: str) -> str:
        """Call any OpenAI-compatible ``chat/completions`` endpoint via httpx.

        The API key is optional — local providers (e.g. Ollama) serve without
        one. Key-requiring providers are gated upstream by ``_has_credentials``,
        so a missing key there never reaches this call.
        """
        if not self.base_url:
            raise RuntimeError("No LLM base URL available")
        if not self.model:
            raise RuntimeError(
                f"Provider {self.provider!r} requires an explicit model name "
                "(set model= or ISNAD_LLM_MODEL)."
            )

        import httpx

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # OpenRouter app attribution (optional; used for rankings only).
        if self.provider == "openrouter":
            referer = os.environ.get("ISNAD_LLM_REFERER", "")
            title = os.environ.get("ISNAD_LLM_TITLE", "")
            if referer:
                headers["HTTP-Referer"] = referer
            if title:
                headers["X-OpenRouter-Title"] = title

        resp = httpx.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 32,
                "temperature": 0.0,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("choices"):
            return (data["choices"][0]["message"].get("content") or "").strip().upper()
        return ""

    def _call_anthropic(self, prompt: str) -> str:
        """Call the Anthropic Messages API via the ``anthropic`` SDK."""
        if not self.api_key:
            raise RuntimeError("No LLM credentials available")
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        model = self.model or "claude-sonnet-4-20250514"
        response = client.messages.create(
            model=model,
            max_tokens=32,
            messages=[{"role": "user", "content": prompt}],
        )
        return getattr(response.content[0], "text", "").strip().upper()

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against the corpus using LLM + retrieval."""
        if not self._has_credentials():
            return ContentVerdict.UNVERIFIABLE
        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        # Retrieve top-k similar corpus claims via TF-IDF
        self._retriever.evaluate(normalized_claim, normalized_claim, corpus_claims)
        if self._retriever._index is None:
            return ContentVerdict.UNVERIFIABLE

        claim_vec = self._retriever._index.tfidf_vector(normalized_claim)
        scored = []
        for i, cc in enumerate(corpus_claims):
            cv = self._retriever._vectors[i] if i < len(self._retriever._vectors) else {}
            sim = self._retriever._index.cosine_similarity(claim_vec, cv)
            scored.append((sim, cc))
        scored.sort(key=lambda x: -x[0])
        context = [cc for _, cc in scored[: self.top_k]]

        # Cache check
        cache_key = _hash_claim(normalized_claim + "||" + "||".join(context))
        if self.cache_dir:
            cache_file = self.cache_dir / f"{cache_key}.json"
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text())
                    return ContentVerdict(data["verdict"])
                except (json.JSONDecodeError, KeyError, ValueError):
                    pass

        # Domain-agnostic prompt
        domain_hint = f" in the {domain} domain" if domain else ""
        context_text = "\n".join(f"- {c}" for c in context)
        prompt = (
            f"You are a content critic{domain_hint}. "
            f"Judge whether this claim is CONSISTENT with, CONTRADICTS, "
            f"or is UNVERIFIABLE against the corpus context.\n\n"
            f"Claim: {normalized_claim}\n\n"
            f"Corpus context:\n{context_text}\n\n"
            f"Rules:\n"
            f"- CONSISTENT: the claim states the same fact as a corpus claim\n"
            f"- CONTRADICTION: the claim asserts something opposite or incompatible\n"
            f"- UNVERIFIABLE: the corpus has no relevant information\n\n"
            f"Answer with exactly one word: CONSISTENT, CONTRADICTION, or UNVERIFIABLE."
        )

        try:
            text = self._call_llm(prompt)
        except Exception:
            return ContentVerdict.UNVERIFIABLE

        verdict_str = "UNVERIFIABLE"
        if "CONTRADICTION" in text:
            verdict_str = "CONTRADICTION"
        elif "CONSISTENT" in text:
            verdict_str = "CONSISTENT"

        verdict = ContentVerdict(verdict_str.lower())

        if self.cache_dir:
            cache_file = self.cache_dir / f"{cache_key}.json"
            cache_file.write_text(json.dumps({"verdict": verdict.value}))

        return verdict
