"""Tests for bench.mapping — the preregistered rank→grade and hukum→grade rules."""

from __future__ import annotations

from isnad.types import AdalahGrade, ChainGrade, DabtGrade, NarratorGrade

from bench.mapping import (
    SENTINEL_NAMES,
    chain_grade_from_hukum,
    grade_from_qawl,
    is_sentinel,
    narrator_grade_from_rank,
)


class TestNarratorRankMapping:
    def test_reliable_tiers(self):
        for rn in (1, 2, 3):
            m = narrator_grade_from_rank(rn, "ثقة")
            assert m.narrator_grade == NarratorGrade.RELIABLE
            assert m.adalah_grade == AdalahGrade.HIGH
            assert m.dabt_grade == DabtGrade.HIGH

    def test_acceptable_tiers(self):
        m4 = narrator_grade_from_rank(4, "صدوق حسن الحديث")
        assert m4.narrator_grade == NarratorGrade.ACCEPTABLE
        assert m4.dabt_grade == DabtGrade.ACCEPTABLE

    def test_rank5_precision_is_low(self):
        # صدوق يهم: truthful but errs — the two-axis split is load-bearing.
        m = narrator_grade_from_rank(5, "صدوق يهم")
        assert m.narrator_grade == NarratorGrade.ACCEPTABLE
        assert m.adalah_grade == AdalahGrade.ACCEPTABLE  # integrity fine
        assert m.dabt_grade == DabtGrade.LOW  # precision weak

    def test_maqbul_is_acceptable(self):
        assert narrator_grade_from_rank(6, "مقبول").narrator_grade == NarratorGrade.ACCEPTABLE

    def test_unknown_tiers_are_ungraded(self):
        for rn in (7, 9):
            m = narrator_grade_from_rank(rn)
            assert m.narrator_grade == NarratorGrade.UNGRADED
            assert m.adalah_grade == AdalahGrade.UNASSESSED

    def test_weak_tier(self):
        m = narrator_grade_from_rank(8, "ضعيف الحديث")
        assert m.narrator_grade == NarratorGrade.WEAK
        assert m.adalah_grade == AdalahGrade.ACCEPTABLE  # precision, not integrity
        assert m.dabt_grade == DabtGrade.LOW

    def test_rejected_tiers(self):
        m10 = narrator_grade_from_rank(10, "متروك الحديث")
        assert m10.narrator_grade == NarratorGrade.REJECTED
        assert m10.adalah_grade == AdalahGrade.SUSPECT

        for rn in (11, 12):
            m = narrator_grade_from_rank(rn, "كذاب")
            assert m.narrator_grade == NarratorGrade.REJECTED
            assert m.adalah_grade == AdalahGrade.COMPROMISED

    def test_unranked_or_none_is_ungraded(self):
        assert narrator_grade_from_rank(None).narrator_grade == NarratorGrade.UNGRADED
        assert narrator_grade_from_rank(0).narrator_grade == NarratorGrade.UNGRADED


class TestSentinelDetection:
    def test_sentinel_names(self):
        for name in SENTINEL_NAMES:
            assert is_sentinel(name, 12, None) is True

    def test_rank12_with_null_rank_is_sentinel(self):
        assert is_sentinel(None, 12, None) is True

    def test_real_fabricator_is_not_sentinel(self):
        assert is_sentinel("كذاب", 12, "كذاب") is False

    def test_sentinel_maps_to_ungraded_and_flagged(self):
        m = narrator_grade_from_rank(12, None, "موضع تعليق")
        assert m.is_sentinel is True
        assert m.narrator_grade == NarratorGrade.UNGRADED


class TestHukumClassification:
    def test_sahih(self):
        assert chain_grade_from_hukum("إسناده متصل ، رجاله ثقات") == ChainGrade.SAHIH
        assert (
            chain_grade_from_hukum("إسناده متصل ، رجاله ثقات ، رجاله رجال البخاري")
            == ChainGrade.SAHIH
        )

    def test_hasan(self):
        assert chain_grade_from_hukum("إسناد حسن") == ChainGrade.HASAN
        assert chain_grade_from_hukum("إسناده حسن رجاله ثقات عدا فلان وهو صدوق") == ChainGrade.HASAN

    def test_daif(self):
        assert chain_grade_from_hukum("إسناد ضعيف فيه فلان وهو ضعيف الحديث") == ChainGrade.DAIF
        # "weak but becomes hasan with corroboration" is still weak alone.
        assert chain_grade_from_hukum("إسناد ضعيف ويحسن إذا توبع") == ChainGrade.DAIF

    def test_mawdu_markers_take_precedence_over_weak(self):
        assert (
            chain_grade_from_hukum("إسناد شديد الضعف فيه فلان وهو منكر الحديث") == ChainGrade.MAWDU
        )
        assert chain_grade_from_hukum("إسناد فيه متهم بالوضع وهو فلان") == ChainGrade.MAWDU
        assert chain_grade_from_hukum("إسناد ضعيف فيه فلان وهو متروك الحديث") == ChainGrade.MAWDU

    def test_unclassified(self):
        assert chain_grade_from_hukum(None) is None
        assert chain_grade_from_hukum("") is None
        assert chain_grade_from_hukum("نص غير مصنف") is None


class TestQawlClassification:
    def test_reliable(self):
        assert grade_from_qawl("ثقة") == NarratorGrade.RELIABLE
        assert grade_from_qawl("ذكره في الثقات") == NarratorGrade.RELIABLE
        assert grade_from_qawl("له صحبة") == NarratorGrade.RELIABLE

    def test_acceptable(self):
        assert grade_from_qawl("صدوق") == NarratorGrade.ACCEPTABLE
        assert grade_from_qawl("لا بأس به") == NarratorGrade.ACCEPTABLE

    def test_weak(self):
        assert grade_from_qawl("ضعيف") == NarratorGrade.WEAK
        assert grade_from_qawl("ذكره في الضعفاء") == NarratorGrade.WEAK

    def test_rejected(self):
        assert grade_from_qawl("متروك الحديث") == NarratorGrade.REJECTED
        assert grade_from_qawl("كذاب") == NarratorGrade.REJECTED
        assert grade_from_qawl("ليس بثقة") == NarratorGrade.REJECTED

    def test_ungraded(self):
        assert grade_from_qawl("مجهول") == NarratorGrade.UNGRADED

    def test_biographical_is_none(self):
        assert grade_from_qawl("ذكره في تاريخ دمشق") is None
        assert grade_from_qawl(None) is None

    def test_thiqah_wins_over_saduq(self):
        assert grade_from_qawl("ثقة صدوق") == NarratorGrade.RELIABLE
