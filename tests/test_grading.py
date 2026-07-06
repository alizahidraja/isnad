"""Tests for grading.py — weakest-link chain evaluation.

Verifies paper §4.1 commitments with tests that exercise the actual
chain-walking algorithm, not just the minimum-across-all-links fallback.

Key properties tested:
- Destructive weak link creates a permanent floor (paper: strict minimum).
- Generative RELIABLE link WITH corroboration REPAIRS a destructive weak link
  (paper: can raise the floor up to its own grade).
- Generative link WITHOUT corroboration cannot repair (paper: only when
  corroboration supports it).
- Generative link with WEAK grade cannot repair even with corroboration
  (paper: can only raise up to its own grade, and WEAK=DAIF doesn't help).
- Incomplete chain → DAIF regardless of narrator quality (ittiṣāl).
- corroboration_support flag actually changes outcomes (not dead code).
"""

from isnad.grading import grade_chain
from isnad.types import ChainGrade, NarratorGrade, TransformType


class TestWeakestLink:
    """The weakest-link rule: basic minimum across pass-through links."""

    def test_all_reliable_gives_sahih(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE] * 3,
            [TransformType.PASS_THROUGH] * 3,
            is_complete=True,
        )
        assert result == ChainGrade.SAHIH

    def test_one_weak_makes_daif(self) -> None:
        """Weakest link caps the chain — paper §4.1 principle 3."""
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.WEAK, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH] * 3,
            is_complete=True,
        )
        assert result == ChainGrade.DAIF

    def test_one_rejected_makes_mawdu(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.REJECTED],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=True,
        )
        assert result == ChainGrade.MAWDU

    def test_ungraded_narrator_caps_at_hasan(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.UNGRADED],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=True,
        )
        assert result == ChainGrade.HASAN

    def test_empty_chain_returns_daif(self) -> None:
        result = grade_chain([], [], is_complete=False)
        assert result == ChainGrade.DAIF


class TestCompletenessCap:
    """Completeness (ittiṣāl) is an epistemic property — paper §4.1."""

    def test_incomplete_chain_capped_at_daif(self) -> None:
        """Even with all RELIABLE narrators, gap → DAIF."""
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=False,
        )
        assert result == ChainGrade.DAIF

    def test_incomplete_with_weak_still_daif(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.WEAK],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=False,
        )
        assert result == ChainGrade.DAIF


class TestDestructivePermanentCap:
    """Destructive transforms create a permanent floor (paper §4.1)."""

    def test_destructive_weak_permanent_cap_without_corroboration(self) -> None:
        """WEAK destructive link → DAIF floor. RELIABLE generative cannot
        repair WITHOUT corroboration."""
        result = grade_chain(
            [NarratorGrade.WEAK, NarratorGrade.RELIABLE],
            [TransformType.DESTRUCTIVE, TransformType.GENERATIVE],
            is_complete=True,
            corroboration_support=False,
        )
        assert result == ChainGrade.DAIF
        # Verify: changing corroboration_support DOES change the result
        # (proving the flag is not dead code — see next test)

    def test_destructive_weak_can_be_repaired_with_corroboration(self) -> None:
        """WEAK destructive → DAIF floor. RELIABLE generative WITH
        corroboration REPAIRS: floor becomes SAHIH (own grade)."""
        result = grade_chain(
            [NarratorGrade.WEAK, NarratorGrade.RELIABLE],
            [TransformType.DESTRUCTIVE, TransformType.GENERATIVE],
            is_complete=True,
            corroboration_support=True,
        )
        assert result == ChainGrade.SAHIH

    def test_destructive_and_generative_switch_corroboration_changes_result(self) -> None:
        """corroboration_support genuinely changes the output — not dead code."""
        grades = [NarratorGrade.WEAK, NarratorGrade.RELIABLE]
        transforms = [TransformType.DESTRUCTIVE, TransformType.GENERATIVE]

        without = grade_chain(grades, transforms, is_complete=True, corroboration_support=False)
        with_c = grade_chain(grades, transforms, is_complete=True, corroboration_support=True)

        assert without != with_c, f"corroboration_support flag is dead! Both returned {without}"
        assert without == ChainGrade.DAIF
        assert with_c == ChainGrade.SAHIH


