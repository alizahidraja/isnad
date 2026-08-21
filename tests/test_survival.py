"""Tests for the claim-scoped survival primitive (issue #25).

Survival is the positive observed-instance signal: a claim produced by a
narrator survived independent (endorsed) verification.  Three properties are
pinned:

1. **Tazkiyah guard** — a self-verified seal (amber) is NOT survival; it is
   refused.  Only an endorsed (green) verification counts.
2. **Claim-scoped dedup** — re-verifying the same (claim_id, source) is a
   no-op; farming is resisted because survival accumulates per *new* claim.
3. **Precision signal** — survival feeds the jarḥ–taʿdīl loop as PRECISION +
   TADIL (OBSERVED provenance), never seeding ʿadālah (integrity).
"""

from __future__ import annotations

import pytest

from isnad.core.registry import Registry
from isnad.types import (
    EvidenceAction,
    EvidenceProvenance,
    EvidenceType,
    NarratorGrade,
    provenance_of,
)


class TestSurvivalClassification:
    def test_survival_is_observed_provenance(self):
        assert provenance_of(EvidenceType.SURVIVAL) == EvidenceProvenance.OBSERVED

    def test_survival_is_not_prior(self):
        assert provenance_of(EvidenceType.SURVIVAL) != EvidenceProvenance.PRIOR


class TestTazkiyahGuard:
    def test_self_verified_is_refused(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.UNGRADED)
        g = reg.record_survival("m", "d", "c1", "seal", self_verified=True)
        assert g == NarratorGrade.UNGRADED  # unchanged
        # No evidence was logged.
        assert reg.evidence_provenance("m", "d").observed_count == 0

    def test_endorsed_survival_is_recorded(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.UNGRADED)
        g = reg.record_survival("m", "d", "c1", "gov.uk", self_verified=False)
        # Recorded as SURVIVAL + TADIL → observed.
        assert reg.evidence_provenance("m", "d").observed_count == 1


class TestClaimScopedDedup:
    def test_same_claim_and_source_dedup(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.UNGRADED)
        reg.record_survival("m", "d", "c1", "gov.uk")
        reg.record_survival("m", "d", "c1", "gov.uk")
        reg.record_survival("m", "d", "c1", "gov.uk")
        # Only one SURVIVAL entry.
        assert reg.evidence_provenance("m", "d").observed_count == 1

    def test_same_claim_different_source_counts_twice(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.UNGRADED)
        reg.record_survival("m", "d", "c1", "gov.uk")
        reg.record_survival("m", "d", "c1", "accreditor.org")
        # Same claim, two different independent verifiers → two events.
        assert reg.evidence_provenance("m", "d").observed_count == 2

    def test_different_claims_accumulate(self):
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.UNGRADED)
        for i in range(5):
            reg.record_survival("m", "d", f"claim-{i}", "gov.uk")
        assert reg.evidence_provenance("m", "d").observed_count == 5


class TestSurvivalFeedsPrecisionNotIntegrity:
    def test_survival_never_seeds_adalah(self):
        """Survival is a ḍabṭ (precision) signal — it must not anchor ʿadālah."""
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.UNGRADED)
        reg.record_survival("m", "d", "c1", "gov.uk")
        narrator = reg.get("m", "d")
        assert narrator.adalah_grade.value == "unassessed"  # integrity untouched
        # The grade moved via precision (ḍabṭ), not integrity.
        assert narrator.grade in (
            NarratorGrade.UNGRADED,
            NarratorGrade.WEAK,
            NarratorGrade.ACCEPTABLE,
        )

    def test_survival_does_not_recover_a_compromised_narrator(self):
        """A narrator quarantined for integrity stays REJECTED despite survival.

        Survival is precision; a fabricator whose ʿadālah is COMPROMISED must
        not climb back via plausible-but-untrue claims that happen to verify.
        """
        reg = Registry()
        reg.register("liar", "d", grade=NarratorGrade.RELIABLE)
        reg.quarantine("liar", "d", "caught fabricating")
        assert reg.get_grade("liar", "d") == NarratorGrade.REJECTED
        # A flood of "surviving" claims cannot lift the integrity quarantine.
        for i in range(20):
            reg.record_survival("liar", "d", f"claim-{i}", "gov.uk")
        assert reg.get_grade("liar", "d") == NarratorGrade.REJECTED


