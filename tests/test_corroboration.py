"""Tests for corroboration.py — independent-chain upgrade + correlation detection.

Verifies paper §4.3 commitments:
- Corroboration upgrades are capped.
- Minimum-grade gate: weak chains cannot manufacture trust.
- Correlation discount: shared model family / upstream source detected.
- Naive set-disjointness is wrong — correlation detection required.
"""

import pytest

from isnad.core.corroboration import (
    CappedCorroborationPolicy,
    CorroborationEngine,
    SharedLineageDetector,
    evaluate_corroboration,
)
from isnad.types import ChainGrade


class TestSharedLineageDetector:
    """Correlation detection: shared model family / upstream source (madār)."""

    def test_no_metadata_is_unknown_lineage_not_full_independence(self) -> None:
        """No lineage metadata → independence is UNKNOWN, not assumed (issue #54).

        Disjoint narrator IDs alone do not demonstrate independence — two
        distinct IDs can still share a corpus or model. Absent lineage evidence
        the score is the below-gate UNKNOWN_LINEAGE_SCORE, and the chains are not
        treated as independent. (Previously this returned 1.0.)
        """
        det = SharedLineageDetector()
        score = det.compute_independence_score(
            ["narrator-A", "narrator-B"],
            ["narrator-C", "narrator-D"],
            {},
        )
        assert score == SharedLineageDetector.UNKNOWN_LINEAGE_SCORE
        assert score < 1.0
        assert not det.are_independent(["narrator-A"], ["narrator-B"], {})

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

    def test_detect_returns_provenance_for_shared_family(self) -> None:
        """detect() reports *why* a chain was discounted (#125 step 3)."""
        det = SharedLineageDetector()
        metadata = {
            "model-1": {"model_family": "gpt-4-family"},
            "model-2": {"model_family": "gpt-4-family"},
        }
        a = det.detect(["model-1"], ["model-2"], metadata)
        assert a.score == 0.6
        assert any("gpt-4-family" in s for s in a.shared_signals)

    def test_detect_unknown_lineage_has_no_shared_signals(self) -> None:
        """Unknown lineage is a 'cannot tell' case, not a shared signal."""
        det = SharedLineageDetector()
        a = det.detect(["narrator-A"], ["narrator-B"], {})
        assert a.score == SharedLineageDetector.UNKNOWN_LINEAGE_SCORE
        assert a.shared_signals == ()  # empty — not a correlation finding

    def test_detect_shared_narrator_ids_has_provenance(self) -> None:
        """Shared narrator IDs produce a provenance entry naming the shared ID."""
        det = SharedLineageDetector()
        a = det.detect(["narrator-B"], ["narrator-B"], {})
        assert a.score == 0.0
        assert any("narrator-B" in s for s in a.shared_signals)

    def test_shared_document_hashes_are_hard_correlation(self) -> None:
        """Shared retrieved-document hash → hard correlation (the madār case).

        Two chains with different narrators and different model families that
        both retrieved the same document are one source, not two. This is the
        callback's SHARED_ANCESTRY_DETECTED signal, now in the core detector.
        """
        det = SharedLineageDetector()
        metadata = {
            "agent-1": {"model_family": "claude"},
            "agent-2": {"model_family": "gemini"},
        }
        score = det.compute_independence_score(
            ["agent-1"],
            ["agent-2"],
            metadata,
            chain_a_document_hashes={"doc-hash-123"},
            chain_b_document_hashes={"doc-hash-123"},
        )
        assert score == 0.0
        assert not det.are_independent(
            ["agent-1"],
            ["agent-2"],
            metadata,
            chain_a_document_hashes={"doc-hash-123"},
            chain_b_document_hashes={"doc-hash-123"},
        )

    def test_disjoint_document_hashes_do_not_raise_score(self) -> None:
        """Non-overlapping document hashes are NOT evidence of independence.

        Absent lineage metadata, disjoint doc hashes must fall through to the
        unknown-lineage score, never raise it.
        """
        det = SharedLineageDetector()
        score = det.compute_independence_score(
            ["agent-1"],
            ["agent-2"],
            {},
            chain_a_document_hashes={"doc-a"},
            chain_b_document_hashes={"doc-b"},
        )
        assert score == SharedLineageDetector.UNKNOWN_LINEAGE_SCORE

    def test_missing_document_hashes_skips_the_check(self) -> None:
        """None document hashes (not provided) → check skipped, backward compatible."""
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
        assert score == 1.0  # unchanged from pre-doc-hash behaviour

    def test_one_sided_document_hashes_is_no_information(self) -> None:
        """One side present + one absent → no overlap detectable, no penalty."""
        det = SharedLineageDetector()
        metadata = {
            "agent-1": {"model_family": "claude"},
            "agent-2": {"model_family": "gemini"},
        }
        score = det.compute_independence_score(
            ["agent-1"],
            ["agent-2"],
            metadata,
            chain_a_document_hashes={"doc-a"},
        )
        assert score == 1.0  # different families, and doc overlap unprovable


