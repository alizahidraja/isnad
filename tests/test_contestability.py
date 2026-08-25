"""Tests for contestability — dispute + adjudicate (issue #38)."""

from __future__ import annotations

import pytest

from isnad.core.registry import Registry
from isnad.types import AdalahGrade, EvidenceAction, EvidenceType, NarratorGrade


class TestDispute:
    def test_logs_without_grade_change(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        d = reg.dispute("m", "d", "I disagree")
        assert d.disputed_grade == "reliable"
        assert reg.get("m", "d").grade == NarratorGrade.RELIABLE  # unchanged
        last = reg.get("m", "d").evidence_log[-1]
        assert last["evidence_type"] == EvidenceType.DISPUTE.value
        assert last["action"] == EvidenceAction.NEUTRAL.value

    def test_requires_existing_narrator(self):
        reg = Registry()
        with pytest.raises(KeyError):
            reg.dispute("nonexistent", "d")


class TestAdjudicate:
    def test_uphold_leaves_grade_unchanged(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.WEAK)
        assert reg.adjudicate("m", "d", overturn=False) == NarratorGrade.WEAK

    def test_overturn_restores_quarantined_narrator(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE, adalah=AdalahGrade.HIGH)
        reg.quarantine("m", "d", "mistaken strike")
        assert reg.get("m", "d").grade == NarratorGrade.REJECTED
        assert reg.get("m", "d").adalah_grade == AdalahGrade.COMPROMISED

        grade = reg.adjudicate("m", "d", overturn=True, reason="strike was a mistake")
        assert grade == NarratorGrade.ACCEPTABLE
        narrator = reg.get("m", "d")
        assert narrator.adalah_grade == AdalahGrade.ACCEPTABLE
        assert narrator.is_active is True

    def test_overturn_targets_are_configurable(self):
        reg = Registry()
        reg.register("m", "d")
        reg.quarantine("m", "d", "q")
        reg.adjudicate(
            "m",
            "d",
            overturn=True,
            target_grade=NarratorGrade.RELIABLE,
            target_adalah=AdalahGrade.HIGH,
        )
        assert reg.get("m", "d").grade == NarratorGrade.RELIABLE
        assert reg.get("m", "d").adalah_grade == AdalahGrade.HIGH


class TestAuditTrail:
    def test_strike_dispute_adjudication_are_all_logged(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE, adalah=AdalahGrade.HIGH)
        reg.quarantine("m", "d", "q")
        reg.dispute("m", "d", "d")
        reg.adjudicate("m", "d", overturn=True)
        types = [e["evidence_type"] for e in reg.get("m", "d").evidence_log]
        assert types == ["human_review", "dispute", "adjudication"]

    def test_overturn_is_marked_in_metadata(self):
        reg = Registry()
        reg.register("m", "d")
        reg.quarantine("m", "d", "q")
        reg.adjudicate("m", "d", overturn=True)
        last = reg.get("m", "d").evidence_log[-1]
        assert last["metadata"]["overturned"] is True
