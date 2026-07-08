"""Local NLI-based content critic for ISNAD.

Uses a cross-encoder Natural Language Inference model to judge whether
a claim is entailed-by, contradicts, or is neutral to the corpus.

This replaces the weak word-overlap EmbeddingCritic with proper semantic
understanding.  Runs locally — no API key required.

Models (auto-downloaded on first use, ~500MB):
- Default: 'cross-encoder/nli-deberta-v3-small' (fast, good accuracy)
- Better: 'cross-encoder/nli-deberta-v3-base' (slower, higher accuracy)

Requires: pip install sentence-transformers

IMPORTANT: This is an OPTIONAL dependency.  If sentence-transformers is
not installed, the critic gracefully degrades to UNVERIFIABLE.
"""

from __future__ import annotations

from typing import Any

from isnad.types import ContentVerdict

_SENTENCE_TRANSFORMERS_AVAILABLE = False
try:
    from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]

    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    CrossEncoder = None  # type: ignore


class LocalNLICritic:
    """Local NLI-based content critic — semantic entailment/contradiction.

    Uses a cross-encoder model fine-tuned for NLI (Natural Language
    Inference).  For each corpus claim, computes:
    - ENTAILMENT score: the claim is supported by the corpus
    - CONTRADICTION score: the claim conflicts with the corpus
    - NEUTRAL score: no relationship

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.4).  Swap freely.

    Args:
        model_name: HuggingFace cross-encoder model for NLI.
            Default: 'cross-encoder/nli-deberta-v3-small' (fast, ~500MB)
        entailment_threshold: Score above which claim is CONSISTENT.
        contradiction_threshold: Score above which claim is CONTRADICTION.
        max_corpus_claims: Max corpus claims to check per evaluation.

    Example:
        critic = LocalNLICritic()
        result = critic.evaluate(
            "F = ma", "f = m a",
            ["force equals mass times acceleration"], "physics"
        )
        # → ContentVerdict.CONSISTENT (entailment)
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/nli-deberta-v3-small",
        entailment_threshold: float = 0.65,
        contradiction_threshold: float = 0.55,
        max_corpus_claims: int = 20,
    ):
        self.model_name = model_name
        self.entailment_threshold = entailment_threshold
        self.contradiction_threshold = contradiction_threshold
        self.max_corpus_claims = max_corpus_claims
        self._model: Any = None

    def _load_model(self) -> Any:
        """Lazy-load the cross-encoder model."""
        if self._model is not None:
            return self._model

        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            return None

        try:
            self._model = CrossEncoder(  # type: ignore[call-arg]
                self.model_name,
                device="cpu",  # safe default; can override
            )
        except Exception:
            return None

        return self._model

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against the corpus using NLI.

        Returns:
            CONSISTENT if ≥1 corpus claim strongly entails the claim.
            CONTRADICTION if ≥1 corpus claim contradicts it.
            UNVERIFIABLE if neither threshold is met or model unavailable.
        """
        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        model = self._load_model()
        if model is None:
            return ContentVerdict.UNVERIFIABLE

        # Truncate corpus for performance
        corpus_sample = corpus_claims[: self.max_corpus_claims]

        # Build NLI pairs: (corpus_premise, claim_hypothesis)
        pairs = [(cc, normalized_claim) for cc in corpus_sample]

        try:
            scores = model.predict(pairs)  # type: ignore[union-attr]
        except Exception:
            return ContentVerdict.UNVERIFIABLE

        # scores[i] = [contradiction_score, neutral_score, entailment_score]
        # (DeBERTa NLI models output in this order)

        max_entailment = 0.0
        max_contradiction = 0.0

        for score in scores:
            if len(score) >= 3:
                max_contradiction = max(max_contradiction, float(score[0]))
                max_entailment = max(max_entailment, float(score[2]))
            elif len(score) == 1:
                # Some models output a single score (entailment-like)
                max_entailment = max(max_entailment, float(score[0]))

        # Decision logic — entailment overrides contradiction if both high
        if max_entailment >= self.entailment_threshold:
            return ContentVerdict.CONSISTENT

        if max_contradiction >= self.contradiction_threshold:
            return ContentVerdict.CONTRADICTION

        return ContentVerdict.UNVERIFIABLE


# ── Fast embedding-based retriever (pre-filter for NLI) ────────


class HybridCritic:
    """Two-stage critic: fast embedding retrieval → NLI judgment.

    Uses a fast embedding model to retrieve top-k relevant corpus claims,
    then applies the LocalNLICritic for precise entailment/contradiction.

    Much faster than running NLI on the full corpus while maintaining
    the accuracy of semantic NLI.

    Requires: pip install sentence-transformers
    """

    def __init__(
        self,
        embed_model: str = "all-MiniLM-L6-v2",
        nli_model: str = "cross-encoder/nli-deberta-v3-small",
        top_k: int = 10,
        entailment_threshold: float = 0.65,
        contradiction_threshold: float = 0.55,
    ):
        self.embed_model_name = embed_model
        self.nli_model_name = nli_model
        self.top_k = top_k
        self.entailment_threshold = entailment_threshold
        self.contradiction_threshold = contradiction_threshold

        self._embed_model: Any = None
        self._nli_critic: LocalNLICritic | None = None

    def _load_embed_model(self) -> Any:
        if self._embed_model is not None:
            return self._embed_model
        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            return None
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

            self._embed_model = SentenceTransformer(self.embed_model_name)
        except Exception:
            return None
        return self._embed_model

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Two-stage evaluation: retrieve → NLI judge."""
        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        embed_model = self._load_embed_model()
        if embed_model is None:
            return ContentVerdict.UNVERIFIABLE

        # Stage 1: embed and retrieve top-k
        try:
            claim_vec = embed_model.encode(normalized_claim)
            corpus_vecs = embed_model.encode(corpus_claims)
            from sentence_transformers import util  # type: ignore[import-not-found]

            scores = util.cos_sim(claim_vec, corpus_vecs)[0]
            top_indices = scores.argsort(descending=True)[: self.top_k]
            top_corpus = [corpus_claims[int(i)] for i in top_indices]
        except Exception:
            return ContentVerdict.UNVERIFIABLE

        # Stage 2: NLI judgment on top-k
        if self._nli_critic is None:
            self._nli_critic = LocalNLICritic(
                model_name=self.nli_model_name,
                entailment_threshold=self.entailment_threshold,
                contradiction_threshold=self.contradiction_threshold,
            )

        return self._nli_critic.evaluate(
            claim_text, normalized_claim, top_corpus, domain,
        )