class TestSharedLineageDetectorDocHashesThroughEngine:
    """Document-hash correlation must flow through CorroborationEngine."""

    def test_engine_withholds_upgrade_on_shared_document_hashes(self) -> None:
        """Fixture-3 case: chains that read the same report must not corroborate."""
        engine = CorroborationEngine(min_independent_chains=1)
        # Base chain is DAIF, one corroborating chain is HASAN — would normally
        # upgrade to HASAN — but both retrieved the same document.
        result = engine.evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["source:A", "model:A"],
            corroborating_chains=[
                {
                    "grade": "hasan",
                    "narrators": ["source:B", "model:B"],
                    "document_hashes": ["shared-report"],
                }
            ],
            narrator_metadata={
                "source:A": {"model_family": None, "upstream_source": "noaa.gov"},
                "model:A": {"model_family": "fam-a", "upstream_source": "noaa.gov"},
                "source:B": {"model_family": None, "upstream_source": "noaa.gov"},
                "model:B": {"model_family": "fam-b", "upstream_source": "noaa.gov"},
            },
            base_document_hashes={"shared-report"},
        )
        assert result.upgraded is False
        assert result.independent_chains == 0

    def test_engine_upgrades_on_distinct_documents_and_lineage(self) -> None:
        """Distinct docs + distinct lineage → upgrade still fires."""
        engine = CorroborationEngine(min_independent_chains=1)
        result = engine.evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["source:A", "model:A"],
            corroborating_chains=[
                {
                    "grade": "hasan",
                    "narrators": ["source:B", "model:B"],
                    "document_hashes": ["report-b"],
                }
            ],
            narrator_metadata={
                "source:A": {"model_family": None, "upstream_source": "openstax.org"},
                "model:A": {"model_family": "fam-a", "upstream_source": "openstax.org"},
                "source:B": {"model_family": None, "upstream_source": "hyperphysics.org"},
                "model:B": {"model_family": "fam-b", "upstream_source": "hyperphysics.org"},
            },
            base_document_hashes={"report-a"},
        )
        assert result.upgraded is True


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
        """Default prior (0.20) tightens: HASAN+DAIF alone no longer clears the gate."""
        pol = CappedCorroborationPolicy()
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.HASAN, ChainGrade.DAIF],
            [1.0, 0.5, 1.0],  # second chain correlated (0.5 < 0.8)
        )
        # Independent: [HASAN(1.0), DAIF(1.0)] — but the tawātur discount
        # (prior 0.20) scales each by 0.80, so effective weight ≈ 1.76 < 2.0.
        assert result == ChainGrade.DAIF

    def test_disjointness_discount_reduces_effective_weight(self) -> None:
        """A partial independence score (0.85) earns less weight than 1.0 (#125).

        Isolates the #125 disjointness discount by pinning the #54 tawātur prior
        to 0 (the discount under test is the score, not the blind-spot prior).
        HASAN + DAIF at full independence gives effective weight 2.046 (upgrade);
        the same pair at 0.85 gives 1.817 (no upgrade).
        """
        pol = CappedCorroborationPolicy(shared_blind_spot_prior=0.0)
        full = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.DAIF],
            [1.0, 1.0],
        )
        discounted = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.DAIF],
            [0.85, 0.85],
        )
        assert full == ChainGrade.HASAN
        assert discounted == ChainGrade.DAIF  # discount pushed it below the gate

    def test_disjointness_discount_is_noop_at_full_independence(self) -> None:
        """All scores 1.0 AND prior 0 → behaviour identical to pre-discount."""
        pol = CappedCorroborationPolicy(shared_blind_spot_prior=0.0)
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.HASAN],
            [1.0, 1.0],
        )
        assert result == ChainGrade.HASAN

    def test_disjointness_discount_partial_score_still_counts(self) -> None:
        """A partial score above the gate contributes, just weighted down."""
        pol = CappedCorroborationPolicy(shared_blind_spot_prior=0.0)
        # 3 HASAN at 0.85 → effective 3.073 ≥ 2.0 → still upgrades, despite the
        # discount. Partial credit is not zero credit.
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.HASAN, ChainGrade.HASAN],
            [0.85, 0.85, 0.85],
        )
        assert result == ChainGrade.HASAN

    # ── The tawātur discount (#54) ────────────────────────────────────

    def test_tawatur_discount_requires_more_corroboration(self) -> None:
        """With the default blind-spot prior (0.20), a near-threshold case that
        used to upgrade no longer does — corroboration got harder, as honesty
        demands when independence is no longer assumed perfect (#54)."""
        pol = CappedCorroborationPolicy()  # default prior 0.20
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.DAIF],
            [1.0, 1.0],
        )
        assert result == ChainGrade.DAIF  # effective weight ≈ 1.76 < 2.0

    def test_tawatur_discount_zero_prior_is_backward_compatible(self) -> None:
        """shared_blind_spot_prior=0.0 reproduces the pre-#54 behaviour exactly."""
        pol = CappedCorroborationPolicy(shared_blind_spot_prior=0.0)
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.HASAN],
            [1.0, 1.0],
        )
        assert result == ChainGrade.HASAN

    def test_tawatur_discount_full_prior_disables_corroboration(self) -> None:
        """shared_blind_spot_prior=1.0 → no corroboration credit at all."""
        pol = CappedCorroborationPolicy(shared_blind_spot_prior=1.0)
        result = pol.compute_corroborated_grade(
            ChainGrade.DAIF,
            [ChainGrade.HASAN, ChainGrade.HASAN, ChainGrade.HASAN],
            [1.0, 1.0, 1.0],
        )
        assert result == ChainGrade.DAIF

    def test_effective_witnesses_below_nominal(self) -> None:
        """The engine reports effective_witnesses < nominal count when prior > 0."""
        engine = CorroborationEngine(min_independent_chains=1)
        result = engine.evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["a1", "a2"],
            corroborating_chains=[
                {"grade": "hasan", "narrators": ["b1", "b2"]},
                {"grade": "hasan", "narrators": ["c1", "c2"]},
            ],
            narrator_metadata={
                "a1": {"model_family": "f0", "upstream_source": "s0"},
                "a2": {"model_family": "f0", "upstream_source": "s0"},
                "b1": {"model_family": "f1", "upstream_source": "s1"},
                "b2": {"model_family": "f1", "upstream_source": "s1"},
                "c1": {"model_family": "f2", "upstream_source": "s2"},
                "c2": {"model_family": "f2", "upstream_source": "s2"},
            },
        )
        assert result.independent_chains == 2
        assert result.shared_blind_spot_prior == pytest.approx(0.20)
        # 2 nominal chains × (1 − 0.20) = 1.6 effective witnesses
        assert result.effective_witnesses == pytest.approx(1.6)


