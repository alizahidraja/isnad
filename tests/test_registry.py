"""Tests for registry.py — narrator registry + jarḥ–taʿdīl state machine.

Verifies paper §4.2 commitments:
- Domain-conditioned grading: key is (narrator_id, domain).
- Version-bump resets to UNGRADED.
- jarḥ–taʿdīl is a state machine driven by evidence.
- ʿAdālah and ḍabṭ as two distinct axes.
- REJECTED is sticky (active containment) — with ThresholdTransitionPolicy.
- BayesianTransitionPolicy as the new default.
"""

import pytest

from isnad.core.registry import (
    BayesianTransitionPolicy,
    CalibratedThresholdPolicy,
    Registry,
    ThresholdTransitionPolicy,
)
from isnad.types import (
    AdalahGrade,
    DabtGrade,
    EvidenceAction,
    EvidenceAxis,
    EvidenceType,
    NarratorGrade,
)


class TestDomainConditionedGrading:
    """Registry key is (narrator_id, domain), never narrator_id alone."""

    def test_same_narrator_different_domains_have_different_grades(self) -> None:
        reg = Registry()

        reg.register("model-M", "physics-classical", grade=NarratorGrade.RELIABLE)
        reg.register("model-M", "physics-quantum", grade=NarratorGrade.WEAK)

        assert reg.get_grade("model-M", "physics-classical") == NarratorGrade.RELIABLE
        assert reg.get_grade("model-M", "physics-quantum") == NarratorGrade.WEAK

    def test_unknown_narrator_defaults_to_ungraded(self) -> None:
        reg = Registry()
        assert reg.get_grade("nonexistent", "any-domain") == NarratorGrade.UNGRADED


class TestVersionBumpReset:
    """Version bump resets narrator to UNGRADED per domain (paper §4.2)."""

    def test_version_bump_resets_grade(self) -> None:
        reg = Registry()
        reg.register(
            "ingest-model",
            "physics",
            grade=NarratorGrade.RELIABLE,
            model_version="v1",
        )
        assert reg.get_grade("ingest-model", "physics") == NarratorGrade.RELIABLE

        reg.bump_version("ingest-model", "physics", "v2")
        assert reg.get_grade("ingest-model", "physics") == NarratorGrade.UNGRADED

    def test_version_bump_clears_error_rate(self) -> None:
        reg = Registry()
        reg.register(
            "ingest-model",
            "physics",
            grade=NarratorGrade.ACCEPTABLE,
            known_error_rate=0.05,
            model_version="v1",
        )

        reg.bump_version("ingest-model", "physics", "v2")
        narrator = reg.get("ingest-model", "physics")
        assert narrator is not None
        assert narrator.known_error_rate is None
        assert narrator.model_version == "v2"

    def test_version_bump_resets_adalah_and_dabt(self) -> None:
        reg = Registry()
        reg.register(
            "ingest-model",
            "physics",
            adalah=AdalahGrade.HIGH,
            dabt=DabtGrade.HIGH,
        )

        reg.bump_version("ingest-model", "physics", "v2")
        narrator = reg.get("ingest-model", "physics")
        assert narrator is not None
        assert narrator.adalah_grade == AdalahGrade.UNASSESSED
        assert narrator.dabt_grade == DabtGrade.UNASSESSED

    def test_version_bump_logs_evidence(self) -> None:
        reg = Registry()
        reg.register("ingest-model", "physics")
        reg.bump_version("ingest-model", "physics", "v2")

        narrator = reg.get("ingest-model", "physics")
        assert narrator is not None
        assert len(narrator.evidence_log) == 1
        assert narrator.evidence_log[0]["evidence_type"] == EvidenceType.VERSION_BUMP.value


