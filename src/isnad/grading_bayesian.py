"""Bayesian grading engine — Beta-distribution narrator grades.

Replaces the hardcoded ThresholdTransitionPolicy with a Bayesian update
mechanism.  Each narrator has a Beta(α, β) prior per domain.  Evidence
updates the posterior.  The grade is derived from the posterior mean.

The Bayesian approach is one instantiation of a parameter the framework
leaves open (paper §4.2).  Swap freely via the TransitionPolicy interface.

Mathematical basis:
- Prior: Beta(α=1, β=1)  [uniform, uninformative]
- Positive evidence (taʿdīl): α += 1
- Adverse evidence (jarḥ):    β += 1
- Posterior mean: μ = α / (α + β)
- Grade mapping:
    μ ≥ 0.90  → RELIABLE
    μ ≥ 0.75  → ACCEPTABLE
    μ ≥ 0.50  → WEAK
    μ < 0.50  → REJECTED
- Confidence interval: 95% HDI from Beta distribution
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from isnad.types import (
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    TransitionPolicy,
)


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
