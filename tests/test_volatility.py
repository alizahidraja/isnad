"""Tests for the grade-expiry fix — time decay of narrator grades.

Verifies:
- Three-window decay: FRESH as-stored, STALE downgraded one tier, EXPIRED → UNGRADED.
- The stored grade is preserved; only the *effective* lookup grade decays.
- Per-domain + per-narrator-type volatility (config-driven, not hardcoded).
- REJECTED (containment) and UNGRADED never decay; version bump clears the clock.
- record_evidence re-arms the freshness clock.
- RegistryDB round-trips the freshness columns.
"""

from datetime import UTC, datetime, timedelta

import pytest

from isnad.core.registry import (
    Registry,
    RegistryDB,
    ThresholdTransitionPolicy,
)
from isnad.core.volatility import FixedVolatilityPolicy
from isnad.storage.sqlalchemy import drop_db, init_db, reset_engine
from isnad.types import (
    EvidenceAction,
    EvidenceType,
    FreshnessStatus,
    NarratorGrade,
    NarratorType,
    VolatilityPolicy,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _register_fresh(reg: Registry, narrator_id: str, domain: str, grade: NarratorGrade) -> None:
    """Register a grade with a clock that starts at T0 (deterministic decay)."""
    reg.register(narrator_id, domain, grade=grade, graded_at=T0)


class TestFreshnessWindows:
    """FRESH / STALE / EXPIRED by reference time."""

    def test_fresh_grade_used_as_stored(self) -> None:
        reg = Registry()
        _register_fresh(reg, "model-M", "physics", NarratorGrade.RELIABLE)
        result = reg.effective_grade("model-M", "physics", now=T0)
        assert result.grade == NarratorGrade.RELIABLE
        assert result.freshness == FreshnessStatus.FRESH
        assert not result.needs_recheck

    def test_stale_downgrades_one_tier(self) -> None:
        reg = Registry()
        _register_fresh(reg, "model-M", "physics", NarratorGrade.RELIABLE)
        policy = reg.volatility_policy
        ttl = policy.time_to_live(NarratorType.MODEL, "physics")
        # Just inside the grace window at the end of the TTL.
        stale_at = T0 + ttl - timedelta(seconds=1)
        result = reg.effective_grade("model-M", "physics", now=stale_at)
        assert result.grade == NarratorGrade.ACCEPTABLE  # RELIABLE → ACCEPTABLE
        assert result.freshness == FreshnessStatus.STALE
        assert result.needs_recheck

    def test_stale_downgrade_map(self) -> None:
        reg = Registry()
        for grade, expected in [
            (NarratorGrade.RELIABLE, NarratorGrade.ACCEPTABLE),
            (NarratorGrade.ACCEPTABLE, NarratorGrade.WEAK),
            (NarratorGrade.WEAK, NarratorGrade.UNGRADED),
        ]:
            _register_fresh(reg, f"n-{grade.value}", "physics", grade)
            policy = reg.volatility_policy
            ttl = policy.time_to_live(NarratorType.MODEL, "physics")
            stale_at = T0 + ttl - timedelta(seconds=1)
            result = reg.effective_grade(f"n-{grade.value}", "physics", now=stale_at)
            assert result.grade == expected

    def test_expired_reverts_to_ungraded(self) -> None:
        reg = Registry()
        _register_fresh(reg, "model-M", "physics", NarratorGrade.RELIABLE)
        policy = reg.volatility_policy
        ttl = policy.time_to_live(NarratorType.MODEL, "physics")
        result = reg.effective_grade("model-M", "physics", now=T0 + ttl + timedelta(seconds=1))
        assert result.grade == NarratorGrade.UNGRADED
        assert result.freshness == FreshnessStatus.EXPIRED
        assert result.needs_recheck

    def test_stored_grade_preserved_after_expiry(self) -> None:
        """Decay is a lookup-time overlay — the record is never wiped."""
        reg = Registry()
        _register_fresh(reg, "model-M", "physics", NarratorGrade.RELIABLE)
        policy = reg.volatility_policy
        ttl = policy.time_to_live(NarratorType.MODEL, "physics")
        reg.effective_grade("model-M", "physics", now=T0 + ttl + timedelta(days=365))
        narrator = reg.get("model-M", "physics")
        assert narrator is not None
        assert narrator.grade == NarratorGrade.RELIABLE  # stored, not wiped

    def test_get_grade_is_time_aware(self) -> None:
        reg = Registry()
        _register_fresh(reg, "model-M", "physics", NarratorGrade.RELIABLE)
        assert reg.get_grade("model-M", "physics", now=T0) == NarratorGrade.RELIABLE
        policy = reg.volatility_policy
        ttl = policy.time_to_live(NarratorType.MODEL, "physics")
        assert (
            reg.get_grade("model-M", "physics", now=T0 + ttl + timedelta(seconds=1))
            == NarratorGrade.UNGRADED
        )
        assert reg.needs_recheck("model-M", "physics", now=T0 + ttl - timedelta(seconds=1))


class TestRejectedAndUngradedNeverDecay:
    """Containment is permanent; ungraded has nothing to decay."""

    def test_rejected_never_decays(self) -> None:
        reg = Registry()
        reg.register("poisoned", "general", grade=NarratorGrade.REJECTED)
        result = reg.effective_grade("poisoned", "general", now=T0 + timedelta(days=10_000))
        assert result.grade == NarratorGrade.REJECTED
        assert result.freshness == FreshnessStatus.FRESH
        assert not result.needs_recheck

    def test_ungraded_never_decays(self) -> None:
        reg = Registry()
        reg.register("model-M", "physics")  # UNGRADED, no clock
        result = reg.effective_grade("model-M", "physics", now=T0 + timedelta(days=10_000))
        assert result.grade == NarratorGrade.UNGRADED

    def test_unknown_narrator_is_ungraded(self) -> None:
        reg = Registry()
        assert reg.get_grade("ghost", "physics", now=T0) == NarratorGrade.UNGRADED


class TestVolatilityConfiguration:
    """Volatility is config-driven, not a hardcoded table."""

    def test_model_ttl_shorter_than_source_ttl(self) -> None:
        policy = FixedVolatilityPolicy(base_days=90)
        model_ttl = policy.time_to_live(NarratorType.MODEL, "physics")
        source_ttl = policy.time_to_live(NarratorType.SOURCE, "physics")
        assert model_ttl < source_ttl

    def test_per_domain_override(self) -> None:
        policy = FixedVolatilityPolicy(base_days=90, domain_days={"physics": 365})
        assert policy.time_to_live(NarratorType.MODEL, "physics") == timedelta(days=365)
        assert policy.time_to_live(NarratorType.MODEL, "general") == timedelta(days=90 * 0.5)

    def test_same_narrator_different_domain_ttl(self) -> None:
        reg = Registry(
            volatility_policy=FixedVolatilityPolicy(base_days=90, domain_days={"physics": 365})
        )
        reg.register("model-M", "physics", grade=NarratorGrade.RELIABLE)
        reg.register("model-M", "general", grade=NarratorGrade.RELIABLE)
        p = reg.volatility_policy
        assert reg.get("model-M", "physics").valid_until is not None
        assert reg.get("model-M", "general").valid_until is not None
        assert p.time_to_live(NarratorType.MODEL, "physics") > p.time_to_live(
            NarratorType.MODEL, "general"
        )

    def test_invalid_stale_ratio_rejected(self) -> None:
        with pytest.raises(ValueError):
            FixedVolatilityPolicy(stale_ratio=1.5)

    def test_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("ISNAD_TTL_BASE_DAYS", "7")
        policy = FixedVolatilityPolicy()
        assert policy.time_to_live(NarratorType.SOURCE, "general") == timedelta(days=14)

    def test_custom_volatility_policy_is_pluggable(self) -> None:
        class NoDecay(VolatilityPolicy):
            def time_to_live(self, narrator_type, domain):
                return timedelta(days=365 * 100)

            def stale_window(self, narrator_type, domain):
                return timedelta(days=0)

            def valid_until(self, narrator_type, domain, now=None):
                return (now or datetime.now(UTC)) + self.time_to_live(narrator_type, domain)

        reg = Registry(volatility_policy=NoDecay())
        reg.register("model-M", "physics", grade=NarratorGrade.RELIABLE, graded_at=T0)
        assert (
            reg.get_grade("model-M", "physics", now=T0 + timedelta(days=365))
            == NarratorGrade.RELIABLE
        )


class TestClockRearmAndClear:
    """Evidence re-arms the clock; version bump / quarantine clear it."""

    def test_record_evidence_restarts_window(self) -> None:
        reg = Registry()
        reg.register("model-M", "physics", grade=NarratorGrade.RELIABLE)
        old_until = reg.get("model-M", "physics").valid_until
        assert old_until is not None
        reg.record_evidence(
            "model-M",
            "physics",
            EvidenceType.EVAL_HARNESS,
            EvidenceAction.TADIL,
            "Re-validated",
        )
        narrator = reg.get("model-M", "physics")
        assert narrator is not None
        assert narrator.graded_at is not None
        assert narrator.valid_until is not None
        assert narrator.valid_until > old_until

    def test_version_bump_clears_clock(self) -> None:
        reg = Registry()
        reg.register("model-M", "physics", grade=NarratorGrade.RELIABLE)
        reg.bump_version("model-M", "physics", "v2")
        narrator = reg.get("model-M", "physics")
        assert narrator is not None
        assert narrator.graded_at is None
        assert narrator.valid_until is None
        assert reg.get_grade("model-M", "physics", now=T0) == NarratorGrade.UNGRADED

    def test_quarantine_clears_clock(self) -> None:
        reg = Registry()
        reg.register("source-A", "physics", grade=NarratorGrade.RELIABLE)
        reg.quarantine("source-A", "physics", "Injection")
        narrator = reg.get("source-A", "physics")
        assert narrator is not None
        assert narrator.graded_at is None
        assert narrator.valid_until is None

    def test_evidence_driven_rejected_has_no_clock(self) -> None:
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("scraper-v1", "physics", grade=NarratorGrade.WEAK)
        for i in range(3):
            reg.record_evidence(
                "scraper-v1",
                "physics",
                EvidenceType.POST_HOC_AUDIT,
                EvidenceAction.JARH,
                f"fail {i}",
            )
        narrator = reg.get("scraper-v1", "physics")
        assert narrator is not None
        assert narrator.grade == NarratorGrade.REJECTED
        assert narrator.valid_until is None


class TestPersistence:
    """RegistryDB round-trips the freshness columns."""

    def test_graded_at_and_valid_until_round_trip(self) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite://")
        session_maker = sessionmaker(bind=engine)
        from isnad.models import Base

        Base.metadata.create_all(engine)
        session = session_maker()

        reg = RegistryDB(session=session)
        reg.registry.register(
            "model-M",
            "physics",
            grade=NarratorGrade.RELIABLE,
            narrator_type=NarratorType.MODEL,
        )
        reg.flush()

        fresh = RegistryDB(session=session)
        fresh.load()
        narrator = fresh.registry.get("model-M", "physics")
        assert narrator is not None
        assert narrator.graded_at is not None
        assert narrator.valid_until is not None
        assert fresh.registry.get_grade("model-M", "physics", now=T0) == NarratorGrade.RELIABLE

        # Expiry survives reload: valid_until reloaded → grade decays on time.
        policy = fresh.registry.volatility_policy
        ttl = policy.time_to_live(NarratorType.MODEL, "physics")
        assert fresh.registry.get_grade("model-M", "physics", now=narrator.valid_until) in (
            NarratorGrade.UNGRADED,
            NarratorGrade.ACCEPTABLE,
        )
        assert fresh.registry.needs_recheck("model-M", "physics", now=narrator.valid_until)

        engine.dispose()

    def test_legacy_rows_keep_null_clocks_on_load(self) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from isnad.models import Base, NarratorRegistry

        engine = create_engine("sqlite://")
        session_maker = sessionmaker(bind=engine)
        Base.metadata.create_all(engine)
        session = session_maker()

        # A pre-migration row: graded, but with no freshness clock at all.
        session.add(
            NarratorRegistry(
                narrator_id="legacy-scribe",
                domain_tag="physics",
                narrator_type=NarratorType.SOURCE.value,
                grade=NarratorGrade.RELIABLE.value,
                is_active=True,
                graded_at=None,
                valid_until=None,
            )
        )
        session.commit()

        reg = RegistryDB(session=session)
        reg.load()
        narrator = reg.registry.get("legacy-scribe", "physics")
        assert narrator is not None
        assert narrator.graded_at is None
        assert narrator.valid_until is None

        # NULL clock = never expires: still FRESH decades later.
        result = reg.registry.effective_grade(
            "legacy-scribe", "physics", now=T0 + timedelta(days=365 * 10)
        )
        assert result.grade == NarratorGrade.RELIABLE
        assert result.freshness == FreshnessStatus.FRESH
        assert result.needs_recheck is False

        engine.dispose()


# ---------------------------------------------------------------------------
# renew_grade() must not manufacture upgrade evidence (regression: the
# original PR wrote CORROBORATION_OUTCOME + TADIL, which fed the upgrade
# thresholds — five renewals + one neutral audit promoted a WEAK narrator
# to ACCEPTABLE with nothing ever evaluating its correctness.)
# ---------------------------------------------------------------------------


class TestRenewGradeDoesNotPromote:
    def test_renewals_do_not_feed_upgrade_thresholds(self):
        """5 renewals + 1 neutral audit must leave a WEAK narrator WEAK."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("scribe", "physics", grade=NarratorGrade.WEAK)

        for _ in range(5):
            assert reg.renew_grade("scribe", "physics") is True

        # A neutral audit would have been the trigger for the old bug.
        reg.record_evidence(
            "scribe", "physics", EvidenceType.POST_HOC_AUDIT, EvidenceAction.NEUTRAL
        )
        assert reg.get_grade("scribe", "physics") == NarratorGrade.WEAK

    def test_renewals_do_not_feed_bayesian_posterior(self):
        """Under the default Bayesian policy, renewals must not inflate the mean."""
        reg = Registry()  # default BayesianTransitionPolicy
        reg.register("scribe", "physics", grade=NarratorGrade.WEAK)

        for _ in range(5):
            reg.renew_grade("scribe", "physics")

        # The narrator's grade must not have been promoted by renewal alone.
        assert reg.get_grade("scribe", "physics") == NarratorGrade.WEAK
