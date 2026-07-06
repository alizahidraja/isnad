"""Tests for matn.py — content criticism (fully decoupled from chain grading).

Verifies paper §4.4 commitment:
- Content criticism is independent of chain grading.
- DeterministicRuleCritic works for test/offline use.
"""

from isnad.matn import DeterministicRuleCritic
from isnad.types import ContentVerdict


class TestDeterministicRuleCritic:
    def test_empty_corpus_returns_unverifiable(self) -> None:
        critic = DeterministicRuleCritic()
        result = critic.evaluate(
            "p = mv",
            "p = mv",
            [],
        )
        assert result == ContentVerdict.UNVERIFIABLE

    def test_exact_match_is_consistent(self) -> None:
        critic = DeterministicRuleCritic()
        result = critic.evaluate(
            "momentum is p = mv",
            "momentum is p = mv",
            ["momentum is p = mv", "energy is e = mc^2"],
        )
        assert result == ContentVerdict.CONSISTENT

    def test_contradiction_pattern_detected(self) -> None:
        critic = DeterministicRuleCritic()
        result = critic.evaluate(
            "the momentum of a photon is p = h/λ",
            "the momentum of a photon is p = h/lambda",
            ["momentum p = mv"],
        )
        assert result == ContentVerdict.CONTRADICTION

    def test_classical_vs_quantum_contradiction(self) -> None:
        critic = DeterministicRuleCritic()
        result = critic.evaluate(
            "light behaves as a particle",
            "light behaves as a particle",
            ["light behaves as a wave"],
        )
        assert result == ContentVerdict.CONTRADICTION

    def test_unrelated_claims_are_unverifiable(self) -> None:
        critic = DeterministicRuleCritic()
        result = critic.evaluate(
            "the sky is blue",
            "the sky is blue",
            ["water boils at 100 degrees celsius"],
        )
        assert result == ContentVerdict.UNVERIFIABLE

    def test_critic_does_not_use_chain_information(self) -> None:
        """Content criticism is fully decoupled from chain grading."""
        critic = DeterministicRuleCritic()
        # The critic should work identically regardless of what chain
        # grade we might have — it only sees claim text and corpus.
        result = critic.evaluate(
            "p = mv",
            "p = mv",
            ["p = h/lambda"],
        )
        assert result == ContentVerdict.CONTRADICTION
        # No chain grade was involved — pure content check.
