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

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from isnad.models import (
    NarratorEvidence,
    NarratorRegistry,
)
from isnad.types import (
    AdalahGrade,
    DabtGrade,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    NarratorType,
    TransitionPolicy,
)

# ===========================================================================
# Default TransitionPolicy implementation
# ===========================================================================


@dataclass
class BetaState:
    """Beta distribution state for one narrator in one domain."""

    alpha: float = 1.0  # successes + 1 (prior)
    beta: float = 1.0  # failures + 1 (prior)
    total_evidence: int = 0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        ab = self.alpha + self.beta
        return (self.alpha * self.beta) / (ab * ab * (ab + 1))

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    def confidence_interval(self, width: float = 0.95) -> tuple[float, float]:
        """Approximate 95% confidence interval using normal approximation."""
        m = self.mean
        s = self.std
        z = 1.96  # 95%
        return (max(0.0, m - z * s), min(1.0, m + z * s))

    def update(self, positive: bool) -> None:
        if positive:
            self.alpha += 1.0
        else:
            self.beta += 1.0
        self.total_evidence += 1

    def to_grade(self) -> NarratorGrade:
        """Map posterior mean to ordinal grade."""
        mu = self.mean
        if mu >= 0.90:
            return NarratorGrade.RELIABLE
        elif mu >= 0.75:
            return NarratorGrade.ACCEPTABLE
        elif mu >= 0.50:
            return NarratorGrade.WEAK
        else:
            return NarratorGrade.REJECTED


class BayesianTransitionPolicy:
    """Bayesian transition policy using Beta distribution updates.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  Swap freely.

    Each narrator×domain maintains a Beta(α, β) state.  Evidence updates
    the posterior.  Grades are derived from the posterior mean with
    calibrated thresholds.

    Key advantages over threshold counting:
    - Continuous confidence (posterior mean + credible interval)
    - Graceful with small samples (prior provides regularization)
    - Natural uncertainty quantification
    - No arbitrary "3 adverse events" cutoff
    """

    def __init__(self):
        self._states: dict[tuple[str, str], BetaState] = {}

    def get_state(self, narrator_id: str, domain: str) -> BetaState:
        key = (narrator_id, domain)
        if key not in self._states:
            self._states[key] = BetaState()
        return self._states[key]

    def seed_grade(
        self,
        narrator_id: str,
        domain: str,
        prior_mean: float,
        prior_weight: float = 10.0,
    ) -> None:
        """Seed a narrator with a prior belief.

        Args:
            narrator_id: The narrator identifier.
            domain: Domain tag.
            prior_mean: Expected reliability (0.0–1.0).
            prior_weight: Strength of prior (pseudo-observations).
        """
        alpha = prior_mean * prior_weight
        beta = (1.0 - prior_mean) * prior_weight
        key = (narrator_id, domain)
        self._states[key] = BetaState(alpha=alpha + 1, beta=beta + 1)

    def evaluate_transition(
        self,
        current_grade: NarratorGrade,
        evidence_history: list[dict[str, object]],
        new_evidence: dict[str, object],
    ) -> NarratorGrade:
        """Compute new narrator grade from evidence.

        Note: This method signature matches the TransitionPolicy protocol
        but the Bayesian approach uses its own internal state rather than
        counting from the evidence_history list. For the protocol interface,
        we derive the grade from accumulated evidence counts.

        For full Bayesian usage, use get_state().update() and get_state().to_grade()
        directly through the calibration loop.
        """
        # Count evidence from history + new evidence
        positive = sum(
            1
            for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
        )
        adverse = sum(
            1
            for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.JARH
        )

        action = EvidenceAction(str(new_evidence.get("action", EvidenceAction.NEUTRAL.value)))
        if action == EvidenceAction.TADIL:
            positive += 1
        elif action == EvidenceAction.JARH:
            adverse += 1

        # Build Beta state from counts
        state = BetaState(alpha=float(positive + 1), beta=float(adverse + 1))
        state.total_evidence = positive + adverse

        # Version bump resets
        evidence_type = EvidenceType(str(new_evidence.get("evidence_type", "")))
        if evidence_type == EvidenceType.VERSION_BUMP:
            return NarratorGrade.UNGRADED

        return state.to_grade()


# ── Calibrated Threshold Policy (data-driven) ────────────────────


