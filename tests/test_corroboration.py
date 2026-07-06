"""Tests for corroboration.py — independent-chain upgrade + correlation detection.

Verifies paper §4.3 commitments:
- Corroboration upgrades are capped.
- Minimum-grade gate: weak chains cannot manufacture trust.
- Correlation discount: shared model family / upstream source detected.
- Naive set-disjointness is wrong — correlation detection required.
"""

import pytest

from isnad.corroboration import (
    CappedCorroborationPolicy,
    SharedLineageDetector,
    evaluate_corroboration,
)
from isnad.types import ChainGrade


class TestSharedLineageDetector:
    """Correlation detection: shared model family / upstream source (madār)."""

    def test_disjoint_narrators_with_no_metadata_are_independent(self) -> None:
        det = SharedLineageDetector()
        score = det.compute_independence_score(
            ["narrator-A", "narrator-B"],
            ["narrator-C", "narrator-D"],
            {},
        )
        assert score == 1.0
        assert det.are_independent(["narrator-A"], ["narrator-B"], {})

    def test_shared_narrator_ids_are_correlated(self) -> None:
        """Naive set-disjointness is wrong — but shared IDs ARE correlated."""
        det = SharedLineageDetector()
        score = det.compute_independence_score(
            ["narrator-A", "narrator-B"],
            ["narrator-B", "narrator-C"],
            {},
        )
        assert score == 0.0
        assert not det.are_independent(
            ["narrator-A", "narrator-B"],
            ["narrator-B", "narrator-C"],
            {},
        )

    def test_shared_model_family_reduces_independence(self) -> None:
        """Same model family → correlated (the madār problem)."""
        det = SharedLineageDetector()
        metadata = {
            "model-1": {"model_family": "gpt-4-family"},
            "model-2": {"model_family": "gpt-4-family"},
        }
        score = det.compute_independence_score(
            ["model-1"],
            ["model-2"],
            metadata,
        )
        assert score < 1.0  # penalty applied
        assert score > 0.0  # not fully correlated
        # Should be 1.0 - 0.4 = 0.6
        assert score == 0.6

    def test_shared_upstream_source_reduces_independence(self) -> None:
        """Shared upstream source → correlated."""
        det = SharedLineageDetector()
        metadata = {
            "scraper-A": {"upstream_source": "wikipedia.org"},
            "scraper-B": {"upstream_source": "wikipedia.org"},
        }
        score = det.compute_independence_score(
            ["scraper-A"],
            ["scraper-B"],
            metadata,
        )
        assert score == 0.7  # 1.0 - 0.3

    def test_both_shared_is_heavily_penalized(self) -> None:
        det = SharedLineageDetector()
        metadata = {
            "agent-1": {"model_family": "claude", "upstream_source": "arxiv.org"},
            "agent-2": {"model_family": "claude", "upstream_source": "arxiv.org"},
        }
        score = det.compute_independence_score(
            ["agent-1"],
            ["agent-2"],
            metadata,
        )
        assert score == pytest.approx(0.3)  # 1.0 - 0.4 - 0.3

    def test_different_lineages_are_independent(self) -> None:
        det = SharedLineageDetector()
        metadata = {
            "agent-1": {"model_family": "claude"},
            "agent-2": {"model_family": "gemini"},
        }
        score = det.compute_independence_score(
            ["agent-1"],
            ["agent-2"],
            metadata,
        )
        assert score == 1.0  # different families → independent


class TestCappedCorroborationPolicy:
    """Corroboration: capped, minimum-gated, correlation-discounted."""

    def test_no_corroborating_chains_returns_base(self) -> None:
        pol = CappedCorroborationPolicy()
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [],
            [],
        )
        assert result == ChainGrade.DAIF

    def test_mawdu_cannot_be_upgraded(self) -> None:
        pol = CappedCorroborationPolicy()
        result = pol.compute_corroborated_grade(
            ChainGrade.MAWDU,
            [ChainGrade.SAHIH, ChainGrade.SAHIH],
            [1.0, 1.0],
        )
        assert result == ChainGrade.MAWDU  # unrecoverable

    def test_corrupt_chains_cannot_manufacture_trust(self) -> None:
        """Minimum-grade gate: all weak chains → no upgrade."""
        pol = CappedCorroborationPolicy()
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.DAIF, ChainGrade.DAIF, ChainGrade.DAIF],
            [1.0, 1.0, 1.0],
        )
        assert result == ChainGrade.DAIF  # gate not passed

    def test_daif_upgraded_to_hasan_with_good_corroboration(self) -> None:
        pol = CappedCorroborationPolicy()
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.HASAN],
            [1.0, 1.0],
        )
        assert result == ChainGrade.HASAN

    def test_hasan_cannot_reach_sahih_via_corroboration(self) -> None:
        """Upgrade is capped: corroboration cannot reach SAHIH (paper §4.3)."""
        pol = CappedCorroborationPolicy()
        result = pol.compute_corroborated_grade(
            ChainGrade.HASAN,
            [ChainGrade.SAHIH, ChainGrade.SAHIH, ChainGrade.SAHIH],
            [1.0, 1.0, 1.0],
        )
        assert result == ChainGrade.HASAN  # capped — cannot reach SAHIH

    def test_correlated_chains_are_discounted(self) -> None:
        """Correlated chains contribute less weight."""
        pol = CappedCorroborationPolicy()
        # Two chains, both correlated (score 0.5) → effective count < 2
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.HASAN],
            [0.5, 0.5],  # correlated
        )
        # Effective count = 1.0, below threshold of 2 → no upgrade
        assert result == ChainGrade.DAIF

    def test_mixed_independent_and_correlated(self) -> None:
        pol = CappedCorroborationPolicy()
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.HASAN, ChainGrade.DAIF],
            [1.0, 0.5, 1.0],  # middle one correlated
        )
        # DAIF chains are excluded from effective count (only HASAN+ help)
        # Effective = 1.0 (HASAN independent) + 0.5 (HASAN correlated) = 1.5 < 2
        assert result == ChainGrade.DAIF


class TestEvaluateCorroborationIntegration:
    """End-to-end corroboration evaluation with correlation detection."""

    def test_independent_chains_upgrade_daif(self) -> None:
        result = evaluate_corroboration(
            base_grade=ChainGrade.DAIF,
            corroborating_chain_grades=[ChainGrade.HASAN, ChainGrade.HASAN],
            base_narrators=["narr-A", "narr-B"],
            corroborating_narrators=[["narr-C"], ["narr-D", "narr-E"]],
            narrator_metadata={},
        )
        assert result == ChainGrade.HASAN

    def test_correlated_chains_dont_upgrade(self) -> None:
        result = evaluate_corroboration(
            base_grade=ChainGrade.DAIF,
            corroborating_chain_grades=[ChainGrade.HASAN, ChainGrade.HASAN],
            base_narrators=["model-gpt4"],
            corroborating_narrators=[["model-gpt4o"], ["model-gpt4-turbo"]],
            narrator_metadata={
                "model-gpt4": {"model_family": "gpt-4"},
                "model-gpt4o": {"model_family": "gpt-4"},
                "model-gpt4-turbo": {"model_family": "gpt-4"},
            },
        )
        # All share gpt-4 family → heavily penalized → no upgrade
        assert result == ChainGrade.DAIF
