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

import os

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
# LLM-backed critic (optional, reference integration)
# ===========================================================================


class LLMCritic:
    """LLM-backed content critic using Anthropic's API.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.4).  Swap freely.

    REFERENCE INTEGRATION STUB: Sends the claim + corpus context to an
    Anthropic model and parses the structured response.  A production
    version would add batching, caching, confidence scores, multi-model
    ensemble, and domain-specific prompting templates.
    """

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against the corpus using an LLM.

        Returns UNVERIFIABLE if no API key is set (graceful degradation).
        """
        if not self.api_key:
            return ContentVerdict.UNVERIFIABLE

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)

            corpus_text = "\n".join(
                f"- {c}"
                for c in corpus_claims[:20]  # limit context window
            )
            prompt = self._build_prompt(claim_text, corpus_text, domain)

            response = client.messages.create(
                model=self.model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )

            # response.content is a list of ContentBlock union types;
            # the first block is typically TextBlock with a .text attribute
            block = response.content[0]
            verdict_text = getattr(block, "text", "").strip().upper()
            return self._parse_verdict(verdict_text)

        except Exception:
            # Graceful degradation: any failure → UNVERIFIABLE
            return ContentVerdict.UNVERIFIABLE

    @staticmethod
    def _build_prompt(claim_text: str, corpus_text: str, domain: str) -> str:
        domain_line = f"Domain: {domain}\n" if domain else ""
        return (
            "You are a content critic for a knowledge base. "
            "Evaluate whether the following claim contradicts existing corpus claims.\n\n"
            f"{domain_line}"
            f"New claim: {claim_text}\n\n"
            f"Existing corpus claims:\n{corpus_text}\n\n"
            "Respond with exactly one word: "
            "CONSISTENT, CONTRADICTION, or UNVERIFIABLE."
        )

    @staticmethod
    def _parse_verdict(text: str) -> ContentVerdict:
        text = text.strip().upper()
        if "CONSISTENT" in text:
            return ContentVerdict.CONSISTENT
        if "CONTRADICTION" in text:
            return ContentVerdict.CONTRADICTION
        return ContentVerdict.UNVERIFIABLE
