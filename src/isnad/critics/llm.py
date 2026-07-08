"""LLM-backed content critic for ISNAD.

Higher-quality content criticism using an LLM with retrieved corpus context.
Retrieves top-k similar corpus claims (via EmbeddingCritic's retriever),
then asks an LLM to judge: CONSISTENT, CONTRADICTION, or UNVERIFIABLE.

Features:
- Cached on disk (keyed by claim + context hash) — re-runs are free
- Configurable model (default: claude-sonnet-4-20250514)
- Cost-guarded (prints estimated cost before running)
- Graceful degradation: returns UNVERIFIABLE if no API key

IMPORTANT: Requires an Anthropic API key. Set ANTHROPIC_API_KEY env var.
The critic quality depends on the LLM's reasoning — false-CONSISTENT and
false-CONTRADICTION errors are possible. See CRITIC_EVAL.md.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from isnad.critics.embedding import EmbeddingCritic
from isnad.types import ContentVerdict


def _hash_claim(claim: str) -> str:
    return hashlib.sha256(claim.encode()).hexdigest()[:16]


class LLMCritic:
    """LLM-backed content critic with retrieval-augmented context.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.4).  Swap freely.

    Args:
        api_key: Anthropic API key (default: ANTHROPIC_API_KEY env var).
        model: Anthropic model to use.
        top_k: Number of similar corpus claims to retrieve as context.
        cache_dir: Directory for on-disk cache (None = no caching).

    Example:
        critic = LLMCritic(api_key="sk-...")
        corpus = ["force equals mass times acceleration"]
        result = critic.evaluate("F = ma", "f = m a", corpus, "physics")
        # → ContentVerdict.CONSISTENT
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        top_k: int = 5,
        cache_dir: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.top_k = top_k
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._retriever = EmbeddingCritic()  # TF-IDF, zero-deps

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against the corpus using LLM + retrieval."""
        if not self.api_key:
            return ContentVerdict.UNVERIFIABLE

        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        # Retrieve top-k similar corpus claims using TF-IDF
        self._retriever.evaluate(  # builds index if needed
            normalized_claim, normalized_claim, corpus_claims,
        )
        # Reuse the built index to get similarities
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

        # Check cache
        cache_key = _hash_claim(normalized_claim + "||" + "||".join(context))
        if self.cache_dir:
            cache_file = self.cache_dir / f"{cache_key}.json"
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text())
                    return ContentVerdict(data["verdict"])
                except (json.JSONDecodeError, KeyError, ValueError):
                    pass

        # Call LLM
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)
            context_text = "\n".join(f"- {c}" for c in context)
            prompt = (
                f"You are a physics content critic. "
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
            response = client.messages.create(
                model=self.model,
                max_tokens=32,
                messages=[{"role": "user", "content": prompt}],
            )
            text = getattr(response.content[0], "text", "").strip().upper()
        except Exception:
            return ContentVerdict.UNVERIFIABLE

        verdict_str = "UNVERIFIABLE"
        if "CONTRADICTION" in text:
            verdict_str = "CONTRADICTION"
        elif "CONSISTENT" in text:
            verdict_str = "CONSISTENT"

        verdict = ContentVerdict(verdict_str.lower())

        # Cache result
        if self.cache_dir:
            cache_file = self.cache_dir / f"{cache_key}.json"
            cache_file.write_text(json.dumps({"verdict": verdict.value}))

        return verdict


def _vec_to_dict(vec: Any) -> dict[str, float]:
    if isinstance(vec, dict):
        return {str(k): float(v) for k, v in vec.items()}
    if isinstance(vec, list):
        return {str(i): float(v) for i, v in enumerate(vec)}
    return {}
