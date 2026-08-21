"""LLM-backed content critic for ISNAD — provider-agnostic.

Higher-quality content criticism using an LLM with retrieved corpus context.
Supports OpenAI-compatible APIs (DeepSeek, OpenAI, local vLLM) and Anthropic.

Features:
- Provider-agnostic: pass base_url + api_key for any OpenAI-compatible endpoint
- Falls back to Anthropic if ANTHROPIC_API_KEY is set and no base_url provided
- Cached on disk (keyed by claim + context hash) — re-runs are free
- Graceful degradation: returns UNVERIFIABLE if no credentials
- Domain-agnostic prompt

Usage:
    # DeepSeek
    critic = LLMCritic(
        base_url="https://api.deepseek.com/v1",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        model="deepseek-chat",
    )
    # Anthropic
    critic = LLMCritic()  # reads ANTHROPIC_API_KEY from env
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from isnad.critics.embedding import EmbeddingCritic
from isnad.types import ContentVerdict


def _hash_claim(claim: str) -> str:
    return hashlib.sha256(claim.encode()).hexdigest()[:16]


class LLMCritic:
    """LLM-backed content critic with retrieval-augmented context.

    Provider-agnostic: supports any OpenAI-compatible endpoint (DeepSeek,
    OpenAI, local vLLM) via base_url + api_key. Falls back to Anthropic
    when ANTHROPIC_API_KEY is set and no base_url is provided.

    Args:
        base_url: OpenAI-compatible API base URL (e.g. https://api.deepseek.com/v1).
        api_key: API key for the provider.
        model: Model name to use (default: deepseek-chat).
        top_k: Number of similar corpus claims to retrieve as context.
        cache_dir: Directory for on-disk cache (None = no caching).
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        top_k: int = 5,
        cache_dir: str | None = None,
    ):
        self.base_url = base_url or ""
        self.api_key = api_key or ""
        self.model = model
        self.top_k = top_k
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._retriever = EmbeddingCritic()

    def _has_credentials(self) -> bool:
        return bool(self.base_url and self.api_key) or bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _call_llm(self, prompt: str) -> str:
        """Call LLM — OpenAI-compatible first, Anthropic fallback."""
        if self.base_url and self.api_key:
            import httpx

            resp = httpx.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
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

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            import anthropic

            client = anthropic.Anthropic(api_key=anthropic_key)
            model = self.model if self.model != "deepseek-chat" else "claude-sonnet-4-20250514"
            response = client.messages.create(
                model=model,
                max_tokens=32,
                messages=[{"role": "user", "content": prompt}],
            )
            return getattr(response.content[0], "text", "").strip().upper()

        raise RuntimeError("No LLM credentials available")

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
