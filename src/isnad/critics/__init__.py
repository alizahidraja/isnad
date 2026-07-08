"""Content critics for ISNAD — real matn criticism.

Bundled critics:
- EmbeddingCritic: fast, cheap, offline — TF-IDF cosine similarity
- LocalNLICritic: semantic entailment via DeBERTa cross-encoder
- HybridCritic: two-stage (MiniLM retrieval -> NLI judgment)
- LLMCritic: LLM-backed with retrieval-augmented context

All implement ContentCritic protocol from .base
"""

from isnad.critics.base import ContentCritic
from isnad.critics.embedding import EmbeddingCritic, TFIDFIndex
from isnad.critics.llm import LLMCritic
from isnad.critics.nli import HybridCritic, LocalNLICritic

__all__ = [
    "ContentCritic",
    "EmbeddingCritic",
    "HybridCritic",
    "LLMCritic",
    "LocalNLICritic",
    "TFIDFIndex",
]
