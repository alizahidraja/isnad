"""Tests for the RecomputeCritic and EnsembleCritic.

These cover the arithmetic critic in isolation and the confirm-to-upgrade
composition. Most composition tests use a stub semantic critic so they run
offline (no NLI model download). One test uses a real EmbeddingCritic to pin the
exact safety property with a real semantic critic: a correct number inside a
false claim must NOT be served, even when the semantic critic returns
UNVERIFIABLE rather than CONTRADICTION.
"""

from isnad.critics.base import ContentCritic
from isnad.critics.embedding import EmbeddingCritic
from isnad.critics.ensemble import EnsembleCritic
from isnad.critics.recompute import RecomputeCritic
from isnad.types import ContentVerdict

CONSISTENT = ContentVerdict.CONSISTENT
CONTRADICTION = ContentVerdict.CONTRADICTION
UNVERIFIABLE = ContentVerdict.UNVERIFIABLE


# Generic structured rows: a GROUP-BY-style result (key: count) plus a blank tally.
ROWS = [
    "category alpha: 26 items",
    "category beta: 14 items",
    "category gamma: 12 items",
    "rows with no category label: 470",
    "total rows: 522",
]
# 26 + 14 + 12 + 470 = 522, matching the explicit total.


class TestRecomputeCriticAlone:
    def test_correct_total_and_blank_is_consistent(self):
        critic = RecomputeCritic()
        claim = "There are 522 rows; 470 have no category label."
        assert critic.evaluate(claim, claim, ROWS) == CONSISTENT

    def test_inflated_total_is_contradiction(self):
        """Claim asserts an aggregate larger than the rows carry -> conflict."""
        critic = RecomputeCritic()
        claim = "There are 900 rows in total."
        assert critic.evaluate(claim, claim, ROWS) == CONTRADICTION

    def test_the_97_vs_3_shape_is_contradiction(self):
        """The real-log failure class: a claimed total far above the rows."""
        rows = ["item a: 2", "item b: 1", "total: 3"]
        critic = RecomputeCritic()
        claim = "There are 97 items in the working set."
        assert critic.evaluate(claim, claim, rows) == CONTRADICTION

    def test_no_numeric_assertion_defers(self):
        critic = RecomputeCritic()
        claim = "The categories are ranked in descending order."
        assert critic.evaluate(claim, claim, ROWS) == UNVERIFIABLE

    def test_unstructured_corpus_defers(self):
        critic = RecomputeCritic()
        claim = "There are 522 rows."
        assert critic.evaluate(claim, claim, ["some prose with no counts"]) == UNVERIFIABLE

    def test_bound_language_on_matching_number_defers(self):
        """A3 shape: 'over 522 ... dominating'. The number matches the total, but
        the bound/superlative wrapper means it is not an equality assertion.
        recompute must DEFER (not bless), on the CONSISTENT path only."""
        critic = RecomputeCritic()
        claim = "Category alpha dominates with over 522 occurrences overwhelming the set."
        assert critic.evaluate(claim, claim, ROWS) == UNVERIFIABLE

    def test_bound_guard_does_not_suppress_a_real_contradiction(self):
        """The guard is on the CONSISTENT path only. An inflated aggregate with a
        bound word ('over 900') must STILL be CONTRADICTION, not deferred.
        Promoting a contradiction to unverifiable would serve it on a SAHIH chain."""
        critic = RecomputeCritic()
        claim = "There are over 900 rows dominating the dataset."
        assert critic.evaluate(claim, claim, ROWS) == CONTRADICTION

    def test_correct_total_but_extra_unaccounted_number_defers(self):
        """Correct total + a number the rows don't support -> stay silent, do NOT
        bless. This is what stops the ensemble serving a 'right total, wrong
        detail' claim on the arithmetic path."""
        critic = RecomputeCritic()
        claim = "There are 522 rows across 99 fully-annotated categories."
        # 99 matches no part/total/blank in ROWS -> not a clean confirm.
        assert critic.evaluate(claim, claim, ROWS) == UNVERIFIABLE


class _StubSemantic:
    """A ContentCritic stub returning a fixed verdict, for composition tests."""

    def __init__(self, verdict: ContentVerdict):
        self.verdict = verdict

    def evaluate(self, claim_text, normalized_claim, corpus_claims, domain=""):
        return self.verdict


# make sure the stub satisfies the protocol
_: ContentCritic = _StubSemantic(UNVERIFIABLE)


