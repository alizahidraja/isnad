"""Tests for matrix.py — the 4×2 decision matrix.

Verifies paper §4.4: every cell routes to the correct action, including:
- ṣaḥīḥ × contradiction → REVIEW (ʿilal)
- mawḍūʿ → REJECT_AND_QUARANTINE_NARRATOR
- All 8 core cells (plus unverifiable variants).
"""

from isnad.core.decision import decide, describe_action
from isnad.types import Action, ChainGrade, ContentVerdict


class TestDecisionMatrix:
    """Each cell of the 4×2 + unverifiable matrix routes correctly."""

    # --- SAHIH row ---
    def test_sahih_consistent_serve(self) -> None:
        assert decide(ChainGrade.SAHIH, ContentVerdict.CONSISTENT) == Action.SERVE

    def test_sahih_contradiction_review(self) -> None:
        """ṣaḥīḥ × contradiction → REVIEW (ʿilal) — highest-value case."""
        assert decide(ChainGrade.SAHIH, ContentVerdict.CONTRADICTION) == Action.REVIEW

    def test_sahih_unverifiable_caveat(self) -> None:
        assert decide(ChainGrade.SAHIH, ContentVerdict.UNVERIFIABLE) == Action.SERVE_WITH_CAVEAT

    # --- HASAN row ---
    def test_hasan_consistent_caveat(self) -> None:
        assert decide(ChainGrade.HASAN, ContentVerdict.CONSISTENT) == Action.SERVE_WITH_CAVEAT

    def test_hasan_contradiction_review(self) -> None:
        """ḥasan × contradiction → REVIEW; do not serve."""
        assert decide(ChainGrade.HASAN, ContentVerdict.CONTRADICTION) == Action.REVIEW

    def test_hasan_unverifiable_review(self) -> None:
        assert decide(ChainGrade.HASAN, ContentVerdict.UNVERIFIABLE) == Action.REVIEW

    # --- DAIF row ---
    def test_daif_consistent_review(self) -> None:
        """ḍaʿīf × consistent → REVIEW; seek corroboration first."""
        assert decide(ChainGrade.DAIF, ContentVerdict.CONSISTENT) == Action.REVIEW

    def test_daif_contradiction_quarantine(self) -> None:
        assert decide(ChainGrade.DAIF, ContentVerdict.CONTRADICTION) == Action.QUARANTINE

    def test_daif_unverifiable_review(self) -> None:
        assert decide(ChainGrade.DAIF, ContentVerdict.UNVERIFIABLE) == Action.REVIEW

    # --- MAWDU row ---
    def test_mawdu_consistent_reject_and_quarantine(self) -> None:
        """mawḍūʿ tier = active containment, not passive label."""
        result = decide(ChainGrade.MAWDU, ContentVerdict.CONSISTENT)
        assert result == Action.REJECT_AND_QUARANTINE_NARRATOR

    def test_mawdu_contradiction_reject_and_quarantine(self) -> None:
        result = decide(ChainGrade.MAWDU, ContentVerdict.CONTRADICTION)
        assert result == Action.REJECT_AND_QUARANTINE_NARRATOR

    def test_mawdu_unverifiable_reject_and_quarantine(self) -> None:
        result = decide(ChainGrade.MAWDU, ContentVerdict.UNVERIFIABLE)
        assert result == Action.REJECT_AND_QUARANTINE_NARRATOR

    # --- All mawḍūʿ cells are containment ---
    def test_all_mawdu_cells_are_reject_and_quarantine(self) -> None:
        """Every mawḍūʿ cell quarantines — containment is unconditional."""
        for verdict in ContentVerdict:
            assert decide(ChainGrade.MAWDU, verdict) == Action.REJECT_AND_QUARANTINE_NARRATOR

    # --- Descriptive output ---
    def test_describe_action_returns_string(self) -> None:
        desc = describe_action(ChainGrade.SAHIH, ContentVerdict.CONTRADICTION)
        assert "ʿilal" in desc.lower() or "highest-value" in desc.lower()