class TestJarhTadilStateMachine:
    """The jarḥ–taʿdīl loop is a state machine, not a formula (paper §4.2)."""

    def test_downgrade_on_sufficient_adverse_evidence(self) -> None:
        """Threshold policy: 3 adverse → downgrade from RELIABLE to ACCEPTABLE."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("scraper-v1", "physics", grade=NarratorGrade.RELIABLE)

        # 3 adverse events → downgrade
        for i in range(3):
            new_grade = reg.record_evidence(
                "scraper-v1",
                "physics",
                EvidenceType.POST_HOC_AUDIT,
                EvidenceAction.JARH,
                f"Audit failure {i}",
            )
        assert new_grade == NarratorGrade.ACCEPTABLE

    def test_upgrade_requires_sustained_corroborated_accuracy(self) -> None:
        """Threshold policy: 5 positive (3 corroborated) → upgrade to ACCEPTABLE."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("model-M", "physics", grade=NarratorGrade.WEAK)

        # Give 5 positive events, 3 of which are corroboration outcomes
        for i in range(3):
            reg.record_evidence(
                "model-M",
                "physics",
                EvidenceType.CORROBORATION_OUTCOME,
                EvidenceAction.TADIL,
                f"Corroborated {i}",
            )
        for i in range(2):
            reg.record_evidence(
                "model-M",
                "physics",
                EvidenceType.EVAL_HARNESS,
                EvidenceAction.TADIL,
                f"Eval pass {i}",
            )

        narrator = reg.get("model-M", "physics")
        assert narrator is not None
        assert narrator.grade == NarratorGrade.ACCEPTABLE

    def test_rejected_is_sticky(self) -> None:
        """Threshold policy: REJECTED is sticky — only human review restores."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("poisoned-source", "general", grade=NarratorGrade.REJECTED)

        # Even favorable evidence shouldn't auto-restore
        new_grade = reg.record_evidence(
            "poisoned-source",
            "general",
            EvidenceType.CORROBORATION_OUTCOME,
            EvidenceAction.TADIL,
            "Corroborated claim",
        )
        assert new_grade == NarratorGrade.REJECTED

    def test_human_review_can_restore_from_rejected(self) -> None:
        """Threshold policy: HUMAN_REVIEW + TADIL restores REJECTED → WEAK."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("poisoned-source", "general", grade=NarratorGrade.REJECTED)

        new_grade = reg.record_evidence(
            "poisoned-source",
            "general",
            EvidenceType.HUMAN_REVIEW,
            EvidenceAction.TADIL,
            "Human reviewer cleared",
        )
        assert new_grade == NarratorGrade.WEAK  # restored to weak, not reliable


def _threshold_policies() -> list:
    """Fresh instances of every threshold-family policy in the package.

    The ratchet fix (issue #9 finding #1) is applied identically to all of
    them, so the regression constraints below are parametrized across the set.
    Each policy exposes its own downgrade threshold and upgrade requirement, so
    the scenarios are built relative to those rather than hardcoded — the two
    policies use different thresholds and windows.
    """
    return [ThresholdTransitionPolicy(), CalibratedThresholdPolicy()]


def _thresholds(policy) -> tuple[int, int, int]:
    """(downgrade_threshold, upgrade_sustained_count, window) for a policy."""
    down = getattr(policy, "downgrade_threshold", None) or policy.DOWNGRADE_THRESHOLD
    up = getattr(policy, "upgrade_sustained_count", None) or policy.UPGRADE_SUSTAINED_COUNT
    window = getattr(policy, "window", None) or policy.DEFAULT_WINDOW
    return down, up, window