class TestDedupSurvivesRoundTrip:
    def test_dedup_persists_through_registry_db(self, tmp_path):
        """Dedup is derived from the evidence log, so it survives a DB round-trip."""
        import tempfile

        from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine
        from sqlalchemy.orm import Session

        from isnad.core.registry import RegistryDB

        with tempfile.TemporaryDirectory() as d:
            url = f"sqlite:///{d}/survival.db"
            reset_engine()
            init_db(url)
            engine = create_engine_from_url(url)

            with Session(engine) as s:
                rdb = RegistryDB(session=s)
                rdb.registry.register("m", "d", grade=NarratorGrade.UNGRADED)
                rdb.registry.record_survival("m", "d", "c1", "gov.uk")
                rdb.flush()
                s.commit()

            with Session(engine) as s:
                rdb2 = RegistryDB(session=s)
                rdb2.load()
                # After reload, the same claim+source must still dedup.
                before = rdb2.registry.evidence_provenance("m", "d").observed_count
                rdb2.registry.record_survival("m", "d", "c1", "gov.uk")
                after = rdb2.registry.evidence_provenance("m", "d").observed_count
                assert before == after == 1

            reset_engine()


class TestEndToEndWithLiveVerify:
    def test_endorsed_seal_is_survival_self_verified_is_not(self):
        """Composes with the Live Verify adapter's self_verified flag.

        An ENDORSED seal (verified and not self_verified) → survival recorded.
        A SELF-verified seal (verified but self_verified) → refused.
        """
        from isnad.integrations.liveverify.client import VerificationResult
        from isnad.integrations.liveverify.adapter import seal_to_narrator

        reg = Registry()

        # Endorsed seal → integrity HIGH, and its source is a genuine survival.
        endorsed = VerificationResult(
            verified=True,
            status="VERIFIED",
            domain="gov.uk",
            authorized_by="gov.uk/v1",
            self_verified=False,
        )
        sealed = seal_to_narrator(endorsed)
        assert sealed.self_verified is False
        # The caller records survival only for endorsed (non-self-verified) seals.
        reg.register(sealed.narrator_id, "d", grade=sealed.grade)
        g = reg.record_survival(
            sealed.narrator_id, "d", "claim-1", sealed.domain, self_verified=sealed.self_verified
        )
        assert reg.evidence_provenance(sealed.narrator_id, "d").observed_count == 1

        # Self-verified seal → refused.
        self_sealed = seal_to_narrator(
            VerificationResult(
                verified=True, status="VERIFIED", domain="blog.example", self_verified=True
            )
        )
        assert self_sealed.self_verified is True
        reg.register(self_sealed.narrator_id, "d", grade=self_sealed.grade)
        g2 = reg.record_survival(
            self_sealed.narrator_id,
            "d",
            "claim-1",
            self_sealed.domain,
            self_verified=self_sealed.self_verified,
        )
        assert reg.evidence_provenance(self_sealed.narrator_id, "d").observed_count == 0


class TestRejectedStickyRegression:
    """A bug found while testing survival: the Bayesian policy (the DEFAULT)
    had no REJECTED-stickiness guard, so a quarantined narrator could be
    silently promoted back to RELIABLE on a flood of positive precision
    evidence.  This pins the fix — REJECTED is active containment."""

    def test_bayesian_rejected_is_sticky(self):
        from isnad.core.policies import BayesianTransitionPolicy

        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("liar", "d", grade=NarratorGrade.RELIABLE)
        reg.quarantine("liar", "d", "caught fabricating")
        assert reg.get_grade("liar", "d") == NarratorGrade.REJECTED

        # A flood of positive precision evidence (survival) must not rehabilitate.
        for i in range(30):
            reg.record_survival("liar", "d", f"claim-{i}", "gov.uk")
        assert reg.get_grade("liar", "d") == NarratorGrade.REJECTED

    def test_bayesian_human_review_restores_to_weak(self):
        """Only an explicit human-review taʿdīl restores from REJECTED (to WEAK)."""
        from isnad.core.policies import BayesianTransitionPolicy

        reg = Registry(transition_policy=BayesianTransitionPolicy())
        reg.register("liar", "d", grade=NarratorGrade.RELIABLE)
        reg.quarantine("liar", "d", "caught fabricating")
        reg.record_evidence(
            "liar", "d", EvidenceType.HUMAN_REVIEW, EvidenceAction.TADIL, "rehabilitated on review"
        )
        assert reg.get_grade("liar", "d") == NarratorGrade.WEAK
