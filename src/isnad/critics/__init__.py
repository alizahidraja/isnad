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
from isnad.critics.ensemble import EnsembleCritic
from isnad.critics.llm import LLMCritic
from isnad.critics.nli import HybridCritic, LocalNLICritic
from isnad.critics.recompute import RecomputeCritic
from isnad.critics.routing import AggregateRouter


def _sentence_transformers_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def best_available_critic(*, prefer_llm: bool = True, **kwargs: Any) -> ContentCritic:
    """Return the strongest content critic this environment can actually run.

    Preference order (highest semantic recall first):

    1. ``LLMCritic`` — the strongest tier (measured 100% recall / 0% false-
       consistent). Auto-detected from any configured provider key
       (``DEEPSEEK_API_KEY`` etc.) or a local server via
       ``ISNAD_LLM_PROVIDER=ollama`` + ``ISNAD_LLM_MODEL``. Selected by default
       when credentials are present (``prefer_llm=True``); pass
       ``prefer_llm=False`` to force an offline critic.
    2. ``HybridCritic`` — semantic NLI offline, needs ``sentence-transformers``
       (~500 MB of models, downloaded on first use).
    3. ``EmbeddingCritic`` — TF-IDF, contradiction-only (never CONSISTENT),
       always works.

    Every tier is composed with a deterministic ``RecomputeCritic`` inside an
    ``EnsembleCritic``: a numeric-aggregate contradiction (an inflated total, a
    wrong count) is caught even when the semantic critic cannot compute it. The
    ensemble never upgrades on a number alone, so it is never less safe than
    the semantic critic.

    Honest by construction: it never returns a critic it cannot run, and it
    degrades gracefully down the list. See ``docs/critics.md`` for the measured
    recall of each tier.
    """
    if prefer_llm:
        candidate = LLMCritic()
        if candidate._has_credentials():
            return EnsembleCritic(candidate, RecomputeCritic())
    if _sentence_transformers_available():
        return EnsembleCritic(HybridCritic(**kwargs), RecomputeCritic())
    return EnsembleCritic(EmbeddingCritic(), RecomputeCritic())


__all__ = [
    "AggregateRouter",
    "ContentCritic",
    "EmbeddingCritic",
    "EnsembleCritic",
    "HybridCritic",
    "LLMCritic",
    "LocalNLICritic",
    "RecomputeCritic",
    "TFIDFIndex",
    "best_available_critic",
]