@pytest.mark.parametrize("policy", _threshold_policies(), ids=lambda p: type(p).__name__)
class TestThresholdRatchetRegression:
    """Regression tests for issue #9 finding #1 — the monotonic ratchet.

    The threshold-family policies counted adverse (jarḥ) evidence over the
    narrator's *entire* history with no window or decay, and the downgrade
    branch was level-triggered. Once a narrator crossed the adverse threshold,
    every subsequent evidence call — including pure taʿdīl — downgraded it one
    tier, marching RELIABLE → ACCEPTABLE → WEAK → REJECTED with no possible
    recovery. A sliding window plus an edge trigger repairs this: stale adverse
    evidence ages out and only arriving evidence moves the grade, so sustained
    good behaviour recovers a narrator while a narrator that *keeps* failing
    still reaches REJECTED.

    Parametrized across every threshold-family policy to back the claim that the
    fix is applied identically to all of them.
    """

    def _seed(
        self,
        reg: Registry,
        nid: str,
        action: EvidenceAction,
        etype: EvidenceType,
        n: int,
        axis: EvidenceAxis = EvidenceAxis.PRECISION,
    ) -> None:
        # These scenarios model *precision* (ḍabṭ) lapses — audit-detected error
        # rate, which the tradition treats as recoverable over time. Integrity
        # (ʿadālah) behaviour is covered by TestIntegrityAxisPermanence below.
        for i in range(n):
            reg.record_evidence(nid, "physics", etype, action, f"ev {i}", axis=axis)

    def test_sustained_favorable_recovers_a_downgraded_narrator(self, policy) -> None:
        """Past the threshold + sustained recent taʿdīl → narrator fully recovers.

        The core of the ratchet: recovery must be possible for a *precision*
        lapse. Drive a RELIABLE narrator down one tier, then feed a long clean
        corroborated streak and require it to climb all the way back to RELIABLE.
        """
        down, up, window = _thresholds(policy)
        reg = Registry(transition_policy=policy)
        reg.register("scraper-v1", "physics", grade=NarratorGrade.RELIABLE)

        # Cross the adverse threshold → one downgrade to ACCEPTABLE.
        self._seed(reg, "scraper-v1", EvidenceAction.JARH, EvidenceType.POST_HOC_AUDIT, down)
        assert reg.get_grade("scraper-v1", "physics") == NarratorGrade.ACCEPTABLE

        # Enough corroborated favorable evidence to climb two tiers back to top.
        self._seed(
            reg, "scraper-v1", EvidenceAction.TADIL, EvidenceType.CORROBORATION_OUTCOME, window + up
        )
        assert reg.get_grade("scraper-v1", "physics") == NarratorGrade.RELIABLE

    def test_recovery_from_weak_is_possible(self, policy) -> None:
        """A WEAK narrator recovers to ACCEPTABLE on a sustained clean streak.

        WEAK is the last grade above sticky REJECTED — the ratchet made this
        recovery impossible. (A narrator driven to REJECTED by sustained failure
        stays contained; that is intended and covered separately.)
        """
        _, up, _ = _thresholds(policy)
        reg = Registry(transition_policy=policy)
        reg.register("model-W", "physics", grade=NarratorGrade.WEAK)

        self._seed(reg, "model-W", EvidenceAction.TADIL, EvidenceType.CORROBORATION_OUTCOME, up)
        assert reg.get_grade("model-W", "physics") == NarratorGrade.ACCEPTABLE

    def test_stale_adverse_does_not_downgrade_on_new_favorable(self, policy) -> None:
        """Old adverse evidence + fresh taʿdīl must not trigger a downgrade.

        The bug: level-triggered downgrade fired on every call once the
        cumulative count was high. The edge trigger makes only arriving jarḥ
        able to downgrade.
        """
        down, _, _ = _thresholds(policy)
        reg = Registry(transition_policy=policy)
        reg.register("model-M", "physics", grade=NarratorGrade.RELIABLE)

        self._seed(reg, "model-M", EvidenceAction.JARH, EvidenceType.POST_HOC_AUDIT, down)
        grade_before = reg.get_grade("model-M", "physics")

        # A single favorable event must not push it further down.
        reg.record_evidence(
            "model-M", "physics", EvidenceType.EVAL_HARNESS, EvidenceAction.TADIL, "clean eval"
        )
        assert reg.get_grade("model-M", "physics") >= grade_before  # ordinal: no downgrade

    def test_persistent_adverse_still_reaches_rejected(self, policy) -> None:
        """Genuine repeat offenders must still be contained (REJECTED).

        The fix must not weaken containment for narrators that keep failing.
        """
        down, _, _ = _thresholds(policy)
        reg = Registry(transition_policy=policy)
        reg.register("bad-source", "physics", grade=NarratorGrade.RELIABLE)

        # Enough uninterrupted adverse evidence for three downgrades → REJECTED.
        self._seed(reg, "bad-source", EvidenceAction.JARH, EvidenceType.POST_HOC_AUDIT, down * 3)
        assert reg.get_grade("bad-source", "physics") == NarratorGrade.REJECTED

    def test_more_audit_evidence_does_not_reduce_a_healthy_grade(self, policy) -> None:
        """§8.6 symptom: mostly-favorable evidence must not ratchet down.

        A narrator with a few early failures but a strong recent record should
        not be worse off for having *more* evidence logged.
        """
        down, _, window = _thresholds(policy)
        reg = Registry(transition_policy=policy)
        reg.register("scraper-v2", "physics", grade=NarratorGrade.RELIABLE)

        # Early failures (one downgrade), then a clean streak longer than the window.
        self._seed(reg, "scraper-v2", EvidenceAction.JARH, EvidenceType.POST_HOC_AUDIT, down)
        self._seed(
            reg, "scraper-v2", EvidenceAction.TADIL, EvidenceType.CORROBORATION_OUTCOME, window + 3
        )
        assert reg.get_grade("scraper-v2", "physics") != NarratorGrade.REJECTED