class CalibratedThresholdPolicy:
    """Threshold-based policy with thresholds LEARNED from calibration data.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  Swap freely.

    Rather than hardcoding (3 adverse, 5 positive), these thresholds are
    calibrated from historical performance data via the §8 experiment
    methodology.  The thresholds can be set per-domain and per-narrator-type.
    """

    def __init__(
        self,
        downgrade_threshold: int = 5,
        upgrade_sustained_count: int = 10,
        upgrade_min_corroborated: int = 5,
    ):
        self.downgrade_threshold = downgrade_threshold
        self.upgrade_sustained_count = upgrade_sustained_count
        self.upgrade_min_corroborated = upgrade_min_corroborated

    def evaluate_transition(
        self,
        current_grade: NarratorGrade,
        evidence_history: list[dict[str, object]],
        new_evidence: dict[str, object],
    ) -> NarratorGrade:
        """Compute new narrator grade from evidence."""
        evidence_type = EvidenceType(str(new_evidence.get("evidence_type", "")))
        action = EvidenceAction(str(new_evidence.get("action", EvidenceAction.NEUTRAL.value)))

        if evidence_type == EvidenceType.VERSION_BUMP:
            return NarratorGrade.UNGRADED

        if current_grade == NarratorGrade.REJECTED:
            if evidence_type == EvidenceType.HUMAN_REVIEW and action == EvidenceAction.TADIL:
                return NarratorGrade.WEAK
            return NarratorGrade.REJECTED

        adverse_count = sum(
            1
            for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.JARH
        )
        favorable_count = sum(
            1
            for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
        )
        corroborated_favorable = sum(
            1
            for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
            and EvidenceType(str(e.get("evidence_type", "")))
            == EvidenceType.CORROBORATION_OUTCOME
        )

        if action == EvidenceAction.JARH:
            adverse_count += 1
        elif action == EvidenceAction.TADIL:
            favorable_count += 1
            if evidence_type == EvidenceType.CORROBORATION_OUTCOME:
                corroborated_favorable += 1

        if adverse_count >= self.downgrade_threshold:
            downgrade_map = {
                NarratorGrade.RELIABLE: NarratorGrade.ACCEPTABLE,
                NarratorGrade.ACCEPTABLE: NarratorGrade.WEAK,
                NarratorGrade.WEAK: NarratorGrade.REJECTED,
                NarratorGrade.UNGRADED: NarratorGrade.WEAK,
            }
            return downgrade_map.get(current_grade, NarratorGrade.WEAK)

        if (
            favorable_count >= self.upgrade_sustained_count
            and corroborated_favorable >= self.upgrade_min_corroborated
        ):
            upgrade_map = {
                NarratorGrade.UNGRADED: NarratorGrade.WEAK,
                NarratorGrade.WEAK: NarratorGrade.ACCEPTABLE,
                NarratorGrade.ACCEPTABLE: NarratorGrade.RELIABLE,
            }
            return upgrade_map.get(current_grade, current_grade)

        return current_grade


