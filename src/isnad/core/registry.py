"""Rijāl Registry — the (narrator, domain) graded store.

Implements the jarḥ–taʿdīl state machine (paper §4.2):
- Ordinal grading per (narrator_id, domain) — never global.
- ʿAdālah (integrity) and ḍabṭ (precision) as two distinct axes.
- Version-bump resets narrator to UNGRADED per domain.
- Grade transitions driven by named evidence types, not formulas.
- Pluggable TransitionPolicy for the transition arithmetic.

This is the computational equivalent of the classical rijāl compendium:
a living, evidence-driven registry of transmitter reliability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from isnad.core.identity import is_unknown_version, parse_narrator_id, resolve_narrator_id
from isnad.core.policies import (
    BayesianTransitionPolicy,
    BetaState,
    CalibratedThresholdPolicy,
    ThresholdTransitionPolicy,
    threshold_transition,
)
from isnad.core.volatility import FixedVolatilityPolicy
from isnad.models import (
    NarratorEvidence,
    NarratorRegistry,
)
from isnad.types import (
    AdalahGrade,
    DabtGrade,
    EvidenceAction,
    EvidenceAxis,
    EvidenceType,
    FreshnessStatus,
    NarratorGrade,
    NarratorType,
    TransitionPolicy,
    VolatilityPolicy,
    default_axis_for,
)

# Re-exported for backward compatibility: these used to live in registry.py.
# They now live in policies.py but remain importable from here.
__all__ = [
    "BayesianTransitionPolicy",
    "BetaState",
    "CalibratedThresholdPolicy",
    "ThresholdTransitionPolicy",
    "threshold_transition",
]

# ===========================================================================
# Grade freshness — the time-decay half of the grade-expiry fix
# ===========================================================================

# One-tier staleness downgrade across the positive-trust ordinal.
# REJECTED is active containment and never decays; WEAK reverts to
# UNGRADED (no longer trusted until re-earned).
_STALE_DOWNGRADE: dict[NarratorGrade, NarratorGrade] = {
    NarratorGrade.RELIABLE: NarratorGrade.ACCEPTABLE,
    NarratorGrade.ACCEPTABLE: NarratorGrade.WEAK,
    NarratorGrade.WEAK: NarratorGrade.UNGRADED,
}


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a datetime to timezone-aware UTC.

    SQLite stores timezone-aware columns as naive datetimes, so values
    reloaded from the DB need an explicit UTC zone before comparison.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass
class GradeWithFreshness:
    """A narrator grade plus its time-decay state.

    `grade` is the *effective* (possibly degraded) grade to use at lookup
    time.  `freshness`/`needs_recheck` say why, so a caller can surface a
    caveat or trigger a re-validation before relying on the grade.
    """

    grade: NarratorGrade
    freshness: FreshnessStatus
    needs_recheck: bool
    graded_at: datetime | None = None
    valid_until: datetime | None = None


# ===========================================================================
# Narrator wrapper — in-memory narrator with grade + evidence
# ===========================================================================


class Narrator:
    """A narrator with its domain-conditioned grade and evidence log."""

    def __init__(
        self,
        narrator_id: str,
        domain_tag: str,
        narrator_type: NarratorType = NarratorType.MODEL,
        grade: NarratorGrade = NarratorGrade.UNGRADED,
        adalah_grade: AdalahGrade = AdalahGrade.UNASSESSED,
        dabt_grade: DabtGrade = DabtGrade.UNASSESSED,
        known_error_rate: float | None = None,
        model_version: str | None = None,
        model_family: str | None = None,
        upstream_source: str | None = None,
        is_active: bool = True,
        graded_at: datetime | None = None,
        valid_until: datetime | None = None,
    ):
        self.narrator_id = narrator_id
        self.domain_tag = domain_tag
        self.narrator_type = narrator_type
        self.grade = grade
        self.adalah_grade = adalah_grade
        self.dabt_grade = dabt_grade
        self.known_error_rate = known_error_rate
        self.model_version = model_version
        self.model_family = model_family
        self.upstream_source = upstream_source
        self.is_active = is_active
        self.graded_at = graded_at
        self.valid_until = valid_until
        self.evidence_log: list[dict[str, object]] = []

    def add_evidence(
        self,
        evidence_type: EvidenceType,
        action: EvidenceAction,
        description: str = "",
        metadata: dict[str, object] | None = None,
        axis: EvidenceAxis = EvidenceAxis.UNSPECIFIED,
    ) -> None:
        """Log an evidence entry.

        ``axis`` records whether an adverse (jarḥ) event bears on the narrator's
        integrity (ʿadālah) or precision (ḍabṭ). It governs whether threshold
        policies may let the evidence age out of their window; UNSPECIFIED is
        treated conservatively as integrity-class (never forgotten). See
        ``EvidenceAxis``.
        """
        entry: dict[str, object] = {
            "uid": str(uuid4()),  # stable identity for collision-proof persistence dedup
            "evidence_type": evidence_type.value,
            "action": action.value,
            "axis": axis.value,
            "description": description,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.evidence_log.append(entry)

    @property
    def key(self) -> tuple[str, str]:
        """The composite key (narrator_id, domain_tag)."""
        return (self.narrator_id, self.domain_tag)


# ===========================================================================
# Registry — the in-memory (narrator, domain) graded store
# ===========================================================================


class Registry:
    """The Rijāl Registry: stores and manages narrator grades per domain.

    This is the pure-logic registry — usable without a database.  For
    persistence, use RegistryDB backed by SQLAlchemy.
    """

    def __init__(
        self,
        transition_policy: TransitionPolicy | None = None,
        volatility_policy: VolatilityPolicy | None = None,
    ):
        self._narrators: dict[tuple[str, str], Narrator] = {}
        self._alias_graded: dict[tuple[str, str], set[str]] = {}
        self.transition_policy: TransitionPolicy = transition_policy or BayesianTransitionPolicy()
        self.volatility_policy: VolatilityPolicy = volatility_policy or FixedVolatilityPolicy()

    # ------------------------------------------------------------------
    # Alias index (graded versions per alias+domain)
    # ------------------------------------------------------------------

    @staticmethod
    def _alias_for(narrator_id: str) -> str:
        return parse_narrator_id(narrator_id)[0]

    def _index_set_grade(
        self,
        narrator_id: str,
        domain_tag: str,
        grade: NarratorGrade,
    ) -> None:
        alias = self._alias_for(narrator_id)
        key = (alias, domain_tag)
        if grade == NarratorGrade.UNGRADED:
            bucket = self._alias_graded.get(key)
            if bucket is not None:
                bucket.discard(narrator_id)
                if not bucket:
                    del self._alias_graded[key]
        else:
            self._alias_graded.setdefault(key, set()).add(narrator_id)

    def _rebuild_alias_index(self) -> None:
        """Rebuild graded-alias index from all narrators (e.g. after DB load)."""
        self._alias_graded.clear()
        for narrator in self._narrators.values():
            self._index_set_grade(narrator.narrator_id, narrator.domain_tag, narrator.grade)

    def has_graded_sibling_versions(
        self,
        alias: str,
        domain: str,
        exclude_resolved: str,
    ) -> bool:
        """True if another graded registry entry exists for the same alias in domain."""
        graded = self._alias_graded.get((alias, domain), set())
        return any(nid != exclude_resolved for nid in graded)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(
        self,
        narrator_id: str,
        domain_tag: str,
        narrator_type: NarratorType = NarratorType.MODEL,
        grade: NarratorGrade = NarratorGrade.UNGRADED,
        adalah: AdalahGrade = AdalahGrade.UNASSESSED,
        dabt: DabtGrade = DabtGrade.UNASSESSED,
        known_error_rate: float | None = None,
        model_version: str | None = None,
        model_family: str | None = None,
        upstream_source: str | None = None,
        graded_at: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> Narrator:
        """Register a new narrator or return existing one.

        Registering with an explicit (non-UNGRADED) grade starts the
        freshness clock: the grade is treated as validated right now and
        expires after the volatility policy's TTL.  Passing an explicit
        `graded_at` (e.g. for deterministic tests) starts the clock from
        that instant; passing both `graded_at` and `valid_until` (e.g. from
        a DB load) preserves them exactly.
        """
        key = (narrator_id, domain_tag)
        if key not in self._narrators:
            if grade is not NarratorGrade.UNGRADED and valid_until is None:
                if graded_at is None:
                    graded_at = datetime.now(UTC)
                valid_until = self.volatility_policy.valid_until(
                    narrator_type, domain_tag, now=graded_at
                )
            self._narrators[key] = Narrator(
                narrator_id=narrator_id,
                domain_tag=domain_tag,
                narrator_type=narrator_type,
                grade=grade,
                adalah_grade=adalah,
                dabt_grade=dabt,
                known_error_rate=known_error_rate,
                model_version=model_version,
                model_family=model_family,
                upstream_source=upstream_source,
                graded_at=graded_at,
                valid_until=valid_until,
            )
            self._index_set_grade(narrator_id, domain_tag, grade)
        return self._narrators[key]

    def get(self, narrator_id: str, domain_tag: str) -> Narrator | None:
        """Look up a narrator by (narrator_id, domain_tag)."""
        return self._narrators.get((narrator_id, domain_tag))

    def effective_grade(
        self,
        narrator_id: str,
        domain_tag: str,
        now: datetime | None = None,
    ) -> GradeWithFreshness:
        """The time-decayed grade to use at lookup time (the expiry fix).

        Three windows, defined by the volatility policy:
        - FRESH:  within the TTL — the stored grade is returned as-is.
        - STALE:  inside the grace window at the end of the TTL — the grade
          is downgraded one tier and flagged `needs_recheck`.
        - EXPIRED: past best-before — reverts to UNGRADED until re-earned.

        REJECTED (active containment) never decays.  Grades without a
        freshness clock (never graded, or legacy/indefinite rows) are
        returned unchanged.

        Args:
            narrator_id: The narrator identifier.
            domain_tag: The domain key.
            now: Reference time; defaults to the current UTC time.  Used to
                make the decay deterministic in tests.

        Returns:
            A GradeWithFreshness with the effective grade and its state.
        """
        if now is None:
            now = datetime.now(UTC)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        narrator = self.get(narrator_id, domain_tag)
        if narrator is None:
            return GradeWithFreshness(
                grade=NarratorGrade.UNGRADED,
                freshness=FreshnessStatus.EXPIRED,
                needs_recheck=False,
            )

        grade = narrator.grade
        # REJECTED is active containment — never time-decayed.
        if grade == NarratorGrade.REJECTED:
            return GradeWithFreshness(
                grade=grade,
                freshness=FreshnessStatus.FRESH,
                needs_recheck=False,
                graded_at=_as_utc(narrator.graded_at),
                valid_until=_as_utc(narrator.valid_until),
            )

        # No clock → nothing to decay (never graded, or legacy/indefinite row).
        if grade == NarratorGrade.UNGRADED or narrator.valid_until is None:
            return GradeWithFreshness(
                grade=grade,
                freshness=FreshnessStatus.FRESH,
                needs_recheck=False,
                graded_at=_as_utc(narrator.graded_at),
                valid_until=_as_utc(narrator.valid_until),
            )

        graded_at = _as_utc(narrator.graded_at)
        valid_until = _as_utc(narrator.valid_until)
        if graded_at is None:
            return GradeWithFreshness(
                grade=grade,
                freshness=FreshnessStatus.FRESH,
                needs_recheck=False,
                graded_at=None,
                valid_until=valid_until,
            )

        stale_start = valid_until - self.volatility_policy.stale_window(
            narrator.narrator_type, narrator.domain_tag
        )
        if now > valid_until:
            return GradeWithFreshness(
                grade=NarratorGrade.UNGRADED,
                freshness=FreshnessStatus.EXPIRED,
                needs_recheck=True,
                graded_at=graded_at,
                valid_until=valid_until,
            )
        if now >= stale_start:
            return GradeWithFreshness(
                grade=_STALE_DOWNGRADE.get(grade, grade),
                freshness=FreshnessStatus.STALE,
                needs_recheck=True,
                graded_at=graded_at,
                valid_until=valid_until,
            )
        return GradeWithFreshness(
            grade=grade,
            freshness=FreshnessStatus.FRESH,
            needs_recheck=False,
            graded_at=graded_at,
            valid_until=valid_until,
        )

    def get_grade(
        self,
        narrator_id: str,
        domain_tag: str,
        now: datetime | None = None,
    ) -> NarratorGrade:
        """Return the *effective* (time-decayed) grade, UNGRADED if unknown.

        Time-aware: a grade past its best-before is no longer trusted at
        lookup time, even though the stored grade is preserved.  See
        effective_grade() for the window logic.
        """
        return self.effective_grade(narrator_id, domain_tag, now=now).grade

    def needs_recheck(
        self,
        narrator_id: str,
        domain_tag: str,
        now: datetime | None = None,
    ) -> bool:
        """True when the grade is in its stale window or already expired."""
        return self.effective_grade(narrator_id, domain_tag, now=now).needs_recheck

    def get_adalah_grade(self, narrator_id: str, domain_tag: str) -> AdalahGrade:
        """Return a narrator's ʿadālah (integrity) grade, defaulting to UNASSESSED.

        This is the axis distinct from the precision-oriented NarratorGrade
        (paper §4.2): a narrator can be generally accurate (good NarratorGrade)
        while its integrity has been separately compromised (issue #11 —
        chain-integrity and origin-strength must be distinguishable, not
        collapsed into one grade).
        """
        narrator = self.get(narrator_id, domain_tag)
        return narrator.adalah_grade if narrator else AdalahGrade.UNASSESSED

    def get_grade_for_link(
        self,
        narrator_id: str,
        domain_tag: str,
        version: str | None,
    ) -> NarratorGrade:
        """Return grade for a chain link, resolving alias@version when version is known."""
        resolved = resolve_narrator_id(narrator_id, version)
        return self.get_grade(resolved, domain_tag)

    def register_versioned(
        self,
        narrator_id: str,
        domain_tag: str,
        version: str | None,
        *,
        narrator_type: NarratorType = NarratorType.MODEL,
        grade: NarratorGrade = NarratorGrade.UNGRADED,
        adalah: AdalahGrade = AdalahGrade.UNASSESSED,
        dabt: DabtGrade = DabtGrade.UNASSESSED,
        known_error_rate: float | None = None,
        model_family: str | None = None,
        upstream_source: str | None = None,
    ) -> Narrator:
        """Register a narrator under alias@version when version is supplied."""
        resolved = resolve_narrator_id(narrator_id, version)
        return self.register(
            resolved,
            domain_tag,
            narrator_type=narrator_type,
            grade=grade,
            adalah=adalah,
            dabt=dabt,
            known_error_rate=known_error_rate,
            model_version=version if not is_unknown_version(version) else None,
            model_family=model_family,
            upstream_source=upstream_source,
        )

    def get_metadata(self, narrator_id: str, domain_tag: str) -> dict[str, object]:
        """Return metadata for correlation detection etc."""
        narrator = self.get(narrator_id, domain_tag)
        if narrator is None:
            return {}
        return {
            "model_family": narrator.model_family,
            "upstream_source": narrator.upstream_source,
            "narrator_type": narrator.narrator_type.value,
            "model_version": narrator.model_version,
        }

    # ------------------------------------------------------------------
    # jarḥ–taʿdīl state machine
    # ------------------------------------------------------------------

    def record_evidence(
        self,
        narrator_id: str,
        domain_tag: str,
        evidence_type: EvidenceType,
        action: EvidenceAction,
        description: str = "",
        metadata: dict[str, object] | None = None,
        axis: EvidenceAxis | None = None,
    ) -> NarratorGrade:
        """Log evidence against a narrator and compute the new grade.

        This is the jarḥ–taʿdīl loop: log evidence, re-evaluate grade.
        The actual transition logic is delegated to the pluggable
        TransitionPolicy so implementations can swap the arithmetic
        without touching the registry structure.

        ``axis`` marks an adverse event as bearing on integrity (ʿadālah) or
        precision (ḍabṭ); threshold policies only let *precision* jarḥ age out
        of their window. When omitted, the axis is derived from the evidence
        type (``default_axis_for``): unambiguously-precision types resolve to
        PRECISION, the rest to UNSPECIFIED (integrity-class). See
        ``EvidenceAxis``.

        Returns the new narrator grade.
        """
        resolved_axis = default_axis_for(evidence_type) if axis is None else axis
        narrator = self.register(narrator_id, domain_tag)
        narrator.add_evidence(evidence_type, action, description, metadata, resolved_axis)

        new_grade = self.transition_policy.evaluate_transition(
            current_grade=narrator.grade,
            evidence_history=narrator.evidence_log[:-1],  # all prior
            new_evidence=narrator.evidence_log[-1],
        )
        narrator.grade = new_grade
        self._index_set_grade(narrator_id, domain_tag, new_grade)

        # Every evidence event (re)validates the grade → restart the clock.
        # UNGRADED and REJECTED carry no clock: UNGRADED is unassessed,
        # REJECTED is active containment and never time-decays.
        if new_grade in (NarratorGrade.UNGRADED, NarratorGrade.REJECTED):
            narrator.graded_at = None
            narrator.valid_until = None
        else:
            narrator.graded_at = datetime.now(UTC)
            narrator.valid_until = self.volatility_policy.valid_until(
                narrator.narrator_type, narrator.domain_tag, now=narrator.graded_at
            )
        return new_grade

    # ------------------------------------------------------------------
    # Version bump
    # ------------------------------------------------------------------

    def bump_version(
        self,
        narrator_id: str,
        domain_tag: str,
        new_version: str,
    ) -> None:
        """Model-version bump resets the narrator to UNGRADED per domain.

        Paper §4.2: version drift is a new narrator, not inherited reputation.
        """
        narrator = self.register(narrator_id, domain_tag)
        narrator.model_version = new_version
        narrator.grade = NarratorGrade.UNGRADED
        narrator.adalah_grade = AdalahGrade.UNASSESSED
        narrator.dabt_grade = DabtGrade.UNASSESSED
        narrator.known_error_rate = None
        # A version bump is a new narrator: no reputation, no freshness clock.
        narrator.graded_at = None
        narrator.valid_until = None
        narrator.add_evidence(
            EvidenceType.VERSION_BUMP,
            EvidenceAction.NEUTRAL,
            f"Version bumped to {new_version}; grade reset to UNGRADED",
        )
        self._index_set_grade(narrator_id, domain_tag, NarratorGrade.UNGRADED)

    # ------------------------------------------------------------------
    # Quarantine
    # ------------------------------------------------------------------

    def quarantine(self, narrator_id: str, domain_tag: str, reason: str = "") -> None:
        """Quarantine a narrator: set grade to REJECTED, ʿadālah to COMPROMISED.

        Paper §4.4: the mawḍūʿ tier is active containment, not a passive label.
        """
        narrator = self.register(narrator_id, domain_tag)
        narrator.grade = NarratorGrade.REJECTED
        narrator.adalah_grade = AdalahGrade.COMPROMISED
        narrator.is_active = False
        # Quarantine is active containment with no time limit: no clock.
        narrator.graded_at = None
        narrator.valid_until = None
        narrator.add_evidence(
            EvidenceType.HUMAN_REVIEW,
            EvidenceAction.JARH,
            f"Quarantined: {reason}" if reason else "Quarantined",
            axis=EvidenceAxis.INTEGRITY,  # the archetypal ʿadālah strike — permanent
        )
        self._index_set_grade(narrator_id, domain_tag, NarratorGrade.REJECTED)

    # ------------------------------------------------------------------
    # Event-driven invalidation + freshness renewal (the expiry fix)
    # ------------------------------------------------------------------

    def flag_contradiction(
        self,
        narrator_id: str,
        domain_tag: str,
        description: str = "",
    ) -> NarratorGrade:
        """Event-driven invalidation: log an independent-chain contradiction.

        Part 2 of the fix.  A contradiction between a narrator's claim and
        an independent chain is adverse (jarḥ) evidence, which the
        TransitionPolicy weighs toward a downgrade.  It also restarts the
        freshness clock (see record_evidence), so the contradiction is
        immediately the state we grade from — not something we rediscover
        after a TTL expiry.

        This is a *precision* (ḍabṭ) signal — a factual disagreement, not an
        integrity violation — so it is windowed and recoverable, not permanent.
        A caller who has evidence that the contradiction reflects deliberate
        manipulation should log an INTEGRITY-axis jarḥ (or quarantine) instead.

        Returns the new narrator grade.
        """
        return self.record_evidence(
            narrator_id,
            domain_tag,
            EvidenceType.CORROBORATION_OUTCOME,
            EvidenceAction.JARH,
            description or "Claim contradicted by an independent chain",
            axis=EvidenceAxis.PRECISION,
        )

    def renew_grade(
        self,
        narrator_id: str,
        domain_tag: str,
        reason: str = "corroboration",
    ) -> bool:
        """Renew a grade's freshness window without changing the grade.

        Part 3 of the fix: corroboration is a proxy freshness signal.  When
        independent chains keep agreeing with a narrator, the world has not
        changed on them — so we extend the window instead of letting the
        clock expire.  Does nothing for UNGRADED or REJECTED narrators.

        Returns True if the window was renewed.
        """
        narrator = self.get(narrator_id, domain_tag)
        if narrator is None:
            return False
        if narrator.grade in (NarratorGrade.UNGRADED, NarratorGrade.REJECTED):
            return False
        narrator.graded_at = datetime.now(UTC)
        narrator.valid_until = self.volatility_policy.valid_until(
            narrator.narrator_type, narrator.domain_tag, now=narrator.graded_at
        )
        # Record the renewal as NEUTRAL — it must NOT feed the upgrade
        # thresholds.  Writing CORROBORATION_OUTCOME + TADIL here (as the
        # original PR did) silently manufactured upgrade evidence: five
        # renewals plus one neutral audit promoted a WEAK narrator to
        # ACCEPTABLE with nothing ever evaluating its correctness.  A
        # freshness renewal extends the clock, nothing more.
        narrator.add_evidence(
            EvidenceType.CORROBORATION_OUTCOME,
            EvidenceAction.NEUTRAL,
            f"Grade freshness renewed via {reason}; trust window restarted",
        )
        return True

    # ------------------------------------------------------------------
    # Bulk access
    # ------------------------------------------------------------------

    def all_narrators(self) -> list[Narrator]:
        return list(self._narrators.values())

    def __len__(self) -> int:
        return len(self._narrators)

    def __contains__(self, key: tuple[str, str]) -> bool:
        return key in self._narrators


# ===========================================================================
# Persistence-aware registry (SQLAlchemy-backed)
# ===========================================================================


class RegistryDB:
    """Database-backed narrator registry.

    Wraps the Registry in-memory store with SQLAlchemy persistence.
    """

    def __init__(
        self,
        session: Session,
        transition_policy: TransitionPolicy | None = None,
    ):
        self.session = session
        self.registry = Registry(transition_policy=transition_policy or BayesianTransitionPolicy())

    def load(self) -> None:
        """Load all narrators from the database into the in-memory registry."""
        rows = self.session.query(NarratorRegistry).all()
        for row in rows:
            narrator = self.registry.register(
                narrator_id=row.narrator_id,
                domain_tag=row.domain_tag,
                narrator_type=NarratorType(row.narrator_type),
                grade=NarratorGrade(row.grade),
                adalah=AdalahGrade(row.adalah_grade),
                dabt=DabtGrade(row.dabt_grade),
                known_error_rate=row.known_error_rate,
                model_version=row.model_version,
                model_family=row.model_family,
                upstream_source=row.upstream_source,
                graded_at=row.graded_at,
                valid_until=row.valid_until,
            )
            # Preserve stored clocks exactly.  register() starts a fresh clock
            # for non-UNGRADED grades without one, which would clobber legacy
            # rows that carry a grade but no graded_at/valid_until (NULL = never
            # expires).  Restore the persisted values so loading is lossless.
            narrator.graded_at = row.graded_at
            narrator.valid_until = row.valid_until
            # Load evidence log. The axis (ʿadālah/ḍabṭ) rides in metadata_json
            # until it earns a dedicated column, so integrity vs precision
            # survives a round-trip. Missing axis → UNSPECIFIED (conservative:
            # treated as integrity, non-forgettable).
            for ev in row.evidence_log:
                meta = dict(ev.metadata_json or {})
                axis = EvidenceAxis(str(meta.pop("__axis__", EvidenceAxis.UNSPECIFIED.value)))
                uid = str(meta.pop("__uid__", ""))
                narrator.add_evidence(
                    EvidenceType(ev.evidence_type),
                    EvidenceAction(ev.action),
                    ev.description,
                    meta,
                    axis,
                )
                # Preserve the persisted uid so a re-flush does not duplicate it.
                if uid:
                    narrator.evidence_log[-1]["uid"] = uid
        self.registry._rebuild_alias_index()

    def flush(self) -> None:
        """Persist all narrators and their evidence to the database."""
        for narrator in self.registry.all_narrators():
            row = (
                self.session
                .query(NarratorRegistry)
                .filter_by(
                    narrator_id=narrator.narrator_id,
                    domain_tag=narrator.domain_tag,
                )
                .first()
            )
            if row is None:
                row = NarratorRegistry(
                    narrator_id=narrator.narrator_id,
                    domain_tag=narrator.domain_tag,
                )
                self.session.add(row)

            row.narrator_type = narrator.narrator_type.value
            row.grade = narrator.grade.value
            row.adalah_grade = narrator.adalah_grade.value
            row.dabt_grade = narrator.dabt_grade.value
            row.known_error_rate = narrator.known_error_rate
            row.model_version = narrator.model_version
            row.model_family = narrator.model_family
            row.upstream_source = narrator.upstream_source
            row.is_active = narrator.is_active
            row.graded_at = narrator.graded_at
            row.valid_until = narrator.valid_until

            # Append new evidence entries. Dedup on each entry's stable uid so
            # distinct strikes are never merged (issue #9: integrity permanence
            # depends on every strike surviving — a description+timestamp key
            # could collapse same-instant same-description strikes).
            existing_ids = {str((e.metadata_json or {}).get("__uid__")) for e in row.evidence_log}
            for entry in narrator.evidence_log:
                uid = str(entry.get("uid", ""))
                if uid and uid in existing_ids:
                    continue
                # Persist axis + uid inside metadata_json (no schema migration).
                meta = dict(entry.get("metadata", {}) or {})
                meta["__axis__"] = str(entry.get("axis", EvidenceAxis.UNSPECIFIED.value))
                meta["__uid__"] = uid
                ev = NarratorEvidence(
                    narrator_id=narrator.narrator_id,
                    domain_tag=narrator.domain_tag,
                    evidence_type=entry.get("evidence_type", ""),
                    action=entry.get("action", ""),
                    description=str(entry.get("description", "")),
                    metadata_json=meta,
                )
                self.session.add(ev)
                existing_ids.add(uid)

        self.session.flush()
