"""Tests for #40 — REJECTED-stickiness is now scoped to integrity, not precision.

Before the fix, ANY REJECTED was sticky: a narrator driven to REJECTED by
*precision* evidence (a wrong answer, not a lie) could never recover.  The fix
separates the two paths:

- Integrity-driven REJECTED (quarantine → ʿadālah COMPROMISED) → **sticky**;
  only an explicit human-review taʿdīl restores it.
- Precision-driven REJECTED (Beta posterior / precision downgrades) →
  **recoverable** via sustained precision evidence.
"""

from __future__ import annotations

from isnad.core.registry import BayesianTransitionPolicy, Registry, ThresholdTransitionPolicy
from isnad.types import EvidenceAction, EvidenceType, NarratorGrade


class TestBayesianPrecisionRejectedRecovers:
    def test_single_precision_jarh_then_tadil_recovers(self) -> None:
        """The #40 repro: one precision jarḥ on a fresh narrator → REJECTED,
        then precision taʿdīl must recover it (not stick)."""
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d")
        reg.record_evidence("m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH)
        assert reg.get_grade("m", "d") == NarratorGrade.REJECTED  # Beta(1,2)

        for i in range(10):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") in (
            NarratorGrade.ACCEPTABLE,
            NarratorGrade.RELIABLE,
        )

    def test_precision_jarh_on_reliable_drops_but_recovers(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d")
        for i in range(10):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE

        # A precision jarḥ drops the Beta, but is not permanent.
        reg.record_evidence("m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH)
        assert reg.get_grade("m", "d") == NarratorGrade.ACCEPTABLE
        for i in range(10):
            reg.record_survival("m", "d", f"d-{i}", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE


class TestBayesianIntegrityRejectedStaysSticky:
    def test_quarantined_rejected_is_not_recoverable_by_precision(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.quarantine("m", "d", "caught fabricating")
        for i in range(30):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.REJECTED

    def test_human_review_restores_quarantined_to_weak(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.quarantine("m", "d", "caught fabricating")
        reg.record_evidence(
            "m", "d", EvidenceType.HUMAN_REVIEW, EvidenceAction.TADIL, "cleared on review"
        )
        assert reg.get_grade("m", "d") == NarratorGrade.WEAK


class TestThresholdPrecisionRejectedRecovers:
    def test_precision_rejected_recovers_via_sustained_clean_streak(self) -> None:
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        # Non-quarantined REJECTED (adalah stays UNASSESSED).
        reg.register("m", "d", grade=NarratorGrade.REJECTED)
        # A sustained corroborated clean streak lifts REJECTED → WEAK → … .
        for i in range(6):
            reg.record_evidence("m", "d", EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL)
        assert reg.get_grade("m", "d") in (
            NarratorGrade.WEAK,
            NarratorGrade.ACCEPTABLE,
            NarratorGrade.RELIABLE,
        )

    def test_quarantined_rejected_stays_sticky_in_threshold(self) -> None:
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.quarantine("m", "d", "caught fabricating")
        for i in range(10):
            reg.record_evidence("m", "d", EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL)
        assert reg.get_grade("m", "d") == NarratorGrade.REJECTED

    def test_precision_jarh_cannot_sink_below_rejected(self) -> None:
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.REJECTED)
        # A precision jarḥ at REJECTED must not "wrap" the grade upward.
        for _ in range(4):
            reg.record_evidence("m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH)
        assert reg.get_grade("m", "d") == NarratorGrade.REJECTED


class TestStickinessDrivenByCompromisedFlag:
    def test_register_with_compromised_adalah_is_sticky(self) -> None:
        """Stickiness keys on adalah=COMPROMISED, not on the quarantine() method."""
        from isnad.types import AdalahGrade

        for policy in [BayesianTransitionPolicy(), ThresholdTransitionPolicy()]:
            reg = Registry(transition_policy=policy)
            reg.register(
                "m", "d", grade=NarratorGrade.REJECTED, adalah=AdalahGrade.COMPROMISED
            )
            for i in range(20):
                reg.record_survival("m", "d", f"c-{i}", "gov.uk")
            assert reg.get_grade("m", "d") == NarratorGrade.REJECTED

    def test_register_rejected_without_compromised_is_recoverable(self) -> None:
        """The mirror case: REJECTED without COMPROMISED is precision-driven."""
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.REJECTED)
        for i in range(10):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") in (
            NarratorGrade.ACCEPTABLE,
            NarratorGrade.RELIABLE,
        )
