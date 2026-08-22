"""Tests for the Bayesian policy's integrity strikes-per-tier ladder (#30).

The default BayesianTransitionPolicy previously only enforced REJECTED-stickiness.
It now enforces the full axis split the threshold policies already had:

- Integrity (ʿadālah) jarḥ (JARH with axis != PRECISION) accumulates permanently
  and imposes a tier ceiling via _integrity_cap.
- Precision (ḍabṭ) jarḥ feeds the recoverable Beta posterior.
- The posterior grade is clamped to the integrity ceiling.

Default integrity_strikes_per_tier = 1 (matrūk: one proven integrity impugnment
caps one tier).  Configurable.
"""

from __future__ import annotations

from isnad.core.registry import BayesianTransitionPolicy, Registry
from isnad.types import (
    EvidenceAction,
    EvidenceAxis,
    EvidenceType,
    NarratorGrade,
)


def _tadil_registry(n: int = 10) -> Registry:
    """A registry whose narrator has N precision taʿdīl (survival) entries."""
    reg = Registry(transition_policy=BayesianTransitionPolicy())
    reg.register("m", "d")
    for i in range(n):
        reg.record_survival("m", "d", f"c-{i}", "gov.uk")
    return reg


class TestIntegrityStrikeCaps:
    def test_one_integrity_strike_caps_reliable_to_acceptable(self) -> None:
        reg = _tadil_registry(10)
        assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE
        reg.record_evidence(
            "m", "d", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, axis=EvidenceAxis.INTEGRITY
        )
        assert reg.get_grade("m", "d") == NarratorGrade.ACCEPTABLE

    def test_two_strikes_cap_to_weak(self) -> None:
        reg = _tadil_registry(10)
        for _ in range(2):
            reg.record_evidence(
                "m",
                "d",
                EvidenceType.HUMAN_REVIEW,
                EvidenceAction.JARH,
                axis=EvidenceAxis.INTEGRITY,
            )
        assert reg.get_grade("m", "d") == NarratorGrade.WEAK

    def test_three_strikes_cap_to_rejected(self) -> None:
        reg = _tadil_registry(10)
        for _ in range(3):
            reg.record_evidence(
                "m",
                "d",
                EvidenceType.HUMAN_REVIEW,
                EvidenceAction.JARH,
                axis=EvidenceAxis.INTEGRITY,
            )
        assert reg.get_grade("m", "d") == NarratorGrade.REJECTED

    def test_precision_evidence_cannot_lift_past_integrity_cap(self) -> None:
        reg = _tadil_registry(10)
        reg.record_evidence(
            "m", "d", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, axis=EvidenceAxis.INTEGRITY
        )
        assert reg.get_grade("m", "d") == NarratorGrade.ACCEPTABLE
        # A flood of precision evidence must not restore RELIABLE.
        for i in range(50):
            reg.record_survival("m", "d", f"more-{i}", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.ACCEPTABLE


class TestPrecisionJarhIsRecoverable:
    def test_precision_jarh_is_recoverable_not_a_permanent_cap(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d")
        # Build RELIABLE via precision taʿdīl.
        for i in range(10):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE
        # A precision jarḥ lowers the Beta, but is NOT a permanent integrity cap.
        reg.record_evidence("m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH)
        assert reg.get_grade("m", "d") == NarratorGrade.ACCEPTABLE  # Beta lowered, not capped
        # More precision taʿdīl recovers — proving it wasn't a permanent cap.
        for i in range(10):
            reg.record_survival("m", "d", f"d-{i}", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE

    def test_integrity_jarh_is_not_recoverable_by_precision(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d")
        reg.record_evidence(
            "m", "d", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, axis=EvidenceAxis.INTEGRITY
        )
        for i in range(30):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        # One integrity strike caps at ACCEPTABLE forever.
        assert reg.get_grade("m", "d") == NarratorGrade.ACCEPTABLE


class TestConfigurableStrikesPerTier:
    def test_per_tier_three_needs_three_strikes(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy(integrity_strikes_per_tier=3))
        reg.register("m", "d")
        for i in range(10):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE

        # Two strikes with per-tier=3 → still no cap (0 tiers down).
        for _ in range(2):
            reg.record_evidence(
                "m",
                "d",
                EvidenceType.HUMAN_REVIEW,
                EvidenceAction.JARH,
                axis=EvidenceAxis.INTEGRITY,
            )
        assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE

        # Third strike → one tier down.
        reg.record_evidence(
            "m", "d", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, axis=EvidenceAxis.INTEGRITY
        )
        assert reg.get_grade("m", "d") == NarratorGrade.ACCEPTABLE


class TestRejectedStickinessStillHolds:
    def test_quarantine_stays_rejected_despite_precision_flood(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.quarantine("m", "d", "caught")
        assert reg.get_grade("m", "d") == NarratorGrade.REJECTED
        for i in range(30):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.REJECTED

    def test_human_review_restores_to_weak_then_strike_asserts_cap(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.quarantine("m", "d", "caught")
        reg.record_evidence(
            "m", "d", EvidenceType.HUMAN_REVIEW, EvidenceAction.TADIL, "rehabilitated on review"
        )
        assert reg.get_grade("m", "d") == NarratorGrade.WEAK
        # The permanent integrity strike re-asserts a ceiling (ACCEPTABLE).
        for i in range(10):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") == NarratorGrade.ACCEPTABLE


class TestEpochBoundaryClearsIntegrityStrikes:
    def test_version_bump_forgets_pre_bump_integrity_strike(self) -> None:
        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("m", "d")
        reg.record_evidence(
            "m", "d", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, axis=EvidenceAxis.INTEGRITY
        )
        reg.bump_version("m", "d", "v2")
        assert reg.get_grade("m", "d") == NarratorGrade.UNGRADED
        # Pre-bump integrity strike is an old narrator; new version starts clean.
        for i in range(10):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        assert reg.get_grade("m", "d") in (
            NarratorGrade.ACCEPTABLE,
            NarratorGrade.RELIABLE,
        )
