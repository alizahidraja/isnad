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

from isnad.critics.affirmation_gate import gated
from isnad.types import ContentVerdict

_SENTENCE_TRANSFORMERS_AVAILABLE = False
_CrossEncoder: Any = None


def _ensure_sentence_transformers() -> bool:
    """Lazily import sentence_transformers; True when available.

    Deferred so importing this module (and therefore ``isnad.api``) stays cheap:
    sentence_transformers pulls in torch (~2GB), which otherwise dominates test
    collection and import time even when the NLI critic is never used.
    """
    global _SENTENCE_TRANSFORMERS_AVAILABLE, _CrossEncoder
    if _CrossEncoder is None:
        try:
            from sentence_transformers import CrossEncoder

            _CrossEncoder = CrossEncoder
            _SENTENCE_TRANSFORMERS_AVAILABLE = True
        except ImportError:
            _SENTENCE_TRANSFORMERS_AVAILABLE = False
    return _SENTENCE_TRANSFORMERS_AVAILABLE


class LocalNLICritic:
    """Local NLI-based content critic — semantic entailment/contradiction.

    Uses a cross-encoder fine-tuned for NLI. For each *retrieved* corpus claim it
    computes entailment / contradiction / neutral probabilities, then decides:

    - CONTRADICTION if a same-subject corpus claim clearly contradicts the claim.
    - CONSISTENT if a same-subject corpus claim clearly entails it.
    - UNVERIFIABLE otherwise.

    Issue #110 — this critic previously had three defects, all fixed here:

    1. **Label order** — the cross-encoder outputs `[contradiction, entailment,
       neutral]`, but the code read `[contradiction, neutral, entailment]`, so
       "neutral" was treated as "entailment".
    2. **Raw logits vs probability thresholds** — the thresholds were compared
       against raw logits (unbounded), not softmax probabilities.
    3. **Max over the whole corpus** — a claim was flagged against *every* corpus
       fact, so a "different fact" was spuriously read as a contradiction. The
       critic now retrieves the top-k *similar* claims first (TF-IDF), and only
       judges against those.

    Args:
        model_name: HuggingFace cross-encoder model for NLI.
        entailment_threshold: entailment probability above which CONSISTENT.
        contradiction_threshold: contradiction probability above which CONTRADICTION.
        entailment_margin: entailment must exceed contradiction by this much.
        contradiction_margin: contradiction must exceed entailment by this much.
        retrieve_top_k: how many similar corpus claims to retrieve before NLI.

    Example:
        critic = LocalNLICritic()
        result = critic.evaluate(
            "F = ma", "f = m a",
            ["force equals mass times acceleration"], "physics"
        )
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/nli-deberta-v3-small",
        entailment_threshold: float = 0.7,
        contradiction_threshold: float = 0.5,
        entailment_margin: float = 0.2,
        contradiction_margin: float = 0.2,
        retrieve_top_k: int = 10,
        gate_affirmation: bool = True,
    ):
        self.model_name = model_name
        self.entailment_threshold = entailment_threshold
        self.contradiction_threshold = contradiction_threshold
        self.entailment_margin = entailment_margin
        self.contradiction_margin = contradiction_margin
        self.retrieve_top_k = retrieve_top_k
        self.gate_affirmation = gate_affirmation
        self._model: Any = None
        self._tfidf_cache: dict[tuple[str, ...], tuple[Any, list[dict[str, float]]]] = {}

    def _load_model(self) -> Any:
        """Lazy-load the cross-encoder model."""
        if self._model is not None:
            return self._model

        if not _ensure_sentence_transformers():
            return None

        try:
            self._model = _CrossEncoder(
                self.model_name,
                device="cpu",  # safe default; can override
            )
        except Exception:
            return None

        return self._model

    def _retrieve_topk(self, claim: str, corpus: list[str]) -> list[str]:
        """Return the most TF-IDF-similar corpus claims (same-subject retrieval)."""
        from isnad.critics.embedding import TFIDFIndex

        key = tuple(corpus)
        if key not in self._tfidf_cache:
            idx = TFIDFIndex(corpus)
            vecs = [idx.tfidf_vector(c) for c in corpus]
            self._tfidf_cache[key] = (idx, vecs)
        idx, vecs = self._tfidf_cache[key]

        claim_vec = idx.tfidf_vector(claim)
        ranked = sorted(
            ((idx.cosine_similarity(claim_vec, vecs[i]), i) for i in range(len(corpus))),
            reverse=True,
        )
        return [corpus[i] for _, i in ranked[: self.retrieve_top_k]]

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against the corpus using NLI.

        Returns CONSISTENT / CONTRADICTION / UNVERIFIABLE (see class docstring).
        """
        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        model = self._load_model()
        if model is None:
            return ContentVerdict.UNVERIFIABLE

        # Retrieve same-subject claims first — a claim is only judged against
        # facts it is actually about, so a "different fact" isn't read as a
        # contradiction (issue #110, defect 3).
        sample = corpus_claims
        if self.retrieve_top_k and len(corpus_claims) > self.retrieve_top_k:
            sample = self._retrieve_topk(normalized_claim, corpus_claims)

        pairs = [(cc, normalized_claim) for cc in sample]
        try:
            scores = model.predict(pairs, apply_softmax=True)
        except Exception:
            return ContentVerdict.UNVERIFIABLE

        # scores[i] = [contradiction, entailment, neutral] probabilities
        # (softmax-normalized — see the model's config: label 0=contradiction,
        # 1=entailment, 2=neutral).
        best_contradiction = 0.0
        best_entailment = 0.0
        for score in scores:
            if len(score) >= 3:
                best_contradiction = max(best_contradiction, float(score[0]))
                best_entailment = max(best_entailment, float(score[1]))
            elif len(score) == 1:
                best_entailment = max(best_entailment, float(score[0]))

        # Contradiction takes precedence (the framework's principle: a live
        # contradiction is never papered over by a similarity match), but only
        # when it *clearly* dominates entailment — the cross-encoder spuriously
        # gives same-topic text a high entailment, and without the margin a
        # contradiction would be mislabeled CONSISTENT (issue #110).
        if (
            best_contradiction >= self.contradiction_threshold
            and best_contradiction - best_entailment >= self.contradiction_margin
        ):
            return ContentVerdict.CONTRADICTION

        if (
            best_entailment >= self.entailment_threshold
            and best_entailment - best_contradiction >= self.entailment_margin
        ):
            if self.gate_affirmation:
                return gated("nli", domain, ContentVerdict.CONSISTENT, model=self.model_name)
            return ContentVerdict.CONSISTENT

        return ContentVerdict.UNVERIFIABLE


