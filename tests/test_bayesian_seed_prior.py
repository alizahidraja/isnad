"""Regression tests for #90 and #91 in the Bayesian policy.

#90 — seed grades are no longer clobbered by the first evidence.
  ``register(grade=RELIABLE)`` followed by its ``BOOTSTRAP_SEED`` marker must
  keep the seed, not collapse to WEAK on the first recompute. The seed rides in
  the BOOTSTRAP_SEED evidence metadata as a Beta prior.

#91 — REJECTED is reachable below 50% posterior error.
  The weak/rejected boundary was tightened from 0.50 to 0.60, so a narrator
  with >~40% observed error is quarantined instead of lingering as WEAK.
"""

from __future__ import annotations

from isnad.core.policies import BetaState, BayesianTransitionPolicy
from isnad.core.registry import Registry
from isnad.types import EvidenceAction, EvidenceType, NarratorGrade


class TestSeedGradeNotClobbered:
    def test_reliable_seed_survives_bootstrap_marker(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.record_evidence("m", "d", EvidenceType.BOOTSTRAP_SEED, EvidenceAction.TADIL)
        assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE

    def test_acceptable_seed_survives_bootstrap_marker(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.ACCEPTABLE)
        reg.record_evidence("m", "d", EvidenceType.BOOTSTRAP_SEED, EvidenceAction.TADIL)
        assert reg.get_grade("m", "d") == NarratorGrade.ACCEPTABLE

    def test_seed_prior_persists_through_a_good_observation(self) -> None:
        """A seeded RELIABLE narrator stays RELIABLE after one more survival,
        rather than the seed prior evaporating and dropping a tier."""
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.record_evidence("m", "d", EvidenceType.BOOTSTRAP_SEED, EvidenceAction.TADIL)
        reg.record_survival("m", "d", "c-0", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE

    def test_seed_prior_can_still_fall_with_adverse_evidence(self) -> None:
        """The seed is a prior, not a hard floor: enough jarḥ still lowers it."""
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.record_evidence("m", "d", EvidenceType.BOOTSTRAP_SEED, EvidenceAction.TADIL)
        for _ in range(3):
            reg.record_evidence("m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH)
        assert reg.get_grade("m", "d") == NarratorGrade.WEAK

    def test_rejected_seed_without_marker_still_recoverable(self) -> None:
        """Guard: register(REJECTED) *without* a BOOTSTRAP_SEED marker keeps the
        pre-#90 behaviour — the Bayesian policy re-derives from evidence, so a
        precision-driven REJECTED stays recoverable (issue #40)."""
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.REJECTED)
        for i in range(10):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") in (
            NarratorGrade.ACCEPTABLE,
            NarratorGrade.RELIABLE,
        )


class TestRejectedThresholdReachable:
    def test_mean_0_55_is_rejected_by_default(self) -> None:
        """~45% observed error → REJECTED under the tightened default boundary."""
        assert BetaState(alpha=11, beta=9).to_grade() == NarratorGrade.REJECTED

    def test_old_lenient_boundary_still_configurable(self) -> None:
        """The old >50% boundary is recoverable by passing weak_threshold=0.50."""
        assert BetaState(alpha=11, beta=9).to_grade(weak_threshold=0.50) == NarratorGrade.WEAK

    def test_high_error_reaches_rejected_via_policy(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d")
        for _ in range(6):
            reg.record_evidence("m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH)
        for i in range(4):
            reg.record_survival("m", "d", f"ok-{i}", "gov.uk")
        # 6 jarh vs 4 tadil → posterior mean ≈ 5/12 ≈ 0.42 → REJECTED.
        assert reg.get_grade("m", "d") == NarratorGrade.REJECTED
