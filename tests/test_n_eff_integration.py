"""Tests for the lineage-aware Kish discount (3.0.5 n_eff integration).

Locks the discount from the phi study into ``CappedCorroborationPolicy`` so it
cannot regress silently. The measured same-family phi_bar is 0.6172 (the
arithmetic mean of the 4 ``same_family:true`` pairs in
``experiments/correlated_errors/stats.json``: 0.4888, 0.7306, 0.5595, 0.6898);
it is the documented opt-in example value, NOT the default (default phi = 0.0).
"""

import json
from pathlib import Path

import pytest

from isnad.core.corroboration import (
    CappedCorroborationPolicy,
    CorroborationEngine,
    IndependenceAssessment,
    SharedLineageDetector,
    evaluate_corroboration,
)
from isnad.types import ChainGrade

PHI_MEASURED = 0.6172


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
        for k in (2, 3, 4, 8):
            assert _strength(k, PHI_MEASURED) == pytest.approx(_n_eff(PHI_MEASURED, k))

    def test_policy_kish_scale_matches_identity(self) -> None:
        """The per-chain scale locks the base-inclusive denominator 1/(1+m*phi),
        NOT the pre-fix 1/(1+(m-1)*phi) (3.0.5 brutal-panel finding M2)."""
        pol = CappedCorroborationPolicy(phi_shared_lineage=PHI_MEASURED)
        for m in (1, 2, 3, 4, 8):
            assert pol.kish_scale(m) == pytest.approx(1.0 / (1.0 + m * PHI_MEASURED))

    def test_kish_scale_identity_for_zero_or_no_shared(self) -> None:
        """m_sh <= 0 or phi == 0 -> no discount; m_sh == 1 IS discounted (M2)."""
        pol = CappedCorroborationPolicy(phi_shared_lineage=PHI_MEASURED)
        assert pol.kish_scale(0) == 1.0
        assert pol.kish_scale(1) == pytest.approx(1.0 / (1.0 + PHI_MEASURED))
        assert CappedCorroborationPolicy(phi_shared_lineage=0.0).kish_scale(4) == 1.0

    def test_default_phi_is_zero_opt_in(self) -> None:
        """phi defaults to 0.0 (no discount unless the operator opts in)."""
        assert CappedCorroborationPolicy().phi_shared_lineage == 0.0


class TestSharedLineageDiscount:
    def test_shared_lineage_duplicate_contributes_less(self) -> None:
        """Two shared-lineage HASAN corroborators must not equal two disjoint ones."""
        pol = CappedCorroborationPolicy(phi_shared_lineage=PHI_MEASURED)
        base = ChainGrade.DAIF
        grades = [ChainGrade.HASAN, ChainGrade.HASAN]
        scores = [1.0, 1.0]

        full = pol.compute_corroborated_grade(base, grades, scores)
        discounted = pol.compute_corroborated_grade(
            base, grades, scores, shared_lineage_flags=[True, True]
        )

        assert full == ChainGrade.HASAN
        assert discounted == ChainGrade.DAIF

    def test_discount_is_monotone_in_phi(self) -> None:
        """Higher phi -> lower per-chain scale (stronger discount)."""
        low = CappedCorroborationPolicy(phi_shared_lineage=0.3)
        high = CappedCorroborationPolicy(phi_shared_lineage=0.9)
        assert high.kish_scale(3) < low.kish_scale(3)

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

    def test_two_shared_sahih_corroborators_no_upgrade_at_phi(self) -> None:
        """M2 repro: 2 shared-lineage SAHIH corroborators (score 0.6, prior 0)
        must NOT upgrade DAIF->HASAN at phi=0.6172, but must at phi=0.0."""
        base = ChainGrade.DAIF
        grades = [ChainGrade.SAHIH, ChainGrade.SAHIH]
        scores = [0.6, 0.6]
        flags = [True, True]
        priors = [0.0, 0.0]

        discounted = CappedCorroborationPolicy(
            phi_shared_lineage=PHI_MEASURED
        ).compute_corroborated_grade(
            base,
            grades,
            scores,
            shared_lineage_flags=flags,
            chain_blind_spot_priors=priors,
        )
        naive = CappedCorroborationPolicy(phi_shared_lineage=0.0).compute_corroborated_grade(
            base,
            grades,
            scores,
            shared_lineage_flags=flags,
            chain_blind_spot_priors=priors,
        )
        assert naive == ChainGrade.HASAN
        assert discounted == ChainGrade.DAIF