class TestEvaluateCorroborationIntegration:
    """End-to-end corroboration evaluation with correlation detection."""

    def test_attested_independent_chains_upgrade_daif(self) -> None:
        """Demonstrable independence (distinct attested lineage) upgrades DAIF.

        After issue #54, upgrade requires lineage evidence on every chain so
        distinctness can actually be observed — empty metadata is now 'unknown',
        below the gate, and does not upgrade (see TestIssue54IndependenceLimit).
        """
        result = evaluate_corroboration(
            base_grade=ChainGrade.DAIF,
            corroborating_chain_grades=[ChainGrade.HASAN, ChainGrade.HASAN],
            base_narrators=["narr-A", "narr-B"],
            corroborating_narrators=[["narr-C"], ["narr-D", "narr-E"]],
            narrator_metadata={
                "narr-A": {"model_family": "fam-a", "upstream_source": "src-a"},
                "narr-B": {"model_family": "fam-a", "upstream_source": "src-a"},
                "narr-C": {"model_family": "fam-c", "upstream_source": "src-c"},
                "narr-D": {"model_family": "fam-d", "upstream_source": "src-d"},
                "narr-E": {"model_family": "fam-d", "upstream_source": "src-d"},
            },
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


class TestContentAwareGating:
    """Issue #11 — the shādhdh gate: a corroboration bonus must not be usable
    to paper over a live content contradiction, however many "independent"
    chains agree (the fabricated-chain-with-parallel-sub-chains exploit)."""

    # Attested-distinct lineage so independence is demonstrated (issue #54);
    # this isolates the live-contradiction gate from the independence change.
    _ATTESTED_LINEAGE = {
        "narr-A": {"model_family": "fam-a", "upstream_source": "src-a"},
        "narr-B": {"model_family": "fam-b", "upstream_source": "src-b"},
        "narr-C": {"model_family": "fam-c", "upstream_source": "src-c"},
    }

    def test_live_contradiction_blocks_upgrade_even_with_strong_corroboration(self) -> None:
        engine = CorroborationEngine(min_independent_chains=1)
        result = engine.evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["narr-A"],
            corroborating_chains=[
                {"grade": "hasan", "narrators": ["narr-B"]},
                {"grade": "sahih", "narrators": ["narr-C"]},
            ],
            narrator_metadata=self._ATTESTED_LINEAGE,
            has_live_contradiction=True,
        )
        assert result.upgraded is False
        assert result.upgraded_grade == ChainGrade.DAIF
        assert "contradiction" in result.reason.lower()

    def test_without_live_contradiction_upgrade_still_fires(self) -> None:
        """Control: the same inputs upgrade normally when there's no
        contradiction — proving has_live_contradiction is the actual gate,
        not a change to the underlying upgrade math."""
        engine = CorroborationEngine(min_independent_chains=1)
        result = engine.evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["narr-A"],
            narrator_metadata=self._ATTESTED_LINEAGE,
            corroborating_chains=[
                {"grade": "hasan", "narrators": ["narr-B"]},
                {"grade": "sahih", "narrators": ["narr-C"]},
            ],
            has_live_contradiction=False,
        )
        assert result.upgraded is True
        assert result.upgraded_grade == ChainGrade.HASAN

    def test_live_contradiction_gate_applies_via_evaluate_too(self) -> None:
        """Same gate through the exact-text-match evaluate() entry point."""
        engine = CorroborationEngine(min_independent_chains=1)
        result = engine.evaluate(
            claim_text="fabricated claim",
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["narr-A"],
            all_chains=[
                {
                    "claim_text": "fabricated claim",
                    "chain_grade": "sahih",
                    "narrator_ids": ["narr-B"],
                },
            ],
            has_live_contradiction=True,
        )
        assert result.upgraded is False


