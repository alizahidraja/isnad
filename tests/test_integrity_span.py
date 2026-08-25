"""Tests for narrator-level integrity (spans domains + roles, #28/#29)."""

from __future__ import annotations

from isnad.core.registry import Registry
from isnad.types import (
    AdalahGrade,
    EvidenceAction,
    EvidenceAxis,
    EvidenceType,
    NarratorGrade,
    Role,
)


class TestCrossDomainIntegrity:
    def test_quarantine_spans_domains(self):
        reg = Registry()
        reg.register("m", "physics", grade=NarratorGrade.RELIABLE)
        reg.register("m", "biology", grade=NarratorGrade.RELIABLE)
        reg.quarantine("m", "physics", "caught fabricating")
        # A liar is a liar everywhere — biology is also rejected.
        assert reg.get_grade("m", "biology") == NarratorGrade.REJECTED

    def test_get_adalah_is_narrator_level(self):
        reg = Registry()
        reg.register("m", "physics", grade=NarratorGrade.RELIABLE)
        reg.quarantine("m", "physics", "x")
        assert reg.get_adalah_grade("m", "biology") == AdalahGrade.COMPROMISED


class TestCrossRoleIntegrity:
    def test_integrity_strikes_accumulate_on_default_and_floor_roles(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.register("m", "d", role=Role.SYNTHESIS, grade=NarratorGrade.RELIABLE)
        reg.register("m", "d", role=Role.RETRIEVAL, grade=NarratorGrade.RELIABLE)

        # Three integrity strikes against one role route to the shared default
        # record (issue #29), and the ladder rejects the narrator everywhere.
        for _ in range(3):
            reg.record_evidence(
                "m",
                "d",
                EvidenceType.HUMAN_REVIEW,
                EvidenceAction.JARH,
                "proven lie in synthesis",
                axis=EvidenceAxis.INTEGRITY,
                role=Role.SYNTHESIS,
            )

        assert reg.get_grade("m", "d") == NarratorGrade.REJECTED
        assert reg.get_grade("m", "d", role=Role.RETRIEVAL) == NarratorGrade.REJECTED
        assert reg.get_grade("m", "d", role=Role.SYNTHESIS) == NarratorGrade.REJECTED

    def test_single_integrity_strike_hits_default_not_role(self):
        # One strike routes to the default record (shared), not the role record.
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.register("m", "d", role=Role.SYNTHESIS, grade=NarratorGrade.RELIABLE)
        reg.record_evidence(
            "m",
            "d",
            EvidenceType.HUMAN_REVIEW,
            EvidenceAction.JARH,
            axis=EvidenceAxis.INTEGRITY,
            role=Role.SYNTHESIS,
        )
        default = reg.get("m", "d")
        role_rec = reg.get("m", "d", role=Role.SYNTHESIS)
        assert any(
            e["evidence_type"] == EvidenceType.HUMAN_REVIEW.value for e in default.evidence_log
        )
        assert not any(
            e["evidence_type"] == EvidenceType.HUMAN_REVIEW.value for e in role_rec.evidence_log
        )

    def test_precision_jarh_does_not_compromise_narrator(self):
        # Only INTEGRITY-axis jarḥ is narrator-level; precision stays scoped.
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.record_evidence(
            "m",
            "d",
            EvidenceType.POST_HOC_AUDIT,
            EvidenceAction.JARH,
            "made an error",
            axis=EvidenceAxis.PRECISION,
        )
        # precision strike may lower the grade but does not COMPROMISE integrity.
        assert reg.get_adalah_grade("m", "d") != AdalahGrade.COMPROMISED


class TestOverturnClearsFloor:
    def test_adjudicate_overturn_restores_everywhere(self):
        reg = Registry()
        reg.register("m", "physics", grade=NarratorGrade.RELIABLE)
        reg.register("m", "biology", grade=NarratorGrade.RELIABLE)
        reg.quarantine("m", "physics", "mistake")
        reg.adjudicate("m", "physics", overturn=True)
        assert reg.get_grade("m", "biology") == NarratorGrade.RELIABLE
