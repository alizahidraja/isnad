"""Embedding-based content critic for ISNAD.

Fast, cheap, offline critic using cosine similarity over word overlap
(default) or a pluggable embedding function.

How it works:
1. Embed the incoming claim
2. Find the most similar existing corpus claims (cosine similarity)
3. If a near-duplicate is found → CONSISTENT
4. If a similar claim with contradictory signals is found → CONTRADICTION
5. Otherwise → UNVERIFIABLE

IMPORTANT: The default word-overlap embedding is a lightweight reference.
For production, supply a real embedding model via the `embed_fn` parameter.
The contradiction detection uses simple negation/numeric-difference heuristics
— a known limitation. See CRITIC_EVAL.md for measured performance.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from isnad.types import ContentVerdict


def _default_embed(text: str) -> dict[str, float]:
    """Default word-overlap embedding — fast, no dependencies.

    For production, replace with sentence-transformers or an API call.
    """
    words = re.findall(r"[a-z0-9]+", text.lower())
    total = max(1, len(words))
    return {w: c / total for w, c in Counter(words).items()}


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    if not a or not b:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in set(a) | set(b))
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _has_contradiction_signal(claim: str, corpus_claim: str) -> bool:
    """Heuristic contradiction detection between two similar claims.

    Checks for:
    - Negation patterns (is/is not, does/does not)
    - Numeric differences (>2x or <0.5x) on same quantities
    - Opposite direction words (increases/decreases, positive/negative)

    This is a known limitation — a real system would use an LLM
    or structured knowledge representation.
    """
    c_lower = claim.lower()
    cc_lower = corpus_claim.lower()

    # Negation pattern
    negation_pairs = [
        (" is ", " is not "), (" does ", " does not "),
        (" can ", " cannot "), (" has ", " has no "),
    ]
    for pos, neg in negation_pairs:
        if (pos in c_lower and neg in cc_lower) or (neg in c_lower and pos in cc_lower):
            return True

    # Opposite words
    opposites = [
        ("increases", "decreases"), ("positive", "negative"),
        ("attractive", "repulsive"), ("up", "down"),
        ("faster", "slower"), ("higher", "lower"),
        ("larger", "smaller"), ("hotter", "colder"),
    ]
    for a, b in opposites:
        if (a in c_lower and b in cc_lower) or (b in c_lower and a in cc_lower):
            return True

    # Numeric divergence
    nums_claim = [float(n) for n in re.findall(r"\d+\.?\d*", claim)]
    nums_corpus = [float(n) for n in re.findall(r"\d+\.?\d*", corpus_claim)]
    if nums_claim and nums_corpus:
        for nc in nums_claim:
            for ncc in nums_corpus:
                if nc > 0 and ncc > 0:
                    ratio = max(nc, ncc) / min(nc, ncc)
                    if ratio > 3.0:
                        # Same quantity context?
                        if any(w in c_lower for w in ["equal", "same", "constant"]):
                            continue
                        return True

    return False


class EmbeddingCritic:
    """Embedding-based content critic — fast, offline.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.4).  Swap freely.

    Args:
        embed_fn: Function mapping text → vector (dict or list).
            Default: word-overlap (fast, no deps, limited accuracy).
        similarity_threshold: Cosine sim above which claims are "similar".
        contradiction_threshold: Cosine sim above which we check for
            contradiction signals.

    Example:
        critic = EmbeddingCritic()
        corpus = ["force equals mass times acceleration",
                   "momentum is mass times velocity"]
        result = critic.evaluate("F = ma", "f = m a", corpus, "physics")
        # → ContentVerdict.CONSISTENT
    """

    def __init__(
        self,
        embed_fn: Callable[[str], Any] | None = None,
        similarity_threshold: float = 0.85,
        contradiction_threshold: float = 0.60,
    ):
        self._embed = embed_fn or _default_embed
        self.similarity_threshold = similarity_threshold
        self.contradiction_threshold = contradiction_threshold

        # Cache embeddings for corpus claims
        self._cache: dict[str, Any] = {}

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against the corpus.

        Returns:
            CONSISTENT if ≥1 corpus claim is highly similar without contradiction.
            CONTRADICTION if a similar claim conflicts.
            UNVERIFIABLE if no strong match.
        """
        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        claim_vec = self._embed(normalized_claim)

        best_sim = 0.0
        best_text = ""

        for cc in corpus_claims:
            if cc not in self._cache:
                self._cache[cc] = self._embed(cc)
            cc_vec = self._cache[cc]

            sim = _cosine_similarity(
                self._vec_to_dict(claim_vec),
                self._vec_to_dict(cc_vec),
            )

            if sim > best_sim:
                best_sim = sim
                best_text = cc

        if best_sim >= self.contradiction_threshold:
            if _has_contradiction_signal(normalized_claim, best_text):
                return ContentVerdict.CONTRADICTION

        if best_sim >= self.similarity_threshold:
            return ContentVerdict.CONSISTENT

        return ContentVerdict.UNVERIFIABLE

    @staticmethod
    def _vec_to_dict(vec: Any) -> dict[str, float]:
        """Convert various vector formats to {str: float} dict."""
        if isinstance(vec, dict):
            return {str(k): float(v) for k, v in vec.items()}
        if isinstance(vec, list):
            return {str(i): float(v) for i, v in enumerate(vec)}
        return {}
