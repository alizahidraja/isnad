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
    EvidenceProvenance,
    EvidenceType,
    FreshnessStatus,
    NarratorGrade,
    NarratorType,
    Role,
    TransitionPolicy,
    VolatilityPolicy,
    default_axis_for,
    provenance_of,
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


def _evidence_time(entry: dict[str, object]) -> datetime | None:
    """Parse an evidence entry's ``created_at`` (ISO 8601) or return None.

    Used by period-sliced re-derivation (issue #43) to slice the append-only
    evidence log by a past instant.
    """
    raw = entry.get("created_at", "")
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None
    # Normalise to UTC-aware: in-memory entries are aware, but a SQLite
    # round-trip returns naive datetimes (see _as_utc).
    if t.tzinfo is None:
        return t.replace(tzinfo=UTC)
    return t.astimezone(UTC)


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


@dataclass
class EvidenceProvenanceSummary:
    """Where a narrator's grade came from — priors vs observed instances.

    Issue #6: a grade built on benchmark priors is a *population estimate*;
    a grade built on observed in-pipeline instances is a *record about this
    transmitter*.  Classical rijāl graded on observed instances, never priors.

    This summary lets a caller answer "is this narrator's grade an assumption
    or an observation?" — a signal about the grade, not a new grading axis.

    `prior_only` is the state issue #6 flags as dangerous: a grade with zero
    observed-instance evidence is an unvalidated assumption, however
    confident the benchmark prior looks.
    """

    prior_count: int = 0
    observed_count: int = 0
    human_count: int = 0
    meta_count: int = 0

    @property
    def total_grade_evidence(self) -> int:
        """Count of evidence entries that actually bear on the grade (excl. meta)."""
        return self.prior_count + self.observed_count + self.human_count

    @property
    def prior_only(self) -> bool:
        """True when the grade rests on priors with no observed instance."""
        return self.observed_count == 0 and self.human_count == 0 and self.prior_count > 0

    @property
    def observation_backed(self) -> bool:
        """True when at least one observed in-pipeline instance exists."""
        return self.observed_count > 0


# ===========================================================================
# Narrator wrapper — in-memory narrator with grade + evidence
# ===========================================================================


