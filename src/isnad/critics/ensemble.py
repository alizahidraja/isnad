"""Ensemble critic: combine a semantic critic with a deterministic one.

Motivation: a semantic critic (NLI) understands language but cannot do
arithmetic; a recompute critic does arithmetic but understands no language. Each
is blind where the other sees. Composed with the right priority they cover the
numeric-aggregate case *without* weakening the semantic critic's contradiction
detection.

Composition rule (contradiction-priority, upgrade-only):

    1. If ANY member returns CONTRADICTION → CONTRADICTION.
       (A live contradiction is never papered over. That is the framework's core
       principle, and it is what stops a correct *number* inside a false *claim*
       from being served: the semantic critic still catches the false assertion.)
    2. Else if the deterministic critic returns CONSISTENT → CONSISTENT.
       (Only reachable when NO member contradicted. A confirmed aggregate with no
       semantic contradiction is a genuine upgrade of what NLI alone would leave
       UNVERIFIABLE.)
    3. Else → the semantic critic's own verdict (CONSISTENT or UNVERIFIABLE).

The deterministic critic can only ever UPGRADE unverifiable→consistent, never
override a contradiction. This is the safety property: no member can flip a
contradiction into a serve.
"""

from __future__ import annotations

from isnad.critics.base import ContentCritic
from isnad.types import ContentVerdict


class EnsembleCritic:
    """Contradiction-priority ensemble of a semantic and a deterministic critic.

    Args:
        semantic: the language-understanding critic (e.g. HybridCritic / NLI).
        deterministic: the arithmetic critic (e.g. RecomputeCritic). Its
            CONSISTENT is trusted only when the semantic critic did not
            contradict; its CONTRADICTION is always honored.
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

        # 2. Deterministic confirmation, no contradiction anywhere -> upgrade.
        if det is ContentVerdict.CONSISTENT:
            return ContentVerdict.CONSISTENT

        # 3. Fall back to the semantic verdict (CONSISTENT or UNVERIFIABLE).
        return sem