class TestEnsembleComposition:
    def test_recompute_does_not_upgrade_when_semantic_only_stays_silent(self):
        """The safety rule (found by review of PR #168): a numeric confirmation
        must NOT upgrade to CONSISTENT when the semantic critic merely stays
        silent (UNVERIFIABLE). A number match closes the arithmetic slice only; it
        does not affirm the non-numeric part of the claim. If the semantic critic
        cannot confirm, the honest verdict is UNVERIFIABLE, not CONSISTENT.

        (Earlier this test asserted CONSISTENT here, which was the vulnerability:
        it let a false non-numeric assertion wrapped around a correct number slip
        through. Inverted deliberately.)"""
        ens = EnsembleCritic(semantic=_StubSemantic(UNVERIFIABLE), deterministic=RecomputeCritic())
        claim = "There are 522 rows; 470 have no category label."
        assert ens.evaluate(claim, claim, ROWS) == UNVERIFIABLE

    def test_upgrades_only_when_both_critics_confirm(self):
        """The upgrade path: recompute CONSISTENT and semantic CONSISTENT both,
        so the ensemble returns CONSISTENT."""
        ens = EnsembleCritic(semantic=_StubSemantic(CONSISTENT), deterministic=RecomputeCritic())
        claim = "There are 522 rows; 470 have no category label."
        assert ens.evaluate(claim, claim, ROWS) == CONSISTENT

    def test_real_semantic_critic_false_claim_not_served(self):
        """The counterexample from the PR #168 review, with a REAL semantic critic
        (not a stub). The claim pairs a correct total (522) with a false
        non-numeric assertion ('none are blank' when 470 ARE blank). The
        EmbeddingCritic cannot see the falsehood, so it returns UNVERIFIABLE;
        recompute confirms the 522. The ensemble must NOT serve this.

        This is the test the original stub-only suite was missing: the stub
        returned CONTRADICTION and masked the gap. A real critic returns
        UNVERIFIABLE, which is exactly the case rule 3 must catch."""
        ens = EnsembleCritic(semantic=EmbeddingCritic(), deterministic=RecomputeCritic())
        false_claim = "There are 522 rows total, and none of them are blank."
        assert ens.evaluate(false_claim, false_claim, ROWS) != CONSISTENT

    def test_semantic_contradiction_beats_recompute_consistent(self):
        """THE SAFETY TEST (A2 trap): the claim carries a CORRECT number (522) but
        a FALSE assertion ('all annotated'). Recompute might confirm the total;
        NLI catches the false assertion. Contradiction must win -> never served."""
        ens = EnsembleCritic(semantic=_StubSemantic(CONTRADICTION), deterministic=RecomputeCritic())
        # correct total, but semantically false -> stub semantic says CONTRADICTION
        claim = "All 522 rows are fully annotated with no missing labels."
        assert ens.evaluate(claim, claim, ROWS) == CONTRADICTION

    def test_recompute_contradiction_is_honored(self):
        """A3 case: recompute detects an inflated aggregate even if semantic is
        unsure. Contradiction from either member wins."""
        ens = EnsembleCritic(semantic=_StubSemantic(UNVERIFIABLE), deterministic=RecomputeCritic())
        claim = "There are 900 rows in total."
        assert ens.evaluate(claim, claim, ROWS) == CONTRADICTION

    def test_falls_back_to_semantic_when_recompute_silent(self):
        """Non-numeric claim: recompute defers, ensemble returns the NLI verdict."""
        ens = EnsembleCritic(semantic=_StubSemantic(CONSISTENT), deterministic=RecomputeCritic())
        claim = "The categories are ranked in descending order."
        assert ens.evaluate(claim, claim, ROWS) == CONSISTENT

    def test_recompute_never_overrides_a_contradiction_into_serve(self):
        """Even if recompute would say CONSISTENT, a semantic CONTRADICTION on the
        SAME claim keeps it out of serve-class. Pinned explicitly."""
        ens = EnsembleCritic(semantic=_StubSemantic(CONTRADICTION), deterministic=RecomputeCritic())
        claim = "There are 522 rows; 470 have no category label."  # numerically true
        assert ens.evaluate(claim, claim, ROWS) == CONTRADICTION

    def test_all_integers_correct_but_false_prose_must_not_serve(self):
        """The soundness guard against OUTPUT-OVERRIDE.

        Every integer the claim states (522, 470, 26) is supported by the rows, so
        recompute returns CONSISTENT: it certifies the *integers*, not the
        *claim*. The claim also asserts 'fully validated and error-free', which is
        false and non-numeric; recompute is blind to it, the semantic critic is
        not. If the ensemble ever let recompute's CONSISTENT override a semantic
        CONTRADICTION, THIS would be served. It must not. Contradiction wins.
        """
        ens = EnsembleCritic(semantic=_StubSemantic(CONTRADICTION), deterministic=RecomputeCritic())
        claim = (
            "There are 522 rows, 470 blank, and category alpha has 26, and the "
            "dataset is fully validated and error-free."
        )
        # recompute alone certifies the integers...
        assert RecomputeCritic().evaluate(claim, claim, ROWS) == CONSISTENT
        # ...but the ensemble must still refuse to serve a semantically false claim
        assert ens.evaluate(claim, claim, ROWS) == CONTRADICTION
