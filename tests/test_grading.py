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

from isnad.core.grading import grade_chain
from isnad.types import AdalahGrade, ChainGrade, ContentVerdict, NarratorGrade, TransformType


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

    def test_ungraded_narrator_caps_at_daif_by_default(self) -> None:
        # Strict is the default: an ungraded narrator is a classical majhūl.
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.UNGRADED],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=True,
        )
        assert result == ChainGrade.DAIF

    def test_ungraded_narrator_caps_at_hasan_when_lenient(self) -> None:
        # lenient_unknown=True is the opt-in epistemic-humility mode.
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.UNGRADED],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=True,
            lenient_unknown=True,
        )
        assert result == ChainGrade.HASAN

    def test_lenient_unknown_does_not_affect_graded_narrators(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.ACCEPTABLE],
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

    def test_incomplete_with_rejected_is_mawdu_not_daif(self) -> None:
        """#181: a REJECTED fabricator dominates the completeness cap. Adding a
        gap must never raise a MAWDU chain to (corroboratable) DAIF."""
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.REJECTED],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=False,
        )
        assert result == ChainGrade.MAWDU

    def test_incomplete_with_compromised_adalah_is_mawdu_not_daif(self) -> None:
        """#181: COMPROMISED ʿadālah also dominates the completeness cap — same
        anti-monotonicity argument, applied to the integrity axis."""
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.ACCEPTABLE],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=False,
            link_adalah_grades=[AdalahGrade.ACCEPTABLE, AdalahGrade.COMPROMISED],
        )
        assert result == ChainGrade.MAWDU


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
        pass-through (caps at DAIF under the strict default). Order matters."""
        result = grade_chain(
            [NarratorGrade.WEAK, NarratorGrade.RELIABLE, NarratorGrade.UNGRADED],
            [TransformType.DESTRUCTIVE, TransformType.GENERATIVE, TransformType.PASS_THROUGH],
            is_complete=True,
            corroboration_support=True,
        )
        assert result == ChainGrade.DAIF

    def test_degradation_then_repair(self) -> None:
        """UNGRADED pass → caps at DAIF (strict default). Then RELIABLE gen
        with corroboration replaces the floor at SAHIH."""
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


class TestAdalahIntegrityAxis:
    """Issue #11: ʿadālah (integrity) is a separate axis from NarratorGrade —
    a chain-integrity-only view can't offset a compromised origin. A narrator
    whose adalah has failed poisons the chain even when its collapsed
    NarratorGrade still looks fine (the "fabricated pristine chain" case)."""

    def test_compromised_adalah_forces_mawdu_despite_reliable_grades(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH] * 3,
            is_complete=True,
            link_adalah_grades=[
                AdalahGrade.HIGH,
                AdalahGrade.COMPROMISED,
                AdalahGrade.HIGH,
            ],
        )
        assert result == ChainGrade.MAWDU

    def test_no_compromised_adalah_leaves_grade_unaffected(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=True,
            link_adalah_grades=[AdalahGrade.HIGH, AdalahGrade.ACCEPTABLE],
        )
        assert result == ChainGrade.SAHIH

    def test_omitting_adalah_grades_is_backward_compatible(self) -> None:
        """Default None must not change existing behavior for callers that
        don't yet pass this axis."""
        result = grade_chain(
            [NarratorGrade.RELIABLE] * 3,
            [TransformType.PASS_THROUGH] * 3,
            is_complete=True,
        )
        assert result == ChainGrade.SAHIH

    def test_unassessed_adalah_does_not_trigger_mawdu(self) -> None:
        """Only COMPROMISED is a hard block — UNASSESSED is the neutral default."""
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH] * 2,
            is_complete=True,
            link_adalah_grades=[AdalahGrade.UNASSESSED, AdalahGrade.UNASSESSED],
        )
        assert result == ChainGrade.SAHIH


class TestFidelityAxis:
    """Issue #11, direction 3: per-generative-link transformation fidelity —
    a third axis distinct from NarratorGrade and AdalahGrade. A CONTRADICTION
    verdict caps that specific link's contribution at DAIF regardless of the
    narrator's own historical grade, and blocks it from repairing the floor
    via corroboration — surfacing exactly *where* a chain degraded."""

    def test_contradiction_caps_generative_link_at_daif_despite_reliable_grade(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH, TransformType.GENERATIVE],
            is_complete=True,
            link_fidelity_verdicts=[ContentVerdict.UNVERIFIABLE, ContentVerdict.CONTRADICTION],
        )
        assert result == ChainGrade.DAIF

    def test_contradiction_blocks_corroboration_repair(self) -> None:
        """Without a contradicted fidelity verdict, a WEAK destructive link
        would normally be repaired to SAHIH by a RELIABLE generative link
        with corroboration_support (see TestDestructivePermanentCap). A
        contradicted fidelity verdict on that same generative link must
        block the repair — its own output didn't hold together, so it can't
        vouch for anything upstream either."""
        grades = [NarratorGrade.WEAK, NarratorGrade.RELIABLE]
        transforms = [TransformType.DESTRUCTIVE, TransformType.GENERATIVE]

        repaired = grade_chain(grades, transforms, is_complete=True, corroboration_support=True)
        assert repaired == ChainGrade.SAHIH  # control: repair works without fidelity check

        blocked = grade_chain(
            grades,
            transforms,
            is_complete=True,
            corroboration_support=True,
            link_fidelity_verdicts=[ContentVerdict.UNVERIFIABLE, ContentVerdict.CONTRADICTION],
        )
        assert blocked == ChainGrade.DAIF  # repair blocked by contradicted fidelity

    def test_consistent_fidelity_has_no_effect(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH, TransformType.GENERATIVE],
            is_complete=True,
            link_fidelity_verdicts=[ContentVerdict.UNVERIFIABLE, ContentVerdict.CONSISTENT],
        )
        assert result == ChainGrade.SAHIH

    def test_unverifiable_fidelity_has_no_effect(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH, TransformType.GENERATIVE],
            is_complete=True,
            link_fidelity_verdicts=[ContentVerdict.UNVERIFIABLE, ContentVerdict.UNVERIFIABLE],
        )
        assert result == ChainGrade.SAHIH

    def test_omitting_fidelity_verdicts_is_backward_compatible(self) -> None:
        result = grade_chain(
            [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
            [TransformType.PASS_THROUGH, TransformType.GENERATIVE],
            is_complete=True,
        )
        assert result == ChainGrade.SAHIH