@pytest.mark.parametrize("policy", _threshold_policies(), ids=lambda p: type(p).__name__)
class TestIntegrityAxisPermanence:
    """Issue #9 conceptual follow-up — ʿadālah (integrity) does not forget.

    The sliding-window ratchet fix, applied uniformly, would forget integrity
    strikes too — silently reopening the fabricator-rehabilitation path. The
    axis split makes integrity (ʿadālah) jarḥ permanent and non-forgettable,
    while precision (ḍabṭ) jarḥ stays windowed and recoverable. These tests pin
    that asymmetry.
    """

    def _seed(self, reg, nid, action, etype, n, axis) -> None:
        for i in range(n):
            reg.record_evidence(nid, "physics", etype, action, f"ev {i}", axis=axis)

    def test_integrity_jarh_caps_grade_and_tadil_cannot_lift_it(self, policy) -> None:
        """A precision-clean streak can never lift a grade held by an integrity strike.

        This is al-jarḥ muqaddam ʿalā al-taʿdīl: impugnment of integrity
        outranks any amount of later accreditation.
        """
        down, up, window = _thresholds(policy)
        reg = Registry(transition_policy=policy)
        reg.register("liar", "physics", grade=NarratorGrade.RELIABLE)

        # One threshold's worth of integrity strikes → permanent one-tier cap.
        self._seed(
            reg,
            "liar",
            EvidenceAction.JARH,
            EvidenceType.HUMAN_REVIEW,
            down,
            EvidenceAxis.INTEGRITY,
        )
        assert reg.get_grade("liar", "physics") == NarratorGrade.ACCEPTABLE

        # A flood of corroborated precision taʿdīl must NOT restore RELIABLE.
        self._seed(
            reg,
            "liar",
            EvidenceAction.TADIL,
            EvidenceType.CORROBORATION_OUTCOME,
            (window + up) * 2,
            EvidenceAxis.PRECISION,
        )
        assert reg.get_grade("liar", "physics") == NarratorGrade.ACCEPTABLE

    def test_integrity_strikes_never_age_out(self, policy) -> None:
        """Integrity jarḥ separated by a long clean gap still accumulates.

        Unlike precision jarḥ, integrity strikes are not windowed: strikes far
        apart in history still sum toward the permanent cap.
        """
        down, _, window = _thresholds(policy)
        reg = Registry(transition_policy=policy)
        reg.register("n", "physics", grade=NarratorGrade.RELIABLE)

        # One integrity strike short of a second downgrade, then a long clean
        # precision streak (longer than the window), then the strike that
        # completes the second threshold. The old strikes must not have expired.
        self._seed(
            reg, "n", EvidenceAction.JARH, EvidenceType.HUMAN_REVIEW, down, EvidenceAxis.INTEGRITY
        )
        self._seed(
            reg,
            "n",
            EvidenceAction.TADIL,
            EvidenceType.CORROBORATION_OUTCOME,
            window + 5,
            EvidenceAxis.PRECISION,
        )
        # Second full threshold of integrity strikes → second permanent tier down.
        self._seed(
            reg, "n", EvidenceAction.JARH, EvidenceType.HUMAN_REVIEW, down, EvidenceAxis.INTEGRITY
        )
        assert reg.get_grade("n", "physics") == NarratorGrade.WEAK

    def test_unspecified_axis_is_treated_as_integrity(self, policy) -> None:
        """An untagged jarḥ that resolves to UNSPECIFIED is non-forgettable.

        Forgetting is a privilege a caller earns by an explicit (or
        automatically-derived) PRECISION axis. HUMAN_REVIEW is the type that
        defaults to UNSPECIFIED → integrity, so absent an explicit axis its
        impugnment persists. (Automated types like POST_HOC_AUDIT default to
        PRECISION and are covered separately.)
        """
        down, up, window = _thresholds(policy)
        reg = Registry(transition_policy=policy)
        reg.register("n", "physics", grade=NarratorGrade.RELIABLE)

        # UNSPECIFIED (the default for HUMAN_REVIEW) adverse → one permanent tier.
        for i in range(down):
            reg.record_evidence("n", "physics", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, "")
        assert reg.get_grade("n", "physics") == NarratorGrade.ACCEPTABLE

        # Precision taʿdīl cannot lift it back to RELIABLE — untagged jarḥ stuck.
        self._seed(
            reg,
            "n",
            EvidenceAction.TADIL,
            EvidenceType.CORROBORATION_OUTCOME,
            window + up,
            EvidenceAxis.PRECISION,
        )
        assert reg.get_grade("n", "physics") == NarratorGrade.ACCEPTABLE