class TestDiscountNotExclude:
    """F1: soft shared-lineage chains are admitted (not excluded) and discounted."""

    def test_admits_corroboration_rule(self) -> None:
        pol = CappedCorroborationPolicy()
        # disjoint -> admitted
        assert pol.admits_corroboration(1.0, False) is True
        assert pol.admits_corroboration(0.8, False) is True
        # soft shared-lineage (shared family/source, score > 0) -> admitted
        assert pol.admits_corroboration(0.6, True) is True
        assert pol.admits_corroboration(0.7, True) is True
        assert pol.admits_corroboration(0.3, True) is True
        # hard identity (shared narrator IDs / doc hashes, score == 0) -> excluded
        assert pol.admits_corroboration(0.0, True) is False
        # unknown lineage (no shared signals, score 0.5) -> excluded
        assert pol.admits_corroboration(0.5, False) is False

    def test_four_shared_lineage_corroborators_flip_grade(self) -> None:
        """With 4 shared-family HASAN corroborators (score 0.6) the naive policy
        upgrades DAIF->HASAN but the phi-discounted policy does not."""
        base = ChainGrade.DAIF
        grades = [ChainGrade.HASAN] * 4
        scores = [0.6] * 4
        flags = [True] * 4

        naive = CappedCorroborationPolicy(phi_shared_lineage=0.0).compute_corroborated_grade(
            base, grades, scores, shared_lineage_flags=flags
        )
        discounted = CappedCorroborationPolicy(
            phi_shared_lineage=PHI_MEASURED
        ).compute_corroborated_grade(base, grades, scores, shared_lineage_flags=flags)

        # admission (score 0.6 < 0.8) is what makes the naive policy able to upgrade
        assert naive == ChainGrade.HASAN
        # the Kish discount pulls it back below the 2.0 weight threshold
        assert discounted == ChainGrade.DAIF

    def test_end_to_end_shared_family_admitted_and_discounted(self) -> None:
        """Through the real detector: a shared-family pair (score 0.6) is admitted
        and its effective witness weight is discounted."""
        meta = {
            "n:A": {"model_family": "gpt-4"},
            "n:B": {"model_family": "gpt-4"},
            "n:C": {"model_family": "gpt-4"},
        }
        chains = [
            {"grade": "hasan", "narrators": ["n:B"]},
            {"grade": "hasan", "narrators": ["n:C"]},
        ]
        discounted = CorroborationEngine(
            policy=CappedCorroborationPolicy(phi_shared_lineage=PHI_MEASURED)
        ).evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["n:A"],
            corroborating_chains=chains,
            narrator_metadata=meta,
        )
        no_discount = CorroborationEngine(
            policy=CappedCorroborationPolicy(phi_shared_lineage=0.0)
        ).evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["n:A"],
            corroborating_chains=chains,
            narrator_metadata=meta,
        )

        # previously these shared-family chains (score 0.6) were excluded outright
        assert discounted.independent_chains == 2
        assert no_discount.independent_chains == 2
        # the discount reduces the effective witness weight
        assert discounted.effective_witnesses < no_discount.effective_witnesses

    def test_engine_decision_flips_with_phi(self) -> None:
        """M3: through the engine, 4 shared-family HASAN corroborators (score 0.6)
        upgrade DAIF->HASAN at phi=0.0 but stay DAIF at phi=0.6172."""
        meta = {
            "n:A": {"model_family": "gpt-4"},
            "n:B": {"model_family": "gpt-4"},
            "n:C": {"model_family": "gpt-4"},
            "n:D": {"model_family": "gpt-4"},
            "n:E": {"model_family": "gpt-4"},
        }
        chains = [
            {"grade": "hasan", "narrators": ["n:B"]},
            {"grade": "hasan", "narrators": ["n:C"]},
            {"grade": "hasan", "narrators": ["n:D"]},
            {"grade": "hasan", "narrators": ["n:E"]},
        ]
        discounted = CorroborationEngine(
            policy=CappedCorroborationPolicy(phi_shared_lineage=PHI_MEASURED)
        ).evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["n:A"],
            corroborating_chains=chains,
            narrator_metadata=meta,
        )
        no_discount = CorroborationEngine(
            policy=CappedCorroborationPolicy(phi_shared_lineage=0.0)
        ).evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["n:A"],
            corroborating_chains=chains,
            narrator_metadata=meta,
        )
        assert no_discount.upgraded_grade == ChainGrade.HASAN
        assert discounted.upgraded_grade == ChainGrade.DAIF


