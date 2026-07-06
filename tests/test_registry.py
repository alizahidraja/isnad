"""Tests for registry.py — narrator registry + jarḥ–taʿdīl state machine.

Verifies paper §4.2 commitments:
- Domain-conditioned grading: key is (narrator_id, domain).
- Version-bump resets to UNGRADED.
- jarḥ–taʿdīl is a state machine driven by evidence.
- ʿAdālah and ḍabṭ as two distinct axes.
- REJECTED is sticky (active containment).
"""

from isnad.registry import Registry
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
        reg = Registry()
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
        reg = Registry()
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
        reg = Registry()
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
        reg = Registry()
        reg.register("poisoned-source", "general", grade=NarratorGrade.REJECTED)

        new_grade = reg.record_evidence(
            "poisoned-source",
            "general",
            EvidenceType.HUMAN_REVIEW,
            EvidenceAction.TADIL,
            "Human reviewer cleared",
        )
        assert new_grade == NarratorGrade.WEAK  # restored to weak, not reliable


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