class TestIntegrityStrikeGranularity:
    """Issue #21 — how many integrity strikes lower the ceiling one tier.

    ``integrity_strikes_per_tier`` is now configurable. Default (None) keeps
    integrity on the same footing as precision (one tier per downgrade
    threshold's worth). Setting it to 1 gives the strict
    single-proven-lie-caps-immediately standard.
    """

    def test_default_matches_downgrade_threshold(self):
        # ThresholdTransitionPolicy: DOWNGRADE_THRESHOLD = 3.
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("n", "physics", grade=NarratorGrade.RELIABLE)
        # 2 integrity strikes < 3 → no cap yet.
        for _ in range(2):
            reg.record_evidence(
                "n", "physics", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, "",
                axis=EvidenceAxis.INTEGRITY,
            )
        assert reg.get_grade("n", "physics") == NarratorGrade.RELIABLE
        # 3rd strike completes one threshold → one tier down.
        reg.record_evidence(
            "n", "physics", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, "",
            axis=EvidenceAxis.INTEGRITY,
        )
        assert reg.get_grade("n", "physics") == NarratorGrade.ACCEPTABLE

    def test_single_strike_caps_immediately(self):
        # Strict: integrity_strikes_per_tier=1 → one proven lie caps a tier.
        reg = Registry(transition_policy=ThresholdTransitionPolicy(integrity_strikes_per_tier=1))
        reg.register("n", "physics", grade=NarratorGrade.RELIABLE)
        reg.record_evidence(
            "n", "physics", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, "",
            axis=EvidenceAxis.INTEGRITY,
        )
        assert reg.get_grade("n", "physics") == NarratorGrade.ACCEPTABLE

    def test_single_strike_parameter_reaches_rejected_with_enough_strikes(self):
        # With 1-per-tier, 3 strikes walk RELIABLE → ACCEPTABLE → WEAK → REJECTED.
        reg = Registry(transition_policy=ThresholdTransitionPolicy(integrity_strikes_per_tier=1))
        reg.register("n", "physics", grade=NarratorGrade.RELIABLE)
        for _ in range(3):
            reg.record_evidence(
                "n", "physics", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, "",
                axis=EvidenceAxis.INTEGRITY,
            )
        assert reg.get_grade("n", "physics") == NarratorGrade.REJECTED

    def test_strikes_per_tier_affects_only_integrity_not_precision(self):
        # Precision jarḥ still uses downgrade_threshold, independent of
        # integrity_strikes_per_tier.
        reg = Registry(transition_policy=ThresholdTransitionPolicy(integrity_strikes_per_tier=1))
        reg.register("n", "physics", grade=NarratorGrade.RELIABLE)
        # 1 precision strike < 3 → no downgrade (proves precision axis unaffected).
        reg.record_evidence(
            "n", "physics", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, "",
            axis=EvidenceAxis.PRECISION,
        )
        assert reg.get_grade("n", "physics") == NarratorGrade.RELIABLE