class TestIssue54IndependenceLimit:
    """Issue #54 — corroboration assumes independence when it knows the least.

    The detector checks three *structural* signals (shared narrator ID, shared
    model family, shared upstream source). Two chains that share NONE of them can
    still be correlated — the paper's §7 concedes this is undetectable in
    principle. This suite does NOT claim to detect that. It pins the narrower,
    fixable defect the issue abstracts: when there is *no lineage metadata at
    all*, the detector scored full independence (1.0) and corroboration fired —
    i.e. the framework assumed independence precisely when it had no evidence for
    it. The honest fix scores unknown lineage *below* the gate: independence must
    be demonstrated, not assumed.
    """

    def test_unknown_lineage_is_not_scored_as_fully_independent(self) -> None:
        """No metadata → the score must NOT be 1.0 (full independence)."""
        det = SharedLineageDetector()
        score = det.compute_independence_score(
            ["narrator-A", "narrator-B"],
            ["narrator-C", "narrator-D"],
            {},  # nothing known about lineage
        )
        assert score < 1.0, "unknown lineage must not read as fully independent"
        assert score < CappedCorroborationPolicy.INDEPENDENCE_THRESHOLD, (
            "unknown lineage must fall below the corroboration gate"
        )

    def test_unknown_lineage_does_not_upgrade_by_default(self) -> None:
        """Two clean-looking chains sharing none of the 3 signals, but with no
        attested lineage, must NOT upgrade a DAIF claim — independence unproven.
        """
        result = evaluate_corroboration(
            base_grade=ChainGrade.DAIF,
            corroborating_chain_grades=[ChainGrade.HASAN, ChainGrade.HASAN],
            base_narrators=["narr-A"],
            corroborating_narrators=[["narr-C"], ["narr-D"]],
            narrator_metadata={},  # no lineage attestation
        )
        assert result == ChainGrade.DAIF, "unproven independence must not upgrade"

    def test_attested_distinct_lineage_still_upgrades(self) -> None:
        """Independence you can *demonstrate* still works: distinct model
        families + distinct upstream sources for every narrator → upgrade fires.
        """
        result = evaluate_corroboration(
            base_grade=ChainGrade.DAIF,
            corroborating_chain_grades=[ChainGrade.HASAN, ChainGrade.HASAN],
            base_narrators=["narr-A"],
            corroborating_narrators=[["narr-C"], ["narr-D"]],
            narrator_metadata={
                "narr-A": {"model_family": "fam-a", "upstream_source": "src-a"},
                "narr-C": {"model_family": "fam-c", "upstream_source": "src-c"},
                "narr-D": {"model_family": "fam-d", "upstream_source": "src-d"},
            },
        )
        assert result == ChainGrade.HASAN

    def test_correlated_blind_spot_is_acknowledged_undetectable(self) -> None:
        """The undetectable case, pinned as a known limit (not a passing check).

        Two chains with fully-distinct, attested lineage that nonetheless share a
        corpus-wide blind spot WILL still upgrade — the detector cannot see
        content-level correlation. This test documents that the framework upgrades
        here *by design gap*, so the behaviour is visible and not silently
        mistaken for a guarantee. See issue #54.
        """
        result = evaluate_corroboration(
            base_grade=ChainGrade.DAIF,
            corroborating_chain_grades=[ChainGrade.HASAN, ChainGrade.HASAN],
            base_narrators=["narr-A"],
            corroborating_narrators=[["narr-C"], ["narr-D"]],
            narrator_metadata={
                "narr-A": {"model_family": "fam-a", "upstream_source": "src-a"},
                "narr-C": {"model_family": "fam-c", "upstream_source": "src-c"},
                "narr-D": {"model_family": "fam-d", "upstream_source": "src-d"},
            },
        )
        # Structurally distinct → upgrades, even though a shared blind spot would
        # make this wrong. Topology cannot discharge independence (paper §7).
        assert result == ChainGrade.HASAN
