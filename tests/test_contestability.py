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


class TestOverturnDurability:
    """#182: an overturn must survive the next recompute AND get_grade_as_of —
    the operator's re-accreditation is not undone by a later evidence event or
    a period-sliced re-derivation."""

    def test_overturn_survives_next_evidence_event(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE, adalah=AdalahGrade.HIGH)
        reg.quarantine("m", "d", "mistaken strike")
        reg.adjudicate(
            "m",
            "d",
            overturn=True,
            target_grade=NarratorGrade.RELIABLE,
            target_adalah=AdalahGrade.HIGH,
        )
        assert reg.get("m", "d").grade == NarratorGrade.RELIABLE

        # A subsequent evidence event must NOT re-apply the overturned strike.
        # Before the #182 fix, the integrity jarḥ stayed in the log and the
        # recompute re-asserted the permanent cap, silently dropping the grade.
        reg.record_evidence(
            "m",
            "d",
            EvidenceType.EVAL_HARNESS,
            EvidenceAction.TADIL,
            "sustained precision after overturn",
        )
        n = reg.get("m", "d")
        # The overturned integrity strike did not re-apply: not REJECTED, and
        # integrity is not COMPROMISED.
        assert n.grade != NarratorGrade.REJECTED
        assert n.adalah_grade != AdalahGrade.COMPROMISED

    def test_get_grade_as_of_honors_overturn(self):
        from datetime import UTC, datetime, timedelta

        reg = Registry()
        t0 = datetime.now(UTC)
        reg.register("m", "d", grade=NarratorGrade.RELIABLE, adalah=AdalahGrade.HIGH)
        reg.quarantine("m", "d", "mistaken strike")
        t_q = datetime.now(UTC)
        reg.adjudicate("m", "d", overturn=True, target_grade=NarratorGrade.RELIABLE)
        t_o = datetime.now(UTC) + timedelta(seconds=1)

        # After the overturn, the re-derived grade must NOT be REJECTED.
        assert reg.get_grade_as_of("m", "d", as_of=t_o) == NarratorGrade.RELIABLE
        # Before the overturn, the quarantine still held.
        assert reg.get_grade_as_of("m", "d", as_of=t_q) == NarratorGrade.REJECTED
        assert t0 < t_q