class TestAxisCallerBehaviour:
    """Behaviour of real callers and the untagged default (issue #9 v2).

    The axis split changes what an *untagged* jarḥ means: it is treated as
    integrity (permanent), not precision (recoverable). These tests pin that
    deliberate choice for the framework's own call sites and for the default,
    so the change is documented behaviour rather than an accident.
    """

    def test_untagged_human_review_jarh_is_permanent_by_default(self) -> None:
        """An untagged HUMAN_REVIEW jarḥ does NOT recover — conservative default.

        Automated signals (audit, eval, corroboration) default to PRECISION and
        recover. HUMAN_REVIEW is the one type that defaults to integrity: a human
        may be recording a genuine ʿadālah violation, so absent an explicit axis
        it is treated as permanent. A flood of favorable evidence cannot lift it.
        """
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("n", "physics", grade=NarratorGrade.RELIABLE)
        for _ in range(3):
            reg.record_evidence("n", "physics", EvidenceType.HUMAN_REVIEW, EvidenceAction.JARH, "")
        assert reg.get_grade("n", "physics") == NarratorGrade.ACCEPTABLE

        # A flood of favorable evidence cannot lift an integrity cap.
        for _ in range(30):
            reg.record_evidence(
                "n", "physics", EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL, ""
            )
        assert reg.get_grade("n", "physics") == NarratorGrade.ACCEPTABLE

    def test_untagged_audit_jarh_is_precision_and_recovers(self) -> None:
        """An untagged POST_HOC_AUDIT jarḥ recovers — an audit is an error signal.

        An audit detects that a served claim was *wrong* (ḍabṭ), not that it was
        a *lie* (ʿadālah). Making it permanent would make exactly the downgrades
        §8.6 warns are too aggressive permanent. So it defaults to PRECISION and
        a sustained clean streak restores the grade.
        """
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("n", "physics", grade=NarratorGrade.RELIABLE)
        for _ in range(3):
            reg.record_evidence(
                "n", "physics", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, ""
            )
        assert reg.get_grade("n", "physics") == NarratorGrade.ACCEPTABLE
        for _ in range(12):
            reg.record_evidence(
                "n", "physics", EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL, ""
            )
        assert reg.get_grade("n", "physics") == NarratorGrade.RELIABLE

    def test_flag_contradiction_is_precision_and_recovers(self) -> None:
        """A contradiction is a precision signal — windowed and recoverable.

        flag_contradiction is the corroboration path. A factual disagreement
        must not be a permanent integrity strike, or a single contradicted
        claim would cap a narrator forever (the issue #9 ratchet, back again).
        """
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("n", "physics", grade=NarratorGrade.RELIABLE)
        for _ in range(3):
            reg.flag_contradiction("n", "physics", "contradicted by independent chain")
        assert reg.get_grade("n", "physics") == NarratorGrade.ACCEPTABLE

        for _ in range(12):
            reg.record_evidence(
                "n", "physics", EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL, ""
            )
        assert reg.get_grade("n", "physics") == NarratorGrade.RELIABLE

    def test_quarantine_is_a_permanent_integrity_strike(self) -> None:
        """Quarantine logs an INTEGRITY jarḥ and lands (and stays) REJECTED."""
        reg = Registry(transition_policy=ThresholdTransitionPolicy())
        reg.register("q", "physics", grade=NarratorGrade.RELIABLE)
        reg.quarantine("q", "physics", "poisoned source")
        assert reg.get_grade("q", "physics") == NarratorGrade.REJECTED


