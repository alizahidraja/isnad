"""Tests for registry.py — narrator registry + jarḥ–taʿdīl state machine.

Verifies paper §4.2 commitments:
- Domain-conditioned grading: key is (narrator_id, domain).
- Version-bump resets to UNGRADED.
- jarḥ–taʿdīl is a state machine driven by evidence.
- ʿAdālah and ḍabṭ as two distinct axes.
- REJECTED is sticky (active containment) — with ThresholdTransitionPolicy.
- BayesianTransitionPolicy as the new default.
"""

from isnad.core.registry import BayesianTransitionPolicy, Registry, ThresholdTransitionPolicy
from isnad.types import (
    AdalahGrade,
    DabtGrade,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
)


class TestDomainConditionedGrading:
    """Registry key is (narrator_id, domain), never narrator_id alone."""

    def test_same_narrator_different_domains_have_different_grades(self) -> None:
        reg = Registry()

        reg.register("model-M", "physics-classical", grade=NarratorGrade.RELIABLE)
        reg.register("model-M", "physics-quantum", grade=NarratorGrade.WEAK)

        assert reg.get_grade("model-M", "physics-classical") == NarratorGrade.RELIABLE
        assert reg.get_grade("model-M", "physics-quantum") == NarratorGrade.WEAK

    def test_unknown_narrator_defaults_to_ungraded(self) -> None:
        reg = Registry()
        assert reg.get_grade("nonexistent", "any-domain") == NarratorGrade.UNGRADED


class TestVersionBumpReset:
    """Version bump resets narrator to UNGRADED per domain (paper §4.2)."""

    def test_version_bump_resets_grade(self) -> None:
        reg = Registry()
        reg.register(
            "ingest-model",
            "physics",
            grade=NarratorGrade.RELIABLE,
            model_version="v1",
        )
        assert reg.get_grade("ingest-model", "physics") == NarratorGrade.RELIABLE

        reg.bump_version("ingest-model", "physics", "v2")
        assert reg.get_grade("ingest-model", "physics") == NarratorGrade.UNGRADED

    def test_version_bump_clears_error_rate(self) -> None:
        reg = Registry()
        reg.register(
            "ingest-model",
            "physics",
            grade=NarratorGrade.ACCEPTABLE,
            known_error_rate=0.05,
            model_version="v1",
        )

        reg.bump_version("ingest-model", "physics", "v2")
        narrator = reg.get("ingest-model", "physics")
        assert narrator is not None
        assert narrator.known_error_rate is None
        assert narrator.model_version == "v2"

    def test_version_bump_resets_adalah_and_dabt(self) -> None:
        reg = Registry()
        reg.register(
            "ingest-model",
            "physics",
            adalah=AdalahGrade.HIGH,
            dabt=DabtGrade.HIGH,
        )

        reg.bump_version("ingest-model", "physics", "v2")
        narrator = reg.get("ingest-model", "physics")
        assert narrator is not None
        assert narrator.adalah_grade == AdalahGrade.UNASSESSED
        assert narrator.dabt_grade == DabtGrade.UNASSESSED

    def test_version_bump_logs_evidence(self) -> None:
        reg = Registry()
        reg.register("ingest-model", "physics")
        reg.bump_version("ingest-model", "physics", "v2")

        narrator = reg.get("ingest-model", "physics")
        assert narrator is not None
        assert len(narrator.evidence_log) == 1
        assert narrator.evidence_log[0]["evidence_type"] == EvidenceType.VERSION_BUMP.value


class TestJarhTadilStateMachine:
    """The jarḥ–taʿdīl loop is a state machine, not a formula (paper §4.2)."""

    def test_downgrade_on_sufficient_adverse_evidence(self) -> None:
        """Threshold policy: 3 adverse → downgrade from RELIABLE to ACCEPTABLE."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("scraper-v1", "physics", grade=NarratorGrade.RELIABLE)

        # 3 adverse events → downgrade
        for i in range(3):
            new_grade = reg.record_evidence(
                "scraper-v1",
                "physics",
                EvidenceType.POST_HOC_AUDIT,
                EvidenceAction.JARH,
                f"Audit failure {i}",
            )
        assert new_grade == NarratorGrade.ACCEPTABLE

    def test_upgrade_requires_sustained_corroborated_accuracy(self) -> None:
        """Threshold policy: 5 positive (3 corroborated) → upgrade to ACCEPTABLE."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("model-M", "physics", grade=NarratorGrade.WEAK)

        # Give 5 positive events, 3 of which are corroboration outcomes
        for i in range(3):
            reg.record_evidence(
                "model-M",
                "physics",
                EvidenceType.CORROBORATION_OUTCOME,
                EvidenceAction.TADIL,
                f"Corroborated {i}",
            )
        for i in range(2):
            reg.record_evidence(
                "model-M",
                "physics",
                EvidenceType.EVAL_HARNESS,
                EvidenceAction.TADIL,
                f"Eval pass {i}",
            )

        narrator = reg.get("model-M", "physics")
        assert narrator is not None
        assert narrator.grade == NarratorGrade.ACCEPTABLE

    def test_rejected_is_sticky(self) -> None:
        """Threshold policy: REJECTED is sticky — only human review restores."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("poisoned-source", "general", grade=NarratorGrade.REJECTED)

        # Even favorable evidence shouldn't auto-restore
        new_grade = reg.record_evidence(
            "poisoned-source",
            "general",
            EvidenceType.CORROBORATION_OUTCOME,
            EvidenceAction.TADIL,
            "Corroborated claim",
        )
        assert new_grade == NarratorGrade.REJECTED

    def test_human_review_can_restore_from_rejected(self) -> None:
        """Threshold policy: HUMAN_REVIEW + TADIL restores REJECTED → WEAK."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("poisoned-source", "general", grade=NarratorGrade.REJECTED)

        new_grade = reg.record_evidence(
            "poisoned-source",
            "general",
            EvidenceType.HUMAN_REVIEW,
            EvidenceAction.TADIL,
            "Human reviewer cleared",
        )
        assert new_grade == NarratorGrade.WEAK  # restored to weak, not reliable


