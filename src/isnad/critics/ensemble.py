"""Ensemble critic: combine a semantic critic with a deterministic one.

Motivation: a semantic critic (NLI) understands language but cannot do
arithmetic; a recompute critic does arithmetic but understands no language. Each
is blind where the other sees. The value of composing them is that the
deterministic critic catches arithmetic contradictions (an inflated total, a
97-vs-3 conflict) that an entailment critic cannot compute, without ever making
the result less safe than the semantic critic alone.

Composition rule (contradiction-priority, confirm-to-upgrade):

    1. If ANY member returns CONTRADICTION → CONTRADICTION.
       (A live contradiction is never papered over. That is the framework's core
       principle. It stops an inflated or conflicting number from being served,
       whichever critic sees it.)
    2. deterministic CONSISTENT AND semantic CONSISTENT → CONSISTENT.
       (Both agree. The semantic critic must actively confirm, not merely stay
       silent. A numeric match only closes the arithmetic slice; it does not
       affirm the non-numeric part of the claim.)
    3. deterministic CONSISTENT AND semantic UNVERIFIABLE → UNVERIFIABLE.
       (Defer, do NOT bless. The number checks out, but the semantic critic
       cannot confirm the rest of the claim, so a false non-numeric assertion
       wrapped around a correct number would slip through if we upgraded here.
       This is the safety fix for the "correct number inside a false claim" case.)
    4. Else → the semantic critic's own verdict.

The deterministic critic never overrides a contradiction, and it never upgrades
on a number alone. A CONSISTENT result requires both critics to agree. This is
the safety property: the ensemble is never less safe than the semantic critic.
"""

from __future__ import annotations

from isnad.critics.base import ContentCritic
from isnad.types import ContentVerdict


class EnsembleCritic:
    """Contradiction-priority ensemble of a semantic and a deterministic critic.

    Args:
        semantic: the language-understanding critic (e.g. HybridCritic / NLI).
        deterministic: the arithmetic critic (e.g. RecomputeCritic). Its
            CONSISTENT upgrades the verdict only when the semantic critic also
            confirms (CONSISTENT); its CONTRADICTION is always honored.
    """

    def __init__(self, semantic: ContentCritic, deterministic: ContentCritic):
        self.semantic = semantic
        self.deterministic = deterministic

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        sem = self.semantic.evaluate(claim_text, normalized_claim, corpus_claims, domain)
        det = self.deterministic.evaluate(claim_text, normalized_claim, corpus_claims, domain)

        # 1. Any contradiction wins, semantic OR deterministic.
        if sem is ContentVerdict.CONTRADICTION or det is ContentVerdict.CONTRADICTION:
            return ContentVerdict.CONTRADICTION

        # 2. Upgrade only when BOTH critics confirm. A numeric match closes the
        #    arithmetic slice but does not affirm the non-numeric part of the
        #    claim, so the semantic critic must actively say CONSISTENT, not just
        #    stay silent. If it is UNVERIFIABLE, we defer (fall through to rule 3)
        #    rather than serve a false non-numeric assertion wrapped around a
        #    correct number.
        if det is ContentVerdict.CONSISTENT and sem is ContentVerdict.CONSISTENT:
            return ContentVerdict.CONSISTENT

        # 3/4. Otherwise defer to the semantic verdict. This covers
        #      det=CONSISTENT + sem=UNVERIFIABLE (return UNVERIFIABLE: number
        #      checks out but the rest of the claim is unconfirmed) and the plain
        #      semantic-only cases.
        return sem