class TestEvidenceAxisPersistence:
    """The ʿadālah/ḍabṭ axis must survive a database round-trip.

    It rides in metadata_json (no schema migration). If it were dropped, a
    reloaded integrity strike would become UNSPECIFIED — which is still
    integrity-class (conservative), so the failure direction is safe; these
    tests pin the intended lossless behaviour anyway.
    """

    def _round_trip(self, seed_fn):
        import tempfile

        from isnad.storage.sqlalchemy import (
            create_engine_from_url,
            init_db,
            reset_engine,
        )

        with tempfile.TemporaryDirectory() as d:
            url = f"sqlite:///{d}/axis.db"
            reset_engine()
            init_db(url)
            engine = create_engine_from_url(url)
            from sqlalchemy.orm import Session

            from isnad.core.registry import RegistryDB

            with Session(engine) as s:
                rdb = RegistryDB(session=s)
                seed_fn(rdb)
                rdb.flush()
                s.commit()
            with Session(engine) as s:
                rdb2 = RegistryDB(session=s)
                rdb2.load()
                grade = rdb2.registry.get_grade("n", "physics")
            reset_engine()
            return grade

    def test_integrity_strike_survives_reload_and_stays_permanent(self) -> None:
        def seed(rdb):
            rdb.registry.transition_policy = ThresholdTransitionPolicy()
            rdb.registry.register("n", "physics", grade=NarratorGrade.RELIABLE)
            # One integrity strike short of a downgrade before the reload; the
            # strike must persist so it still counts afterwards.
            for _ in range(3):
                rdb.registry.record_evidence(
                    "n",
                    "physics",
                    EvidenceType.HUMAN_REVIEW,
                    EvidenceAction.JARH,
                    "integrity",
                    axis=EvidenceAxis.INTEGRITY,
                )

        grade = self._round_trip(seed)
        # 3 integrity strikes (threshold 3) → capped one tier down, permanently.
        assert grade == NarratorGrade.ACCEPTABLE

    def test_distinct_integrity_strikes_are_not_merged_on_persist(self) -> None:
        """Integrity permanence relies on every strike surviving the flush dedup.

        RegistryDB.flush dedups on description+created_at (issue #9 finding #4).
        Distinct integrity strikes that happen to share a description must still
        be persisted as separate rows — if they collapse, integrity_jarh
        under-counts and a fabricator is under-contained after reload. This
        drives many same-description strikes through the real record_evidence
        path and asserts the reloaded count still forces REJECTED.
        """

        def seed(rdb):
            rdb.registry.transition_policy = ThresholdTransitionPolicy()
            rdb.registry.register("n", "physics", grade=NarratorGrade.RELIABLE)
            # 9 integrity strikes, all with the SAME description → threshold*3,
            # enough to force REJECTED only if none are merged away.
            for _ in range(9):
                rdb.registry.record_evidence(
                    "n",
                    "physics",
                    EvidenceType.HUMAN_REVIEW,
                    EvidenceAction.JARH,
                    "integrity violation",  # identical description on purpose
                    axis=EvidenceAxis.INTEGRITY,
                )

        grade = self._round_trip(seed)
        assert grade == NarratorGrade.REJECTED


