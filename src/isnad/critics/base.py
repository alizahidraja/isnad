"""Content critic protocol — fully decoupled from chain grading.

Moved from isnad.types to keep the critics module self-contained.
"""

from __future__ import annotations

from typing import Protocol

from isnad.types import ContentVerdict


class ContentCritic(Protocol):
    """Protocol for matn (content) criticism — fully decoupled from chain grading.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.4).  Swap freely.

    Chain grading and content criticism are combined only at the end,
    by the decision matrix.  They never read each other's internals.
    """

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str,
    ) -> ContentVerdict: ...
