"""Content critics for ISNAD — real matn criticism.

Bundled critics, in order of semantic strength:
- EmbeddingCritic: fast, cheap, offline — TF-IDF cosine similarity
- LocalNLICritic: semantic entailment via DeBERTa cross-encoder
- HybridCritic: two-stage (MiniLM retrieval -> NLI judgment)
- LLMCritic: LLM-backed with retrieval-augmented context

All implement ContentCritic protocol from .base. ``best_available_critic()``
picks the strongest one the current environment can actually run.
"""

from typing import Any

from isnad.critics.base import ContentCritic
from isnad.critics.embedding import EmbeddingCritic, TFIDFIndex
from isnad.critics.llm import LLMCritic
from isnad.critics.nli import HybridCritic, LocalNLICritic


def _sentence_transformers_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def best_available_critic(*, prefer_llm: bool = False, **kwargs: Any) -> ContentCritic:
    """Return the strongest content critic this environment can actually run.

    Preference order (highest semantic recall first):

    1. ``LLMCritic`` — the strongest tier, but needs an API key; selected only
       when ``prefer_llm=True`` and credentials are present.
    2. ``HybridCritic`` — semantic NLI offline, needs ``sentence-transformers``
       (~500 MB of models, downloaded on first use).
    3. ``EmbeddingCritic`` — TF-IDF, catches obvious contradictions, always works.

    Honest by construction: it never returns a critic it cannot run, and it
    degrades gracefully down the list. See ``docs/critics.md`` for the measured
    recall of each tier.
    """
    if prefer_llm:
        candidate = LLMCritic()
        if candidate._has_credentials():
            return candidate
    if _sentence_transformers_available():
        return HybridCritic(**kwargs)
    return EmbeddingCritic()


__all__ = [
    "ContentCritic",
    "EmbeddingCritic",
    "HybridCritic",
    "LLMCritic",
    "LocalNLICritic",
    "TFIDFIndex",
    "best_available_critic",
]