class _OldProtocolPolicy:
    """Minimal third-party policy written to the pre-3.0.5 protocol."""

    def compute_corroborated_grade(
        self,
        base_grade: ChainGrade,
        corroborating_chains: list[ChainGrade],
        independence_scores: list[float],
        *,
        chain_blind_spot_priors: list[float] | None = None,
    ) -> ChainGrade:
        return base_grade


class TestThirdPartyCompat:
    """F4: the shared_lineage_flags kwarg is guarded at the call sites."""

    def test_old_protocol_policy_still_works(self) -> None:
        result = evaluate_corroboration(
            base_grade=ChainGrade.DAIF,
            corroborating_chain_grades=[ChainGrade.HASAN],
            base_narrators=["n:A"],
            corroborating_narrators=[["n:B"]],
            narrator_metadata={
                "n:A": {"model_family": "gpt-4"},
                "n:B": {"model_family": "gpt-4"},
            },
            policy=_OldProtocolPolicy(),
        )
        assert result == ChainGrade.DAIF

    def test_old_protocol_policy_through_engine_does_not_raise(self) -> None:
        """M1: a pre-3.0.5 policy passed to CorroborationEngine degrades to the
        old behavior (score-gate admission, flat prior) without AttributeError."""
        engine = CorroborationEngine(policy=_OldProtocolPolicy())
        result = engine.evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["n:A"],
            corroborating_chains=[{"grade": "hasan", "narrators": ["n:B"]}],
            narrator_metadata={
                "n:A": {"model_family": "gpt-4"},
                "n:B": {"model_family": "claude-3"},
            },
        )
        assert result.base_grade == ChainGrade.DAIF
        assert result.upgraded_grade == ChainGrade.DAIF


class TestInvariantsStillHold:
    def test_mawdu_never_upgraded_with_discount(self) -> None:
        pol = CappedCorroborationPolicy(phi_shared_lineage=PHI_MEASURED)
        result = pol.compute_corroborated_grade(
            ChainGrade.MAWDU, [ChainGrade.HASAN], [1.0], shared_lineage_flags=[True]
        )
        assert result == ChainGrade.MAWDU

    def test_hasan_cannot_reach_sahih_with_discount(self) -> None:
        pol = CappedCorroborationPolicy(phi_shared_lineage=PHI_MEASURED)
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


class TestPhiConstant:
    def test_example_value_is_the_four_pair_mean(self) -> None:
        """F3: the documented opt-in example is the arithmetic mean of the 4
        same_family:true pairs in the committed stats.json."""
        stats_path = (
            Path(__file__).resolve().parents[1] / "experiments" / "correlated_errors" / "stats.json"
        )
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        same_family = [p["phi"] for p in stats["pairs"] if p.get("same_family") is True]
        assert len(same_family) == 4
        assert sum(same_family) / len(same_family) == pytest.approx(PHI_MEASURED, abs=1e-4)
