"""Tests for evidence provenance (issue #6 follow-up).

The distinction between *population priors* (benchmark seeds, eval harnesses)
and *observed in-pipeline instances* (post-hoc audits, corroboration) is a
signal about the grade — not a new grading axis.  These tests pin that
`evidence_provenance()` reports it honestly and that the classification is
stable.
"""

from __future__ import annotations

import pytest

from isnad.core.registry import EvidenceProvenanceSummary, Registry
from isnad.types import (
    EvidenceAction,
    EvidenceAxis,
    EvidenceProvenance,
    EvidenceType,
    NarratorGrade,
    provenance_of,
)


class TestProvenanceOf:
    def test_benchmark_seed_is_prior(self):
        assert provenance_of(EvidenceType.BOOTSTRAP_SEED) == EvidenceProvenance.PRIOR

    def test_eval_harness_is_prior(self):
        assert provenance_of(EvidenceType.EVAL_HARNESS) == EvidenceProvenance.PRIOR

    def test_post_hoc_audit_is_observed(self):
        assert provenance_of(EvidenceType.POST_HOC_AUDIT) == EvidenceProvenance.OBSERVED

    def test_corroboration_is_observed(self):
        assert provenance_of(EvidenceType.CORROBORATION_OUTCOME) == EvidenceProvenance.OBSERVED

    def test_human_review_is_human(self):
        assert provenance_of(EvidenceType.HUMAN_REVIEW) == EvidenceProvenance.HUMAN

    def test_version_bump_is_meta(self):
        assert provenance_of(EvidenceType.VERSION_BUMP) == EvidenceProvenance.META


class TestEvidenceProvenanceSummary:
    def test_unknown_narrator_is_all_zero(self):
        reg = Registry()
        s = reg.evidence_provenance("nope", "d")
        assert s == EvidenceProvenanceSummary()
        assert not s.prior_only
        assert not s.observation_backed

    def test_prior_only_flag(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.record_evidence(
            "m", "d", EvidenceType.BOOTSTRAP_SEED, EvidenceAction.TADIL, "benchmark prior"
        )
        s = reg.evidence_provenance("m", "d")
        assert s.prior_count == 1
        assert s.observed_count == 0
        assert s.prior_only
        assert not s.observation_backed

    def test_observation_backed(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.record_evidence(
            "m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.TADIL, "audit passed"
        )
        s = reg.evidence_provenance("m", "d")
        assert s.observed_count == 1
        assert s.prior_count == 0
        assert s.observation_backed
        assert not s.prior_only

    def test_mixed_counts(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.record_evidence("m", "d", EvidenceType.BOOTSTRAP_SEED, EvidenceAction.TADIL, "")
        reg.record_evidence("m", "d", EvidenceType.EVAL_HARNESS, EvidenceAction.TADIL, "")
        reg.record_evidence("m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.TADIL, "")
        reg.record_evidence("m", "d", EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL, "")
        reg.record_evidence("m", "d", EvidenceType.HUMAN_REVIEW, EvidenceAction.TADIL, "")
        reg.record_evidence("m", "d", EvidenceType.VERSION_BUMP, EvidenceAction.NEUTRAL, "")
        s = reg.evidence_provenance("m", "d")
        assert s.prior_count == 2
        assert s.observed_count == 2
        assert s.human_count == 1
        assert s.meta_count == 1
        assert s.total_grade_evidence == 5  # excludes the meta (version bump)
        assert s.observation_backed
        assert not s.prior_only

    def test_version_bump_does_not_count_as_grade_evidence(self):
        """A version bump resets the record; it is meta, not grade evidence."""
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.bump_version("m", "d", "v2")
        s = reg.evidence_provenance("m", "d")
        assert s.meta_count == 1
        assert s.total_grade_evidence == 0
        assert not s.prior_only
        assert not s.observation_backed

    def test_survival_signal_is_corroboration_observed(self):
        """Issue #6: the observed-survival signal already exists as corroboration.

        A claim that survived independent verification is recorded as
        CORROBORATION_OUTCOME + TADIL, which is OBSERVED provenance — not a
        prior.  This is the honest answer to #6: no new SURVIVAL enum is
        needed; corroboration IS the observed-instance signal.
        """
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.flag_contradiction("m", "d")  # adverse, but observed
        s = reg.evidence_provenance("m", "d")
        # flag_contradiction logs CORROBORATION_OUTCOME → observed.
        assert s.observed_count == 1


class TestProvenanceIsASignalNotAnAxis:
    def test_provenance_does_not_change_grade(self):
        """Provenance is descriptive; it must not alter the grade itself."""
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        before = reg.get_grade("m", "d")
        s = reg.evidence_provenance("m", "d")
        after = reg.get_grade("m", "d")
        assert before == after == NarratorGrade.RELIABLE
        # And the summary is populated independently of the grade value.
        assert isinstance(s, EvidenceProvenanceSummary)