class TestBayesianTransitionPolicy:
    """BayesianTransitionPolicy: Beta-distribution narrator grades."""

    def test_default_registry_uses_bayesian(self) -> None:
        """Registry() defaults to BayesianTransitionPolicy."""
        reg = Registry()
        assert isinstance(reg.transition_policy, BayesianTransitionPolicy)

    def test_bayesian_start_from_ungraded(self) -> None:
        """Ungraded narrator with no evidence stays UNGRADED."""
        reg = Registry()
        assert reg.get_grade("new-narrator", "physics") == NarratorGrade.UNGRADED

    def test_bayesian_one_positive_is_weak(self) -> None:
        """Beta(2,1): mean=0.67 → WEAK (just barely above 0.50)."""
        reg = Registry()
        new_grade = reg.record_evidence(
            "model-A",
            "physics",
            EvidenceType.EVAL_HARNESS,
            EvidenceAction.TADIL,
            "Passed eval",
        )
        assert new_grade == NarratorGrade.WEAK

    def test_bayesian_sustained_positive_reaches_acceptable(self) -> None:
        """5 positive + 1 adverse: Beta(7,2), mean=0.78 → ACCEPTABLE."""
        reg = Registry()
        for i in range(5):
            reg.record_evidence(
                "model-B",
                "physics",
                EvidenceType.CORROBORATION_OUTCOME,
                EvidenceAction.TADIL,
                f"Pass {i}",
            )
        reg.record_evidence(
            "model-B",
            "physics",
            EvidenceType.POST_HOC_AUDIT,
            EvidenceAction.JARH,
            "Minor error",
        )
        assert reg.get_grade("model-B", "physics") == NarratorGrade.ACCEPTABLE

    def test_bayesian_many_positives_reaches_reliable(self) -> None:
        """10 positive, 0 adverse: Beta(11,1), mean=0.917 → RELIABLE."""
        reg = Registry()
        for i in range(10):
            reg.record_evidence(
                "model-C",
                "physics",
                EvidenceType.CORROBORATION_OUTCOME,
                EvidenceAction.TADIL,
                f"Pass {i}",
            )
        assert reg.get_grade("model-C", "physics") == NarratorGrade.RELIABLE

    def test_bayesian_adverse_dominates_with_few_samples(self) -> None:
        """3 adverse, 0 positive: Beta(1,4), mean=0.20 → REJECTED."""
        reg = Registry()
        for i in range(3):
            reg.record_evidence(
                "model-D",
                "physics",
                EvidenceType.POST_HOC_AUDIT,
                EvidenceAction.JARH,
                f"Failure {i}",
            )
        assert reg.get_grade("model-D", "physics") == NarratorGrade.REJECTED

    def test_bayesian_version_bump_resets(self) -> None:
        """Version bump resets to UNGRADED regardless of evidence."""
        reg = Registry()
        reg.register("model-E", "physics", grade=NarratorGrade.RELIABLE)
        reg.bump_version("model-E", "physics", "v2")
        assert reg.get_grade("model-E", "physics") == NarratorGrade.UNGRADED

    def test_bayesian_seeding_prior(self) -> None:
        """Seeding a prior mean works."""
        policy = BayesianTransitionPolicy()
        policy.seed_grade("model-F", "physics", prior_mean=0.85, prior_weight=10.0)
        state = policy.get_state("model-F", "physics")
        # alpha = 0.85*10 + 1 = 9.5, beta = 0.15*10 + 1 = 2.5
        # mean = 9.5 / 12.0 ≈ 0.79
        assert 0.78 < state.mean < 0.80
        assert state.to_grade() == NarratorGrade.ACCEPTABLE

    def test_bayesian_can_recover_from_rejected(self) -> None:
        """Bayesian policy: REJECTED is NOT sticky — evidence can restore."""
        reg = Registry()
        reg.register("model-G", "general", grade=NarratorGrade.REJECTED)
        # The Bayesian policy derives grades from posterior, not sticky states.
        # After 1 TADIL, state is built from all evidence.
        new_grade = reg.record_evidence(
            "model-G",
            "general",
            EvidenceType.HUMAN_REVIEW,
            EvidenceAction.TADIL,
            "Human review passed",
        )
        # With 1 positive, 0 adverse → Beta(2,1), mean=0.67 → WEAK
        assert new_grade == NarratorGrade.WEAK


class TestAdalahDabtAxes:
    """ʿAdālah and ḍabṭ are two distinct axes (paper §4.2)."""

    def test_adalah_and_dabt_are_stored_separately(self) -> None:
        reg = Registry()
        reg.register(
            "source-A",
            "physics",
            adalah=AdalahGrade.HIGH,
            dabt=DabtGrade.LOW,
        )
        narrator = reg.get("source-A", "physics")
        assert narrator is not None
        assert narrator.adalah_grade == AdalahGrade.HIGH
        assert narrator.dabt_grade == DabtGrade.LOW

    def test_quarantine_sets_adalah_compromised(self) -> None:
        reg = Registry()
        reg.register("bad-source", "physics", adalah=AdalahGrade.ACCEPTABLE)
        reg.quarantine("bad-source", "physics", "Injection detected")

        narrator = reg.get("bad-source", "physics")
        assert narrator is not None
        assert narrator.grade == NarratorGrade.REJECTED
        assert narrator.adalah_grade == AdalahGrade.COMPROMISED
        assert not narrator.is_active
