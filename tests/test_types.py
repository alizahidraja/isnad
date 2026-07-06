"""Tests for ordinal types and enums — foundational epistemic commitments."""

from isnad.types import (
    ChainGrade,
    NarratorGrade,
    TransformType,
)


class TestNarratorGradeOrdering:
    """Ordinal-first grading: grades are ordered tiers, not floats."""

    def test_reliable_gt_acceptable(self) -> None:
        assert NarratorGrade.RELIABLE > NarratorGrade.ACCEPTABLE

    def test_acceptable_gt_weak(self) -> None:
        assert NarratorGrade.ACCEPTABLE > NarratorGrade.WEAK

    def test_weak_gt_rejected(self) -> None:
        assert NarratorGrade.WEAK > NarratorGrade.REJECTED

    def test_ungraded_lt_weak(self) -> None:
        assert NarratorGrade.UNGRADED < NarratorGrade.WEAK

    def test_min_selects_lowest(self) -> None:
        result = NarratorGrade.min(
            NarratorGrade.RELIABLE,
            NarratorGrade.WEAK,
            NarratorGrade.ACCEPTABLE,
        )
        assert result == NarratorGrade.WEAK

    def test_is_at_least_acceptable(self) -> None:
        assert NarratorGrade.RELIABLE.is_at_least_acceptable
        assert NarratorGrade.ACCEPTABLE.is_at_least_acceptable
        assert not NarratorGrade.WEAK.is_at_least_acceptable
        assert not NarratorGrade.REJECTED.is_at_least_acceptable


class TestChainGradeOrdering:
    def test_sahih_gt_hasan(self) -> None:
        assert ChainGrade.SAHIH > ChainGrade.HASAN

    def test_hasan_gt_daif(self) -> None:
        assert ChainGrade.HASAN > ChainGrade.DAIF

    def test_daif_gt_mawdu(self) -> None:
        assert ChainGrade.DAIF > ChainGrade.MAWDU

    def test_min_selects_lowest(self) -> None:
        result = ChainGrade.min(ChainGrade.SAHIH, ChainGrade.DAIF, ChainGrade.HASAN)
        assert result == ChainGrade.DAIF


class TestTransformType:
    def test_destructive_vs_generative_are_distinct(self) -> None:
        assert TransformType.DESTRUCTIVE != TransformType.GENERATIVE

    def test_pass_through_exists(self) -> None:
        assert TransformType.PASS_THROUGH.value == "pass_through"