class TestGenerativeCannotExceedOwnGrade:
    """Generative link can never raise the floor above its own grade (paper §4.1)."""

    def test_generative_acceptable_cannot_reach_sahih(self) -> None:
        """ACCEPTABLE generative = HASAN ceiling. Even with corroboration,
        the floor cannot exceed HASAN."""
        # Start with a WEAK destructive (DAIF floor), then ACCEPTABLE generative.
        # ACCEPTABLE → HASAN.  Floor should become HASAN, not SAHIH.
        result = grade_chain(
            [NarratorGrade.WEAK, NarratorGrade.ACCEPTABLE],
            [TransformType.DESTRUCTIVE, TransformType.GENERATIVE],
            is_complete=True,
            corroboration_support=True,
        )
        assert result == ChainGrade.HASAN

    def test_generative_weak_cannot_repair_even_with_corroboration(self) -> None:
        """WEAK generative's own grade = DAIF. It cannot repair ANYTHING."""
        result = grade_chain(
            [NarratorGrade.ACCEPTABLE, NarratorGrade.WEAK],
            [TransformType.DESTRUCTIVE, TransformType.GENERATIVE],
            is_complete=True,
            corroboration_support=True,
        )
        assert result == ChainGrade.DAIF


class TestGenerativeCanAlwaysLower:
    """Generative links can always lower the floor (paper §4.1)."""

    def test_reliable_generative_lowers_floor_to_own_grade(self) -> None:
        """Even with corroboration, a RELIABLE generative after all-RELIABLE
        chain sets floor to SAHIH (its own grade) — no harm here."""
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH, TransformType.GENERATIVE],
            is_complete=True,
            corroboration_support=True,
        )
        assert result == ChainGrade.SAHIH

    def test_acceptable_generative_lowers_reliable_chain(self) -> None:
        """RELIABLE chain → ACCEPTABLE generative (without corroboration):
        floor drops to HASAN. Generative can always lower."""
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.ACCEPTABLE],
            [TransformType.PASS_THROUGH, TransformType.GENERATIVE],
            is_complete=True,
            corroboration_support=False,
        )
        assert result == ChainGrade.HASAN


class TestChainWalkingOrder:
    """Chain order matters: walking left-to-right through the transmission."""

    def test_repair_then_degradation(self) -> None:
        """WEAK destructive → RELIABLE gen (repairs to SAHIH) → UNGRADED
        pass-through (caps at HASAN). Order matters."""
        result = grade_chain(
            [NarratorGrade.WEAK, NarratorGrade.RELIABLE, NarratorGrade.UNGRADED],
            [TransformType.DESTRUCTIVE, TransformType.GENERATIVE, TransformType.PASS_THROUGH],
            is_complete=True,
            corroboration_support=True,
        )
        assert result == ChainGrade.HASAN

    def test_degradation_then_repair(self) -> None:
        """UNGRADED pass → caps at HASAN. Then RELIABLE gen with corr
        replaces floor at SAHIH."""
        result = grade_chain(
            [NarratorGrade.UNGRADED, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH, TransformType.GENERATIVE],
            is_complete=True,
            corroboration_support=True,
        )
        assert result == ChainGrade.SAHIH

    def test_all_reliable_always_sahih(self) -> None:
        """All RELIABLE links → SAHIH regardless of transform types."""
        result = grade_chain(
            [NarratorGrade.RELIABLE] * 3,
            [TransformType.DESTRUCTIVE, TransformType.GENERATIVE, TransformType.PASS_THROUGH],
            is_complete=True,
        )
        assert result == ChainGrade.SAHIH
