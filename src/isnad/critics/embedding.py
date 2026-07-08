"""Embedding-based content critic for ISNAD — TF-IDF weighted, zero-dependency.

The DEFAULT critic.  Works out of the box with no downloads, no API keys.
Uses TF-IDF (Term Frequency × Inverse Document Frequency) weighting for
much better similarity than raw word-overlap.

Upgrade path (optional):
    pip install isnad[nli]  →  enables HybridCritic (MiniLM embeddings)
    pip install sentence-transformers  →  enables LocalNLICritic (DeBERTa NLI)

For production: use LocalNLICritic or LLMCritic for highest accuracy.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from isnad.types import ContentVerdict


def _tokenize(text: str) -> list[str]:
    """Tokenize text into words, keeping numbers and units."""
    return re.findall(r"[a-z0-9]+(?:/[a-z0-9²³]+)?", text.lower())


class TFIDFIndex:
    """Lightweight TF-IDF index — zero dependencies, corpus-aware weighting.

    Builds an inverted index from the corpus and computes TF-IDF vectors
    for similarity scoring.  Much better than raw word-overlap because
    rare terms get higher weight and common words are discounted.
    """

    def __init__(self, corpus: list[str] | None = None):
        self._doc_freq: Counter[str] = Counter()
        self._doc_count = 0
        self._docs: list[list[str]] = []
        if corpus:
            self.fit(corpus)

    def fit(self, corpus: list[str]) -> None:
        """Build TF-IDF index from corpus documents."""
        self._doc_count = len(corpus)
        self._docs = []
        self._doc_freq = Counter()
        for doc in corpus:
            tokens = list(set(_tokenize(doc)))  # unique terms per doc for DF
            self._docs.append(_tokenize(doc))  # all terms for TF
            for t in tokens:
                self._doc_freq[t] += 1

    def tfidf_vector(self, text: str) -> dict[str, float]:
        """Compute TF-IDF vector for a text."""
        tokens = _tokenize(text)
        if not tokens:
            return {}
        tf = Counter(tokens)
        vec: dict[str, float] = {}
        for term, count in tf.items():
            df = self._doc_freq.get(term, 0)
            if df == 0:
                df = 1  # smooth unseen terms
            idf = math.log((self._doc_count + 1) / (df + 1)) + 1.0
            vec[term] = (count / len(tokens)) * idf
        return vec

    def cosine_similarity(self, a: dict[str, float], b: dict[str, float]) -> float:
        """Cosine similarity between two TF-IDF vectors."""
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

    Checks negation patterns, opposite words, and numeric divergence.
    """
    c_low = claim.lower()
    cc_low = corpus_claim.lower()

    # Negation
    for pos, neg in [
        (" is ", " is not "), (" does ", " does not "),
        (" can ", " cannot "), (" has ", " has no "),
    ]:
        if (pos in c_low and neg in cc_low) or (neg in c_low and pos in cc_low):
            return True

    # Opposite words
    for a, b in [
        ("increases", "decreases"), ("positive", "negative"),
        ("attractive", "repulsive"), ("faster", "slower"),
        ("higher", "lower"), ("larger", "smaller"),
        ("up", "down"), ("hotter", "colder"),
        ("clockwise", "counterclockwise"), ("left", "right"),
    ]:
        if (a in c_low and b in cc_low) or (b in c_low and a in cc_low):
            return True

    # Numeric divergence >3x
    nums_c = [float(n) for n in re.findall(r"\d+\.?\d*", claim)]
    nums_cc = [float(n) for n in re.findall(r"\d+\.?\d*", corpus_claim)]
    for nc in nums_c:
        for ncc in nums_cc:
            if nc > 0 and ncc > 0 and max(nc, ncc) / min(nc, ncc) > 3.0:
                if not any(w in c_low for w in ["equal", "same", "constant"]):
                    return True
    return False


class EmbeddingCritic:
    """Default content critic — TF-IDF weighted, zero dependencies.

    Works immediately with no installs, no downloads, no API keys.
    For better accuracy: pip install isnad[nli] and use HybridCritic.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.4).  Swap freely.

    Args:
        similarity_threshold: Cosine sim above which claims are "consistent".
        contradiction_threshold: Cosine sim above which we check contradictions.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.75,
        contradiction_threshold: float = 0.50,
    ):
        self.similarity_threshold = similarity_threshold
        self.contradiction_threshold = contradiction_threshold
        self._index: TFIDFIndex | None = None
        self._corpus_texts: list[str] = []
        self._vectors: list[dict[str, float]] = []

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against the corpus using TF-IDF similarity."""
        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        # Build index on first call or when corpus changes
        if self._index is None or corpus_claims != self._corpus_texts:
            self._index = TFIDFIndex(corpus_claims)
            self._corpus_texts = list(corpus_claims)
            self._vectors = [self._index.tfidf_vector(c) for c in corpus_claims]

        claim_vec = self._index.tfidf_vector(normalized_claim)

        best_sim = 0.0
        best_idx = 0
        for i, cv in enumerate(self._vectors):
            sim = self._index.cosine_similarity(claim_vec, cv)
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        # Check contradiction first (lower threshold, more specific)
        if best_sim >= self.contradiction_threshold:
            best_text = self._corpus_texts[best_idx]
            if _has_contradiction_signal(normalized_claim, best_text):
                return ContentVerdict.CONTRADICTION

        if best_sim >= self.similarity_threshold:
            return ContentVerdict.CONSISTENT

        return ContentVerdict.UNVERIFIABLE