class Narrator:
    """A narrator with its domain-conditioned grade and evidence log.

    ``role`` is ``None`` for the default/integrity record (one per
    ``(narrator, domain)``) and a ``Role`` for role-scoped *precision* records
    (one per ``(narrator, role, domain)``).  Integrity (ʿadālah) is only ever
    stored on the default record and is shared across roles.
    """

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
        role: Role | None = None,
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
        self.role = role
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
        self._role_records: dict[tuple[str, str, str], Narrator] = {}
        self._alias_graded: dict[tuple[str, str], set[str]] = {}
        self.transition_policy: TransitionPolicy = transition_policy or BayesianTransitionPolicy()
        self.volatility_policy: VolatilityPolicy = volatility_policy or FixedVolatilityPolicy()

    # ------------------------------------------------------------------
    # Alias index (graded versions per alias+domain)
    # ------------------------------------------------------------------

    @staticmethod
    def _alias_for(narrator_id: str) -> str:
        return parse_narrator_id(narrator_id)[0]

    def _narrator_is_graded(self, narrator_id: str, domain_tag: str) -> bool:
        """True if ANY record (default or any role) for this (narrator, domain) is graded.

        A narrator counts as "graded" for version-drift purposes if any of its
        records holds a non-UNGRADED grade — otherwise a role record's UNGRADED
        would wrongly mask a graded default record (or vice versa).
        """
        default = self._narrators.get((narrator_id, domain_tag))
        if default is not None and default.grade != NarratorGrade.UNGRADED:
            return True
        for (nid, _role, dom), rec in self._role_records.items():
            if nid == narrator_id and dom == domain_tag and rec.grade != NarratorGrade.UNGRADED:
                return True
        return False

    def _index_set_grade(self, narrator_id: str, domain_tag: str) -> None:
        """Refresh the alias index for a narrator across all its records."""
        alias = self._alias_for(narrator_id)
        key = (alias, domain_tag)
        if self._narrator_is_graded(narrator_id, domain_tag):
            self._alias_graded.setdefault(key, set()).add(narrator_id)
        else:
            bucket = self._alias_graded.get(key)
            if bucket is not None:
                bucket.discard(narrator_id)
                if not bucket:
                    del self._alias_graded[key]

    def _rebuild_alias_index(self) -> None:
        """Rebuild graded-alias index from all narrators (e.g. after DB load)."""
        self._alias_graded.clear()
        seen: set[tuple[str, str]] = set()
        for narrator in [*self._narrators.values(), *self._role_records.values()]:
            key = (narrator.narrator_id, narrator.domain_tag)
            if key not in seen:
                seen.add(key)
                self._index_set_grade(narrator.narrator_id, narrator.domain_tag)

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

    @staticmethod
    def _role_key(narrator_id: str, role: Role, domain_tag: str) -> tuple[str, str, str]:
        """Storage key for a role-scoped precision record."""
        return (narrator_id, role.value, domain_tag)

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
        role: Role | None = None,
    ) -> Narrator:
        """Register a new narrator or return the existing one.

        ``role=None`` (default) registers the integrity + default-precision
        record keyed ``(narrator, domain)`` — the legacy behaviour.  ``role``
        given registers a *role-scoped precision* record keyed
        ``(narrator, role, domain)``.  Identity (narrator_type, version,
        family, upstream) is inherited from the default record when it exists,
        and integrity (ʿadālah) is always read from the default record, never
        written to a role record.

        Registering with an explicit (non-UNGRADED) grade starts the freshness
        clock: the grade is treated as validated right now and expires after
        the volatility policy's TTL.
        """
        if role is None:
            store = self._narrators
            key: tuple[str, str] | tuple[str, str, str] = (narrator_id, domain_tag)
        else:
            store = self._role_records
            key = self._role_key(narrator_id, role, domain_tag)
            # Identity is per-narrator, not per-role.  Inherit narrator_type
            # (drives the volatility TTL), model_version/family/upstream from
            # the default record when one exists, so a role record never
            # drifts its identity or decay window.
            default = self._narrators.get((narrator_id, domain_tag))
            if default is not None:
                narrator_type = default.narrator_type
                model_version = default.model_version
                model_family = default.model_family
                upstream_source = default.upstream_source

        if key not in store:
            if grade is not NarratorGrade.UNGRADED and valid_until is None:
                if graded_at is None:
                    graded_at = datetime.now(UTC)
                valid_until = self.volatility_policy.valid_until(
                    narrator_type, domain_tag, now=graded_at
                )
            store[key] = Narrator(
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
                role=role,
            )
            self._index_set_grade(narrator_id, domain_tag)
        return store[key]

    def get(self, narrator_id: str, domain_tag: str, role: Role | None = None) -> Narrator | None:
        """Look up a narrator by ``(narrator_id, domain_tag[, role])``.

        ``role=None`` returns the default/integrity record; a ``Role`` returns
        the role-scoped precision record (if one exists).
        """
        if role is None:
            return self._narrators.get((narrator_id, domain_tag))
        return self._role_records.get(self._role_key(narrator_id, role, domain_tag))

    def effective_grade(
        self,
        narrator_id: str,
        domain_tag: str,
        role: Role | None = None,
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

        ``role=None`` returns the default record's grade (legacy behaviour).
        ``role=<Role>`` returns the role's precision grade, floored by the
        shared integrity state (a quarantined narrator is REJECTED in every
        role).

        Args:
            narrator_id: The narrator identifier.
            domain_tag: The domain key.
            role: Optional task role for per-role precision grading (issue #3).
            now: Reference time; defaults to the current UTC time.  Used to
                make the decay deterministic in tests.

        Returns:
            A GradeWithFreshness with the effective grade and its state.
        """
        if now is None:
            now = datetime.now(UTC)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        if role is not None:
            return self._effective_role_grade(narrator_id, role, domain_tag, now)

        narrator = self.get(narrator_id, domain_tag)
        if narrator is None:
            return GradeWithFreshness(
                grade=NarratorGrade.UNGRADED,
                freshness=FreshnessStatus.EXPIRED,
                needs_recheck=False,
            )
        return self._decay_record(narrator, now)

    def _effective_role_grade(
        self,
        narrator_id: str,
        role: Role,
        domain_tag: str,
        now: datetime,
    ) -> GradeWithFreshness:
        """Effective grade for a role: precision floored by shared integrity.

        Integrity (ʿadālah) is per (narrator, domain) and spans roles.  The
        floor is deliberately conservative: a narrator whose default record is
        COMPROMISED **or** REJECTED is REJECTED in every role, regardless of
        any role-scoped precision evidence.  This errs on the side of
        under-trust (the framework's bias) — it can over-reject a role whose
        own precision is good, but it can never let a quarantined or
        REJECTED narrator slip through on a role's precision.
        """
        default = self.get(narrator_id, domain_tag)
        if default is not None and (
            default.adalah_grade == AdalahGrade.COMPROMISED
            or default.grade == NarratorGrade.REJECTED
        ):
            return GradeWithFreshness(
                grade=NarratorGrade.REJECTED,
                freshness=FreshnessStatus.FRESH,
                needs_recheck=False,
                graded_at=_as_utc(default.graded_at),
                valid_until=_as_utc(default.valid_until),
            )

        role_rec = self.get(narrator_id, domain_tag, role=role)
        if role_rec is not None:
            return self._decay_record(role_rec, now)

        if default is not None:
            return self._decay_record(default, now)

        return GradeWithFreshness(
            grade=NarratorGrade.UNGRADED,
            freshness=FreshnessStatus.EXPIRED,
            needs_recheck=False,
        )

    def _decay_record(self, narrator: Narrator, now: datetime) -> GradeWithFreshness:
        """Apply the freshness windows to a single narrator record."""
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
        role: Role | None = None,
        now: datetime | None = None,
    ) -> NarratorGrade:
        """Return the *effective* (time-decayed) grade, UNGRADED if unknown.

        Time-aware: a grade past its best-before is no longer trusted at
        lookup time, even though the stored grade is preserved.  See
        effective_grade() for the window logic.  ``role`` selects a
        role-scoped precision grade (issue #3).
        """
        return self.effective_grade(narrator_id, domain_tag, role=role, now=now).grade

    def get_grade_as_of(
        self,
        narrator_id: str,
        domain_tag: str,
        as_of: datetime,
        role: Role | None = None,
    ) -> NarratorGrade:
        """Re-derive a narrator's grade as of a past instant (period-sliced).

        This is the ikhtilāṭ remedy (issue #43): a narrator who was sound and
        then declined — or was quarantined — has their record *dated*, not
        discarded.  Querying ``as_of`` before the decline returns the
        pre-decline grade; after it, the post-decline grade.  The grade is
        recomputed from the append-only evidence log up to ``as_of``; it does
        not read the narrator's current (mutated) grade, so it is an honest
        reconstruction, not a guess.

        A quarantine is replayed as the direct REJECTED + COMPROMISED action it
        recorded (via the ``__quarantine__`` marker), so the slice after a
        quarantine is REJECTED, matching live behaviour.
        """
        narrator = self.get(narrator_id, domain_tag, role=role)
        if narrator is None:
            return NarratorGrade.UNGRADED
        as_of = as_of.replace(tzinfo=UTC) if as_of.tzinfo is None else as_of.astimezone(UTC)
        filtered = [
            e
            for e in narrator.evidence_log
            if _evidence_time(e) is not None and _evidence_time(e) <= as_of
        ]
        return self._grade_from_evidence(filtered)

    def _grade_from_evidence(self, evidence: list[dict[str, object]]) -> NarratorGrade:
        """Replay the transition policy over an ordered evidence log.

        Starts from UNGRADED and applies each entry in order, tracking the
        integrity (quarantine) state.  A ``__quarantine__`` entry is replayed
        as the direct REJECTED + COMPROMISED action it records, mirroring
        ``quarantine()``.
        """
        grade = NarratorGrade.UNGRADED
        compromised = False
        for i, entry in enumerate(evidence):
            if (entry.get("metadata", {}) or {}).get("__quarantine__"):
                grade = NarratorGrade.REJECTED
                compromised = True
                continue
            grade = self.transition_policy.evaluate_transition(
                current_grade=grade,
                evidence_history=evidence[:i],
                new_evidence=entry,
                is_compromised=compromised,
            )
        return grade

    def needs_recheck(
        self,
        narrator_id: str,
        domain_tag: str,
        role: Role | None = None,
        now: datetime | None = None,
    ) -> bool:
        """True when the grade is in its stale window or already expired."""
        return self.effective_grade(narrator_id, domain_tag, role=role, now=now).needs_recheck

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
        role: Role | None = None,
    ) -> NarratorGrade:
        """Return grade for a chain link, resolving alias@version when version is known."""
        resolved = resolve_narrator_id(narrator_id, version)
        return self.get_grade(resolved, domain_tag, role=role)

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
        role: Role | None = None,
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
            role=role,
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

    def evidence_provenance(
        self,
        narrator_id: str,
        domain_tag: str,
        role: Role | None = None,
    ) -> EvidenceProvenanceSummary:
        """Summarize where a narrator's grade came from (issue #6).

        Classifies each evidence entry as PRIOR (benchmark seed/eval harness),
        OBSERVED (post-hoc audit / corroboration), HUMAN (reviewer verdict),
        or META (version bump).  Returns counts plus two derived flags:

        - `prior_only`: the grade rests on population priors with no observed
          instance — an unvalidated assumption, however confident the prior.
        - `observation_backed`: at least one observed in-pipeline instance
          exists — a record about THIS transmitter, not its population.

        This is a *signal about the grade*, not a new grading axis.  It does
        not change how grades are computed; it makes visible whether a grade
        is an assumption or an observation.

        ``role`` scopes the summary to a role's precision evidence (issue #3).

        Returns an all-zero summary for an unknown narrator (no evidence).
        """
        narrator = self.get(narrator_id, domain_tag, role=role)
        if narrator is None:
            return EvidenceProvenanceSummary()

        summary = EvidenceProvenanceSummary()
        for entry in narrator.evidence_log:
            etype_raw = entry.get("evidence_type", "")
            try:
                etype = EvidenceType(str(etype_raw))
            except ValueError:
                continue
            provenance = provenance_of(etype)
            if provenance == EvidenceProvenance.PRIOR:
                summary.prior_count += 1
            elif provenance == EvidenceProvenance.OBSERVED:
                summary.observed_count += 1
            elif provenance == EvidenceProvenance.HUMAN:
                summary.human_count += 1
            else:
                summary.meta_count += 1
        return summary

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
        role: Role | None = None,
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

        ``role`` scopes the evidence to a role's precision record (issue #3).
        With a role, only the role's grade is recomputed; integrity is read
        from the shared default record and never written here.

        Returns the new narrator grade.
        """
        resolved_axis = default_axis_for(evidence_type) if axis is None else axis
        narrator = self.register(narrator_id, domain_tag, role=role)
        narrator.add_evidence(evidence_type, action, description, metadata, resolved_axis)

        # Integrity (ʿadālah) lives on the default record, shared across roles.
        # is_compromised drives the REJECTED-stickiness decision (issue #40):
        # only a quarantined (COMPROMISED) narrator's REJECTED is permanent.
        default = self.get(narrator_id, domain_tag)
        is_compromised = default is not None and default.adalah_grade == AdalahGrade.COMPROMISED

        new_grade = self.transition_policy.evaluate_transition(
            current_grade=narrator.grade,
            evidence_history=narrator.evidence_log[:-1],  # all prior
            new_evidence=narrator.evidence_log[-1],
            is_compromised=is_compromised,
        )
        narrator.grade = new_grade
        self._index_set_grade(narrator_id, domain_tag)

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
        self._index_set_grade(narrator_id, domain_tag)

        # Role-scoped precision is void too: a new version is a new narrator.
        # Mirror the default record: reset the grade and clocks, log a
        # VERSION_BUMP, and keep the evidence log intact as an append-only
        # audit trail (the same rule as the default record).
        for key in list(self._role_records):
            if key[0] == narrator_id and key[2] == domain_tag:
                rec = self._role_records[key]
                rec.grade = NarratorGrade.UNGRADED
                rec.dabt_grade = DabtGrade.UNASSESSED
                rec.known_error_rate = None
                rec.graded_at = None
                rec.valid_until = None
                rec.add_evidence(
                    EvidenceType.VERSION_BUMP,
                    EvidenceAction.NEUTRAL,
                    f"Version bumped to {new_version}; role precision reset",
                )

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
            metadata={"__quarantine__": True},  # marks this as active containment, not a
            # mere integrity jarḥ — lets period-sliced re-derivation (issue #43)
            # reconstruct the direct REJECTED + COMPROMISED action.
        )
        self._index_set_grade(narrator_id, domain_tag)
        # Integrity spans roles: quarantine lives on the default record only;

    # ------------------------------------------------------------------
    # Event-driven invalidation + freshness renewal (the expiry fix)
    # ------------------------------------------------------------------

    def flag_contradiction(
        self,
        narrator_id: str,
        domain_tag: str,
        description: str = "",
        role: Role | None = None,
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
            role=role,
        )

    def record_survival(
        self,
        narrator_id: str,
        domain_tag: str,
        claim_id: str,
        source: str,
        *,
        self_verified: bool = False,
        description: str = "",
        role: Role | None = None,
    ) -> NarratorGrade:
        """Record that a claim survived independent verification (issue #25).

        The positive observed-instance signal that #6 wanted: a claim produced
        by this narrator was independently verified against an external
        authority and held up.

        **Tazkiyah guard.**  Survival must come from an *independent* verifier.
        A self-verified seal (amber — the domain vouching for itself) proves
        tamper-evidence and origin, NOT accuracy.  So a self-verified
        "survival" is refused: we return the current grade unchanged and log
        nothing.  Only an *endorsed* verification (green) is genuine survival.

        **Claim-scoped dedup.**  The event binds to (claim_id, source), stored
        in the evidence entry's metadata.  Re-verifying the same claim does
        not double-count: if a SURVIVAL entry with this claim_id+source
        already exists for this narrator, this call is a no-op.  This resists
        farming — survival accumulates per *new* claim, not per re-check.

        Dedup is derived from the evidence log (the source of truth), not a
        parallel set — so it survives a RegistryDB round-trip like any other
        evidence.

        This is a *precision* (ḍabṭ) signal: it is windowed and recoverable,
        exactly like corroboration.  It feeds the existing jarḥ–taʿdīl loop;
        it does not seed ʿadālah (integrity).

        Returns the narrator's grade (unchanged if refused or duplicate).
        """
        narrator = self.register(narrator_id, domain_tag, role=role)
        current_grade = narrator.grade

        # Tazkiyah guard: self-verified survival is not survival.
        if self_verified:
            return current_grade

        # Claim-scoped dedup: has this claim already survived for this narrator?
        for entry in narrator.evidence_log:
            if EvidenceType(str(entry.get("evidence_type", ""))) != EvidenceType.SURVIVAL:
                continue
            meta = entry.get("metadata", {}) or {}
            if meta.get("claim_id") == claim_id and meta.get("source") == source:
                return current_grade

        return self.record_evidence(
            narrator_id,
            domain_tag,
            EvidenceType.SURVIVAL,
            EvidenceAction.TADIL,
            description or f"Claim {claim_id} survived independent verification via {source}",
            metadata={"claim_id": claim_id, "source": source},
            axis=EvidenceAxis.PRECISION,
            role=role,
        )

    def renew_grade(
        self,
        narrator_id: str,
        domain_tag: str,
        reason: str = "corroboration",
        role: Role | None = None,
    ) -> bool:
        """Renew a grade's freshness window without changing the grade.

        Part 3 of the fix: corroboration is a proxy freshness signal.  When
        independent chains keep agreeing with a narrator, the world has not
        changed on them — so we extend the window instead of letting the
        clock expire.  Does nothing for UNGRADED or REJECTED narrators.

        Returns True if the window was renewed.
        """
        narrator = self.get(narrator_id, domain_tag, role=role)
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
        return [*self._narrators.values(), *self._role_records.values()]

    def __len__(self) -> int:
        return len(self._narrators) + len(self._role_records)

    def __contains__(self, key: tuple[str, ...]) -> bool:
        return key in self._narrators or key in self._role_records


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
            role = Role(row.role) if row.role else None
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
                role=role,
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
                # Preserve the original created_at so period-sliced re-derivation
                # (issue #43) works after a reload — otherwise every entry would
                # be stamped with the *load* time, erasing the timeline.
                if ev.created_at is not None:
                    narrator.evidence_log[-1]["created_at"] = ev.created_at.isoformat()
        self.registry._rebuild_alias_index()

    def flush(self) -> None:
        """Persist all narrators and their evidence to the database."""
        for narrator in self.registry.all_narrators():
            role_val = narrator.role.value if narrator.role else ""
            row = (
                self.session
                .query(NarratorRegistry)
                .filter_by(
                    narrator_id=narrator.narrator_id,
                    domain_tag=narrator.domain_tag,
                    role=role_val,
                )
                .first()
            )
            if row is None:
                row = NarratorRegistry(
                    narrator_id=narrator.narrator_id,
                    domain_tag=narrator.domain_tag,
                    role=role_val,
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
                    role=role_val,
                    evidence_type=entry.get("evidence_type", ""),
                    action=entry.get("action", ""),
                    description=str(entry.get("description", "")),
                    metadata_json=meta,
                    created_at=_evidence_time(entry) or datetime.now(UTC),
                )
                self.session.add(ev)
                existing_ids.add(uid)

        self.session.flush()
