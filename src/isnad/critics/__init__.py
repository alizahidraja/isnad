"""Content critics for ISNAD — real matn criticism.

The bundled deterministic critic is a non-functional stub on real text.
These implementations provide WORKING content criticism:

- EmbeddingCritic: fast, cheap, offline — uses cosine similarity
- LLMCritic: higher quality — uses an LLM with retrieved context

Both implement the existing ContentCritic protocol and are pluggable
via the framework's public interface.

IMPORTANT: These critics have measured limitations. See CRITIC_EVAL.md
for precision/recall and false-consistent rates before deploying.
"""

from isnad.critics.embedding import EmbeddingCritic
from isnad.critics.llm import LLMCritic

__all__ = ["EmbeddingCritic", "LLMCritic"]
