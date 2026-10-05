"""Tests for the lineage-aware Kish discount (3.0.5 n_eff integration).

Locks the discount from the phi study (same-family phi_bar = 0.6214) into
``CappedCorroborationPolicy`` so it cannot regress silently.
"""

import pytest

from isnad.core.corroboration import (
    CappedCorroborationPolicy,
    IndependenceAssessment,
)
from isnad.types import ChainGrade


def _n_eff(phi_bar: float, k: int) -> float:
    """Kish effective sample size n_eff = k / (1 + (k-1)*phi)."""
    if k <= 1:
        return float(k)
    denom = 1 + (k - 1) * phi_bar
    return k / denom if denom > 0 else float("inf")


def _strength(m: int, phi_bar: float) -> float:
    """Kish exact form for m routes with pairwise correlation phi."""
    if m <= 1:
        return float(m)
    denom = 1 + (m - 1) * phi_bar
    return m / denom if denom > 0 else float(m)


class TestKishIdentity:
    def test_strength_m_k_equals_n_eff(self) -> None:
        """strength(m=k, phi) == n_eff(phi, k) (ported from experiment_bc)."""
        phi = 0.6214
        for k in (2, 3, 4, 8):
            assert _strength(k, phi) == pytest.approx(_n_eff(phi, k))

    def test_policy_kish_scale_matches_identity(self) -> None:
        """The policy's per-chain scale sums to the Kish total."""
        pol = CappedCorroborationPolicy()
        m = 2
        # total effective count of m shared-lineage chains = m * kish_scale(m)
        assert m * pol._kish_scale(m) == pytest.approx(_strength(m, pol.phi_shared_lineage))

    def test_kish_scale_identity_for_single_or_zero_phi(self) -> None:
        """m_sh <= 1 or phi == 0 -> no discount."""
        assert CappedCorroborationPolicy(phi_shared_lineage=0.6214)._kish_scale(0) == 1.0
        assert CappedCorroborationPolicy(phi_shared_lineage=0.6214)._kish_scale(1) == 1.0
        assert CappedCorroborationPolicy(phi_shared_lineage=0.0)._kish_scale(4) == 1.0


class TestSharedLineageDiscount:
    def test_shared_lineage_duplicate_contributes_less(self) -> None:
        """Two shared-lineage HASAN corroborators must not equal two disjoint ones."""
        pol = CappedCorroborationPolicy()
        base = ChainGrade.DAIF
        grades = [ChainGrade.HASAN, ChainGrade.HASAN]
        scores = [1.0, 1.0]

        full = pol.compute_corroborated_grade(base, grades, scores)
        discounted = pol.compute_corroborated_grade(
            base, grades, scores, shared_lineage_flags=[True, True]
        )

        # Disjoint duplicates clear the 2.0 weight bar -> upgrade.
        assert full == ChainGrade.HASAN
        # Shared-lineage duplicates are discounted below the bar -> no upgrade.
        assert discounted == ChainGrade.DAIF

    def test_discount_is_monotone_in_phi(self) -> None:
        """Higher phi -> lower per-chain scale (stronger discount)."""
        low = CappedCorroborationPolicy(phi_shared_lineage=0.3)
        high = CappedCorroborationPolicy(phi_shared_lineage=0.9)
        assert high._kish_scale(3) < low._kish_scale(3)

    def test_phi_zero_is_backward_compatible(self) -> None:
        """phi = 0 -> shared-lineage flags change nothing."""
        pol = CappedCorroborationPolicy(phi_shared_lineage=0.0)
        base = ChainGrade.DAIF
        grades = [ChainGrade.HASAN, ChainGrade.HASAN]
        scores = [1.0, 1.0]
        with_flags = pol.compute_corroborated_grade(
            base, grades, scores, shared_lineage_flags=[True, True]
        )
        without_flags = pol.compute_corroborated_grade(base, grades, scores)
        assert with_flags == without_flags


class TestInvariantsStillHold:
    def test_mawdu_never_upgraded_with_discount(self) -> None:
        pol = CappedCorroborationPolicy()
        result = pol.compute_corroborated_grade(
            ChainGrade.MAWDU, [ChainGrade.HASAN], [1.0], shared_lineage_flags=[True]
        )
        assert result == ChainGrade.MAWDU

    def test_hasan_cannot_reach_sahih_with_discount(self) -> None:
        pol = CappedCorroborationPolicy()
        result = pol.compute_corroborated_grade(
            ChainGrade.HASAN,
            [ChainGrade.HASAN, ChainGrade.HASAN, ChainGrade.HASAN],
            [1.0, 1.0, 1.0],
            shared_lineage_flags=[True, True, True],
        )
        assert result != ChainGrade.SAHIH


class TestSharedLineageFlag:
    def test_has_shared_lineage_true_when_signals_present(self) -> None:
        a = IndependenceAssessment(0.6, ("shared model family: gpt-4",))
        assert a.has_shared_lineage is True

    def test_has_shared_lineage_false_when_no_signals(self) -> None:
        a = IndependenceAssessment(1.0, ())
        assert a.has_shared_lineage is False