class TestBayesianTransitionPolicy:
    """BayesianTransitionPolicy: Beta-distribution narrator grades."""

    def test_default_registry_uses_bayesian(self) -> None:
        """Registry() defaults to BayesianTransitionPolicy."""
        reg = Registry()
        assert isinstance(reg.transition_policy, BayesianTransitionPolicy)

    def test_bayesian_start_from_ungraded(self) -> None:
        """Ungraded narrator with no evidence stays UNGRADED."""
        reg = Registry()
        assert reg.get_grade("new-narrator", "physics") == NarratorGrade.UNGRADED

    def test_bayesian_one_positive_is_weak(self) -> None:
        """Beta(2,1): mean=0.67 → WEAK (just barely above 0.50)."""
        reg = Registry()
        new_grade = reg.record_evidence(
            "model-A",
            "physics",
            EvidenceType.EVAL_HARNESS,
            EvidenceAction.TADIL,
            "Passed eval",
        )
        assert new_grade == NarratorGrade.WEAK

    def test_bayesian_sustained_positive_reaches_acceptable(self) -> None:
        """5 positive + 1 adverse: Beta(7,2), mean=0.78 → ACCEPTABLE."""
        reg = Registry()
        for i in range(5):
            reg.record_evidence(
                "model-B",
                "physics",
                EvidenceType.CORROBORATION_OUTCOME,
                EvidenceAction.TADIL,
                f"Pass {i}",
            )
        reg.record_evidence(
            "model-B",
            "physics",
            EvidenceType.POST_HOC_AUDIT,
            EvidenceAction.JARH,
            "Minor error",
        )
        assert reg.get_grade("model-B", "physics") == NarratorGrade.ACCEPTABLE

    def test_bayesian_many_positives_reaches_reliable(self) -> None:
        """10 positive, 0 adverse: Beta(11,1), mean=0.917 → RELIABLE."""
        reg = Registry()
        for i in range(10):
            reg.record_evidence(
                "model-C",
                "physics",
                EvidenceType.CORROBORATION_OUTCOME,
                EvidenceAction.TADIL,
                f"Pass {i}",
            )
        assert reg.get_grade("model-C", "physics") == NarratorGrade.RELIABLE

    def test_bayesian_adverse_dominates_with_few_samples(self) -> None:
        """3 adverse, 0 positive: Beta(1,4), mean=0.20 → REJECTED."""
        reg = Registry()
        for i in range(3):
            reg.record_evidence(
                "model-D",
                "physics",
                EvidenceType.POST_HOC_AUDIT,
                EvidenceAction.JARH,
                f"Failure {i}",
            )
        assert reg.get_grade("model-D", "physics") == NarratorGrade.REJECTED

    def test_bayesian_version_bump_resets(self) -> None:
        """Version bump resets to UNGRADED regardless of evidence."""
        reg = Registry()
        reg.register("model-E", "physics", grade=NarratorGrade.RELIABLE)
        reg.bump_version("model-E", "physics", "v2")
        assert reg.get_grade("model-E", "physics") == NarratorGrade.UNGRADED

    def test_bayesian_seeding_prior(self) -> None:
        """Seeding a prior mean works."""
        policy = BayesianTransitionPolicy()
        policy.seed_grade("model-F", "physics", prior_mean=0.85, prior_weight=10.0)
        state = policy.get_state("model-F", "physics")
        # alpha = 0.85*10 + 1 = 9.5, beta = 0.15*10 + 1 = 2.5
        # mean = 9.5 / 12.0 ≈ 0.79
        assert 0.78 < state.mean < 0.80
        assert state.to_grade() == NarratorGrade.ACCEPTABLE

    def test_bayesian_can_recover_from_rejected(self) -> None:
        """Bayesian policy: REJECTED is NOT sticky — evidence can restore."""
        reg = Registry()
        reg.register("model-G", "general", grade=NarratorGrade.REJECTED)
        # The Bayesian policy derives grades from posterior, not sticky states.
        # After 1 TADIL, state is built from all evidence.
        new_grade = reg.record_evidence(
            "model-G",
            "general",
            EvidenceType.HUMAN_REVIEW,
            EvidenceAction.TADIL,
            "Human review passed",
        )
        # With 1 positive, 0 adverse → Beta(2,1), mean=0.67 → WEAK
        assert new_grade == NarratorGrade.WEAK


class TestAdalahDabtAxes:
    """ʿAdālah and ḍabṭ are two distinct axes (paper §4.2)."""

    def test_adalah_and_dabt_are_stored_separately(self) -> None:
        reg = Registry()
        reg.register(
            "source-A",
            "physics",
            adalah=AdalahGrade.HIGH,
            dabt=DabtGrade.LOW,
        )
        narrator = reg.get("source-A", "physics")
        assert narrator is not None
        assert narrator.adalah_grade == AdalahGrade.HIGH
        assert narrator.dabt_grade == DabtGrade.LOW

    def test_quarantine_sets_adalah_compromised(self) -> None:
        reg = Registry()
        reg.register("bad-source", "physics", adalah=AdalahGrade.ACCEPTABLE)
        reg.quarantine("bad-source", "physics", "Injection detected")

        narrator = reg.get("bad-source", "physics")
        assert narrator is not None
        assert narrator.grade == NarratorGrade.REJECTED
        assert narrator.adalah_grade == AdalahGrade.COMPROMISED
        assert not narrator.is_active
