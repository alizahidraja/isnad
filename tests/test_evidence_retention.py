"""Tests for evidence-log retention (issue #39)."""

from __future__ import annotations

from isnad.core.registry import Registry
from isnad.types import EvidenceAction, EvidenceType, NarratorType


def _seed(reg: Registry, n: int) -> None:
    reg.register("m", "d", narrator_type=NarratorType.MODEL)
    for i in range(n):
        reg.record_evidence("m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, f"e{i}")


class TestEvidenceRetention:
    def test_default_keeps_all_evidence(self):
        reg = Registry()
        _seed(reg, 5)
        assert len(reg.get("m", "d").evidence_log) == 5

    def test_retention_prunes_oldest_keeps_most_recent(self):
        reg = Registry(max_evidence_entries=3)
        _seed(reg, 5)
        narrator = reg.get("m", "d")
        assert len(narrator.evidence_log) == 3
        descriptions = [e["description"] for e in narrator.evidence_log]
        assert descriptions == ["e2", "e3", "e4"]

    def test_no_pruning_at_exact_limit(self):
        reg = Registry(max_evidence_entries=3)
        _seed(reg, 3)
        assert len(reg.get("m", "d").evidence_log) == 3

    def test_retention_is_per_narrator(self):
        reg = Registry(max_evidence_entries=2)
        reg.register("a", "d", narrator_type=NarratorType.MODEL)
        reg.register("b", "d", narrator_type=NarratorType.MODEL)
        for i in range(4):
            reg.record_evidence("a", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, f"a{i}")
        reg.record_evidence("b", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, "b0")
        assert len(reg.get("a", "d").evidence_log) == 2
        assert len(reg.get("b", "d").evidence_log) == 1