class ThresholdTransitionPolicy:
    """Default jarḥ–taʿdīl transition policy.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  Swap freely.

    Rules:
    - Downgrade fires when accumulated adverse evidence crosses a threshold.
    - Upgrade requires sustained corroborated accuracy (N positive evals).
    - Version bump resets to UNGRADED.
    - ʿAdālah COMPROMISED → REJECTED (active containment).
    - REJECTED is sticky — requires explicit human review to restore.

    A production deployment would calibrate these thresholds via the
    §8 gated-vs-ungated served-error experiment.  The constants here are
    reference defaults, not validated values.
    """

    # Reference thresholds (not empirically calibrated — see paper §8)
    DOWNGRADE_THRESHOLD: int = 3  # adverse events to trigger downgrade
    UPGRADE_SUSTAINED_COUNT: int = 5  # positive events for upgrade eligibility
    UPGRADE_MIN_CORROBORATED: int = 3  # of those, must be corroboration outcomes

    def evaluate_transition(
        self,
        current_grade: NarratorGrade,
        evidence_history: list[dict[str, object]],
        new_evidence: dict[str, object],
    ) -> NarratorGrade:
        """Compute the new narrator grade given history and new evidence.

        Args:
            current_grade: The narrator's current ordinal grade.
            evidence_history: Prior evidence entries (dicts with 'action', 'evidence_type').
            new_evidence: The new evidence dict (must have 'action', 'evidence_type').

        Returns:
            The new NarratorGrade after applying the transition.
        """
        evidence_type = EvidenceType(str(new_evidence.get("evidence_type", "")))
        action = EvidenceAction(str(new_evidence.get("action", EvidenceAction.NEUTRAL.value)))

        # --- Version bump → reset to UNGRADED ---
        if evidence_type == EvidenceType.VERSION_BUMP:
            return NarratorGrade.UNGRADED

        # --- REJECTED is sticky (containment) ---
        if current_grade == NarratorGrade.REJECTED:
            # Only human review can restore from REJECTED
            if evidence_type == EvidenceType.HUMAN_REVIEW and action == EvidenceAction.TADIL:
                return NarratorGrade.WEAK  # restore to weak, let evidence rebuild
            return NarratorGrade.REJECTED

        # --- Count adverse (jarḥ) and favorable (taʿdīl) events ---
        adverse_count = sum(
            1
            for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.JARH
        )
        favorable_count = sum(
            1
            for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
        )
        corroborated_favorable = sum(
            1
            for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
            and EvidenceType(str(e.get("evidence_type", ""))) == EvidenceType.CORROBORATION_OUTCOME
        )

        if action == EvidenceAction.JARH:
            adverse_count += 1
        elif action == EvidenceAction.TADIL:
            favorable_count += 1
            if evidence_type == EvidenceType.CORROBORATION_OUTCOME:
                corroborated_favorable += 1

        # --- Downgrade: adverse evidence crosses threshold ---
        if adverse_count >= self.DOWNGRADE_THRESHOLD:
            downgrade_map = {
                NarratorGrade.RELIABLE: NarratorGrade.ACCEPTABLE,
                NarratorGrade.ACCEPTABLE: NarratorGrade.WEAK,
                NarratorGrade.WEAK: NarratorGrade.REJECTED,
                NarratorGrade.UNGRADED: NarratorGrade.WEAK,
            }
            return downgrade_map.get(current_grade, NarratorGrade.WEAK)

        # --- Upgrade: sustained corroborated accuracy ---
        if (
            favorable_count >= self.UPGRADE_SUSTAINED_COUNT
            and corroborated_favorable >= self.UPGRADE_MIN_CORROBORATED
        ):
            upgrade_map = {
                NarratorGrade.UNGRADED: NarratorGrade.WEAK,
                NarratorGrade.WEAK: NarratorGrade.ACCEPTABLE,
                NarratorGrade.ACCEPTABLE: NarratorGrade.RELIABLE,
            }
            return upgrade_map.get(current_grade, current_grade)

        return current_grade


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
        self.evidence_log: list[dict[str, object]] = []

    def add_evidence(
        self,
        evidence_type: EvidenceType,
        action: EvidenceAction,
        description: str = "",
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Log an evidence entry."""
        entry: dict[str, object] = {
            "evidence_type": evidence_type.value,
            "action": action.value,
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

    def __init__(self, transition_policy: TransitionPolicy | None = None):
        self._narrators: dict[tuple[str, str], Narrator] = {}
        self.transition_policy: TransitionPolicy = (
            transition_policy or BayesianTransitionPolicy()
        )

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
    ) -> Narrator:
        """Register a new narrator or return existing one."""
        key = (narrator_id, domain_tag)
        if key not in self._narrators:
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
            )
        return self._narrators[key]

    def get(self, narrator_id: str, domain_tag: str) -> Narrator | None:
        """Look up a narrator by (narrator_id, domain_tag)."""
        return self._narrators.get((narrator_id, domain_tag))

    def get_grade(self, narrator_id: str, domain_tag: str) -> NarratorGrade:
        """Return a narrator's grade, defaulting to UNGRADED if unknown."""
        narrator = self.get(narrator_id, domain_tag)
        return narrator.grade if narrator else NarratorGrade.UNGRADED

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
    ) -> NarratorGrade:
        """Log evidence against a narrator and compute the new grade.

        This is the jarḥ–taʿdīl loop: log evidence, re-evaluate grade.
        The actual transition logic is delegated to the pluggable
        TransitionPolicy so implementations can swap the arithmetic
        without touching the registry structure.

        Returns the new narrator grade.
        """
        narrator = self.register(narrator_id, domain_tag)
        narrator.add_evidence(evidence_type, action, description, metadata)

        new_grade = self.transition_policy.evaluate_transition(
            current_grade=narrator.grade,
            evidence_history=narrator.evidence_log[:-1],  # all prior
            new_evidence=narrator.evidence_log[-1],
        )
        narrator.grade = new_grade
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
        narrator.add_evidence(
            EvidenceType.VERSION_BUMP,
            EvidenceAction.NEUTRAL,
            f"Version bumped to {new_version}; grade reset to UNGRADED",
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
        narrator.add_evidence(
            EvidenceType.HUMAN_REVIEW,
            EvidenceAction.JARH,
            f"Quarantined: {reason}" if reason else "Quarantined",
        )

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
        self.registry = Registry(
            transition_policy=transition_policy or BayesianTransitionPolicy()
        )

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
            )
            # Load evidence log
            for ev in row.evidence_log:
                narrator.add_evidence(
                    EvidenceType(ev.evidence_type),
                    EvidenceAction(ev.action),
                    ev.description,
                    ev.metadata_json,
                )

    def flush(self) -> None:
        """Persist all narrators and their evidence to the database."""
        for narrator in self.registry.all_narrators():
            row = (
                self.session.query(NarratorRegistry)
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

            # Append new evidence entries
            existing_ids = {str(e.id) for e in row.evidence_log}
            for entry in narrator.evidence_log:
                # Simple dedup by description+timestamp
                key = f"{entry.get('description', '')}{entry.get('created_at', '')}"
                if key not in existing_ids:
                    ev = NarratorEvidence(
                        narrator_id=narrator.narrator_id,
                        domain_tag=narrator.domain_tag,
                        evidence_type=entry.get("evidence_type", ""),
                        action=entry.get("action", ""),
                        description=str(entry.get("description", "")),
                        metadata_json=entry.get("metadata", {}),
                    )
                    self.session.add(ev)
                    existing_ids.add(key)

        self.session.flush()