# ── Fast embedding-based retriever (pre-filter for NLI) ────────


class HybridCritic:
    """Two-stage critic: fast embedding retrieval → NLI judgment.

    Uses a fast embedding model to retrieve top-k relevant corpus claims,
    then applies the LocalNLICritic for precise entailment/contradiction.

    Requires: pip install sentence-transformers
    """

    def __init__(
        self,
        embed_model: str = "all-MiniLM-L6-v2",
        nli_model: str = "cross-encoder/nli-deberta-v3-small",
        top_k: int = 10,
        entailment_threshold: float = 0.7,
        contradiction_threshold: float = 0.5,
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
        if not _ensure_sentence_transformers():
            return None
        try:
            from sentence_transformers import SentenceTransformer

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
            from sentence_transformers import util

            scores = util.cos_sim(claim_vec, corpus_vecs)[0]
            top_indices = scores.argsort(descending=True)[: self.top_k]
            top_corpus = [corpus_claims[int(i)] for i in top_indices]
        except Exception:
            return ContentVerdict.UNVERIFIABLE

        # Stage 2: NLI judgment on top-k (delegates to the fixed LocalNLI).
        if self._nli_critic is None:
            self._nli_critic = LocalNLICritic(
                model_name=self.nli_model_name,
                entailment_threshold=self.entailment_threshold,
                contradiction_threshold=self.contradiction_threshold,
                # already retrieved top-k; don't re-retrieve inside LocalNLI
                retrieve_top_k=0,
                gate_affirmation=False,  # the Hybrid gates itself as "hybrid"
            )

        result = self._nli_critic.evaluate(
            claim_text,
            normalized_claim,
            top_corpus,
            domain,
        )
        return gated(
            "hybrid",
            domain,
            result,
            model=f"{self.embed_model_name}/{self.nli_model_name}",
        )
