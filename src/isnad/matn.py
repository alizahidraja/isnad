"""Matn Criticism — content evaluation fully decoupled from chain grading.

Implements paper §4.4: transmission quality and content quality are
evaluated independently.  Chain grading and matn criticism are two
separate modules that never read each other's internals.  They are
combined only at the end, by the decision matrix.

Ships two implementations:
1. DeterministicRuleCritic — a reference stub for tests and offline use.
2. LLMCritic — an optional Anthropic-backed critic (reference integration).

REFERENCE STUB NOTICE: The DeterministicRuleCritic uses hardcoded string
pattern matching against a hand-curated CONTRADICTION_PATTERNS list.
It cannot detect contradictions beyond those patterns.  The paper's
worked example passes because the specific patterns needed are included.
A production critic would use semantic similarity, domain-aware formula
canonicalization, or an LLM-backed critic.  This is explicitly a stub
for testing and offline demonstration.
"""

from __future__ import annotations

from isnad.types import ContentVerdict

# ===========================================================================
# Deterministic rule-based critic (reference stub, works without API keys)
# ===========================================================================


class DeterministicRuleCritic:
    """A deterministic, rule-based content critic.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.4).  Swap freely.

    REFERENCE STUB: This critic detects contradictions via exact string
    matching against a hand-curated list of known contradictory phrase pairs.
    It CANNOT detect semantically equivalent contradictions phrased
    differently.  The paper's worked example passes because the required
    patterns (p=mv vs p=h/λ) are included.  For production use, replace
    with an LLM-backed or embedding-based critic.

    Patterns can be extended via ``add_pattern()`` or by subclassing
    and overriding ``_CONTRADICTION_PATTERNS``.
    """

    # Known contradiction patterns — hand-curated reference set.
    # NOT exhaustive.  Extend via add_pattern() for your domain.
    _CONTRADICTION_PATTERNS: list[tuple[str, str]] = [
        ("p = mv", "p = h/λ"),
        ("p = mv", "p = h/lambda"),
        ("particle", "wave"),
        ("wave", "particle"),
        ("classical", "quantum"),
        ("newtonian", "relativistic"),
        ("p = mv", "momentum of a photon"),
        ("energy is conserved", "energy is not conserved"),
    ]

    @classmethod
    def add_pattern(cls, pattern_a: str, pattern_b: str) -> None:
        """Register a new contradiction pattern pair.

        Args:
            pattern_a: Lowercase substring that contradicts pattern_b.
            pattern_b: Lowercase substring that contradicts pattern_a.
        """
        cls._CONTRADICTION_PATTERNS.append((pattern_a.lower(), pattern_b.lower()))

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against the corpus.

        Args:
            claim_text: Original claim text.
            normalized_claim: Normalized claim text.
            corpus_claims: List of existing normalized claims in the corpus.
            domain: Domain tag for domain-specific checking (unused in stub).

        Returns:
            ContentVerdict: CONSISTENT, CONTRADICTION, or UNVERIFIABLE.
        """
        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        # Exact match → consistent
        if normalized_claim in corpus_claims:
            return ContentVerdict.CONSISTENT

        # Check contradiction patterns
        for corpus_claim in corpus_claims:
            for pattern_a, pattern_b in self._CONTRADICTION_PATTERNS:
                if self._matches_pattern(normalized_claim, corpus_claim, pattern_a, pattern_b):
                    return ContentVerdict.CONTRADICTION

        # No clear signal
        return ContentVerdict.UNVERIFIABLE

    @staticmethod
    def _matches_pattern(claim: str, corpus_claim: str, pattern_a: str, pattern_b: str) -> bool:
        """Check if one claim matches pattern_a and the other matches pattern_b."""
        pat_a_lower = pattern_a.lower()
        pat_b_lower = pattern_b.lower()
        return (pat_a_lower in claim and pat_b_lower in corpus_claim) or (
            pat_b_lower in claim and pat_a_lower in corpus_claim
        )


# ===========================================================================
# LLM-backed critic — MOVED to isnad.critics.llm
# ===========================================================================
# The LLMCritic has been consolidated into isnad.critics.llm.LLMCritic
# which includes retrieval-augmented context and disk caching.
# Import from there: from isnad.critics import LLMCritic
# This module retains only the DeterministicRuleCritic for testing/offline use.
