"""Transition policies — the jarḥ–taʿdīl grading arithmetic.

The pluggable ``TransitionPolicy`` implementations that turn evidence history
into narrator grades.  Extracted from ``registry.py`` so the *store* (Narrator,
Registry, RegistryDB) and the *grading arithmetic* (these policies) live apart.

Three policies ship:

- ``BayesianTransitionPolicy`` — the default.  Beta-distribution posterior per
  narrator×domain; grades derive from the posterior mean.
- ``ThresholdTransitionPolicy`` — a simple, interpretable sliding-window
  threshold policy (reference alternative).
- ``CalibratedThresholdPolicy`` — the same, with thresholds learned from the
  §8 calibration data.

All three threshold-family policies share ``threshold_transition``, which
encodes the issue #9 ratchet fix (sliding window + edge trigger) and the
axis split (issue #9 follow-up): integrity (ʿadālah) jarḥ is permanent and
never ages out, while precision (ḍabṭ) jarḥ is windowed and recoverable.

This module is pure logic — no fastapi, no sentence-transformers, no langchain.
Only stdlib + the ordinal types in ``isnad.types``.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass

from isnad.types import (
    EvidenceAction,
    EvidenceAxis,
    EvidenceType,
    NarratorGrade,
)

# ===========================================================================
# Beta state — the Bayesian policy's per-narrator posterior
# ===========================================================================

# Seed-grade prior mapping (issue #90). When an operator seeds a narrator via
# ``register(grade=...)`` followed by a ``BOOTSTRAP_SEED`` evidence marker, the
# seed is treated as a Beta prior at this mean, with ``_SEED_PRIOR_WEIGHT``
# pseudo-observations of strength. Without this, a single BOOTSTRAP_SEED marker
# recomputed from a Beta(1,1) prior and collapsed a RELIABLE seed to WEAK.
_SEED_PRIOR_MEAN: dict[NarratorGrade, float] = {
    NarratorGrade.RELIABLE: 0.96,
    NarratorGrade.ACCEPTABLE: 0.85,
    NarratorGrade.WEAK: 0.70,
    NarratorGrade.REJECTED: 0.30,
}
_SEED_PRIOR_WEIGHT: float = 10.0


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
        """Approximate confidence interval via the normal approximation.

        ``width`` is the two-tailed confidence mass; common values map to
        z-scores (0.90→1.645, 0.95→1.96, 0.99→2.576), unknown widths fall
        back to the 95% z-score.
        """
        m = self.mean
        s = self.std
        z = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}.get(width, 1.96)
        return (max(0.0, m - z * s), min(1.0, m + z * s))

    def update(self, positive: bool) -> None:
        if positive:
            self.alpha += 1.0
        else:
            self.beta += 1.0
        self.total_evidence += 1

    def to_grade(
        self,
        reliable_threshold: float = 0.90,
        acceptable_threshold: float = 0.75,
        weak_threshold: float = 0.60,
    ) -> NarratorGrade:
        """Map posterior mean to ordinal grade.

        Thresholds are reference defaults (issue #91), mapping the posterior
        mean (≈ 1 − observed error rate for a Beta(1,1) prior) onto the ordinal
        tiers. The weak/rejected boundary was tightened from 0.50 to 0.60 so
        REJECTED is reachable at ≈ >40% error, not the old lenient >50%.
        """
        mu = self.mean
        if mu >= reliable_threshold:
            return NarratorGrade.RELIABLE
        if mu >= acceptable_threshold:
            return NarratorGrade.ACCEPTABLE
        if mu >= weak_threshold:
            return NarratorGrade.WEAK
        return NarratorGrade.REJECTED


# ===========================================================================
# Shared jarḥ–taʿdīl machinery for the threshold policy family
# ===========================================================================

# One-tier ordinal moves, shared by every threshold-family policy.
_DOWNGRADE_MAP: dict[NarratorGrade, NarratorGrade] = {
    NarratorGrade.RELIABLE: NarratorGrade.ACCEPTABLE,
    NarratorGrade.ACCEPTABLE: NarratorGrade.WEAK,
    NarratorGrade.WEAK: NarratorGrade.REJECTED,
    NarratorGrade.UNGRADED: NarratorGrade.WEAK,
    NarratorGrade.REJECTED: NarratorGrade.REJECTED,  # precision jarḥ cannot sink lower
}
_UPGRADE_MAP: dict[NarratorGrade, NarratorGrade] = {
    NarratorGrade.REJECTED: NarratorGrade.WEAK,  # precision-driven REJECTED is recoverable (#40)
    NarratorGrade.UNGRADED: NarratorGrade.WEAK,
    NarratorGrade.WEAK: NarratorGrade.ACCEPTABLE,
    NarratorGrade.ACCEPTABLE: NarratorGrade.RELIABLE,
}


def _is_integrity_jarh(entry: dict[str, object]) -> bool:
    """True if an evidence entry is an integrity (ʿadālah) impugnment.

    A jarḥ is integrity-class when its axis is INTEGRITY *or* UNSPECIFIED —
    absent an explicit precision declaration, impugnment is treated as
    permanent (al-jarḥ muqaddam ʿalā al-taʿdīl). Only an explicit PRECISION
    tag makes a jarḥ forgettable. Non-jarḥ entries are never integrity strikes.
    """
    if EvidenceAction(str(entry.get("action", ""))) != EvidenceAction.JARH:
        return False
    axis = EvidenceAxis(str(entry.get("axis", EvidenceAxis.UNSPECIFIED.value)))
    return axis != EvidenceAxis.PRECISION


_GRADE_RANK: dict[NarratorGrade, int] = {
    NarratorGrade.REJECTED: 0,
    NarratorGrade.WEAK: 1,
    NarratorGrade.ACCEPTABLE: 2,
    NarratorGrade.UNGRADED: 2,  # ḥasan-ceiling — ranks with ACCEPTABLE, not below
    NarratorGrade.RELIABLE: 3,
}


def _clamp_to_cap(grade: NarratorGrade, cap: NarratorGrade) -> NarratorGrade:
    """Return ``grade`` unless it exceeds the integrity ``cap``, then the cap.

    Uses a ceiling-aware rank so UNGRADED (ḥasan-ceiling) is not mistaken for
    the ordinal floor. When a grade sits at or below the cap it is returned
    unchanged; only grades *above* the permanent integrity ceiling are pulled
    down to it.
    """
    return grade if _GRADE_RANK[grade] <= _GRADE_RANK[cap] else cap


def _integrity_cap(integrity_jarh_count: int, integrity_strikes_per_tier: int) -> NarratorGrade:
    """The best grade still reachable given accumulated integrity strikes.

    Integrity strikes are *permanent*: each ``integrity_strikes_per_tier`` of
    them lowers the ceiling one ordinal tier, independent of any windowed
    precision recovery below it. Enough of them force REJECTED. This is the
    axis that does not forget — the classical protection of the corpus against
    a proven liar, restored after issue #9's window made all jarḥ forgettable.

    ``integrity_strikes_per_tier`` is configurable (issue #21): the classical
    *matrūk* standard argues one proven lie should cap immediately (a value of
    1), while the threshold-consistent default keeps integrity and precision
    on the same footing (value = the policy's downgrade threshold). Callers
    may tune it per deployment without touching the precision axis.
    """
    strikes = max(1, integrity_strikes_per_tier)
    tiers_down = integrity_jarh_count // strikes
    ladder = [
        NarratorGrade.RELIABLE,
        NarratorGrade.ACCEPTABLE,
        NarratorGrade.WEAK,
        NarratorGrade.REJECTED,
    ]
    return ladder[min(tiers_down, len(ladder) - 1)]


def _epoch_evidence(evidence_history: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return evidence after the last VERSION_BUMP (an epoch boundary).

    A version bump is a new narrator (paper §4.2): reputation does not carry
    forward.  Evidence logged before the latest VERSION_BUMP belongs to the
    previous version and must not count toward the new grade — otherwise a
    bump merely resets the *displayed* grade while old evidence silently
    re-inflates it on the next event.
    """
    for i in range(len(evidence_history) - 1, -1, -1):
        if str(evidence_history[i].get("evidence_type", "")) == EvidenceType.VERSION_BUMP.value:
            return evidence_history[i + 1 :]
    return evidence_history


def threshold_transition(
    current_grade: NarratorGrade,
    evidence_history: list[dict[str, object]],
    new_evidence: dict[str, object],
    *,
    downgrade_threshold: int,
    upgrade_sustained_count: int,
    upgrade_min_corroborated: int,
    window: int,
    integrity_strikes_per_tier: int | None = None,
    is_compromised: bool = False,
) -> NarratorGrade:
    """Shared jarḥ–taʿdīl transition for the whole threshold policy family.

    Encodes the issue #9 fix and its conceptual follow-up so all three
    threshold policies behave identically:

    - **Version bump** → UNGRADED.
    - **REJECTED is sticky only when integrity-driven** — ``is_compromised``
      (quarantine → ʿadālah COMPROMISED). A precision-driven REJECTED is
      recoverable (issue #40): it fell on the precision axis, not on a
      permanent impugnment. Human review restores an integrity REJECTED to
      WEAK.
    - **Integrity (ʿadālah) jarḥ** — INTEGRITY or UNSPECIFIED — accumulates over
      the *entire* history and never ages out. It imposes a permanent ceiling
      (``_integrity_cap``); an arriving integrity jarḥ ratchets down to it.
    - **Precision (ḍabṭ) jarḥ** — explicitly PRECISION-tagged — is counted over
      the sliding ``window`` and is edge-triggered, so it is recoverable.
    - **Upgrade** fires on an arriving taʿdīl completing a windowed clean streak,
      then is clamped to the permanent integrity cap: precision recovery can
      never lift a grade past what integrity allows. The axes are never averaged.
    """
    evidence_type = EvidenceType(str(new_evidence.get("evidence_type", "")))
    action = EvidenceAction(str(new_evidence.get("action", EvidenceAction.NEUTRAL.value)))
    axis = EvidenceAxis(str(new_evidence.get("axis", EvidenceAxis.UNSPECIFIED.value)))

    if evidence_type == EvidenceType.VERSION_BUMP:
        return NarratorGrade.UNGRADED

    # Sticky only when integrity-driven (quarantine → COMPROMISED). A
    # precision-driven REJECTED falls through and is recomputed below;
    # the integrity cap still holds a REJECTED reached via enough
    # integrity strikes.
    if current_grade == NarratorGrade.REJECTED and is_compromised:
        if evidence_type == EvidenceType.HUMAN_REVIEW and action == EvidenceAction.TADIL:
            return NarratorGrade.WEAK
        return NarratorGrade.REJECTED

    all_evidence = [*_epoch_evidence(evidence_history), new_evidence]

    # Integrity strikes accumulate forever and cap everything below them.
    # `integrity_strikes_per_tier` defaults to the downgrade threshold when
    # unset, keeping integrity and precision on the same footing (issue #21).
    strikes_per_tier = (
        downgrade_threshold if integrity_strikes_per_tier is None else integrity_strikes_per_tier
    )
    integrity_jarh = sum(1 for e in all_evidence if _is_integrity_jarh(e))
    integrity_cap = _integrity_cap(integrity_jarh, strikes_per_tier)

    # An arriving integrity jarḥ ratchets down to the permanent cap.
    if action == EvidenceAction.JARH and axis != EvidenceAxis.PRECISION:
        return _clamp_to_cap(current_grade, integrity_cap)

    # Precision counts over the sliding window only.
    recent = all_evidence[-window:]
    precision_adverse = sum(
        1
        for e in recent
        if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.JARH
        and EvidenceAxis(str(e.get("axis", EvidenceAxis.UNSPECIFIED.value)))
        == EvidenceAxis.PRECISION
    )
    favorable_count = sum(
        1 for e in recent if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
    )
    corroborated_favorable = sum(
        1
        for e in recent
        if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
        and EvidenceType(str(e.get("evidence_type", ""))) == EvidenceType.CORROBORATION_OUTCOME
    )

    if action == EvidenceAction.JARH and precision_adverse >= downgrade_threshold:
        return _DOWNGRADE_MAP.get(current_grade, NarratorGrade.WEAK)

    if (
        action == EvidenceAction.TADIL
        and favorable_count >= upgrade_sustained_count
        and corroborated_favorable >= upgrade_min_corroborated
    ):
        upgraded = _UPGRADE_MAP.get(current_grade, current_grade)
        return _clamp_to_cap(upgraded, integrity_cap)

    return current_grade


# ===========================================================================
# Policy implementations
# ===========================================================================


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

    The axis split (issues #9/#20) applies here too: integrity (ʿadālah) jarḥ
    accumulates permanently and imposes a ceiling (``_integrity_cap``), while
    precision (ḍabṭ) jarḥ feeds the recoverable Beta posterior.  The posterior
    grade is clamped to the integrity ceiling, so a narrator whose integrity
    is impugned can never be lifted back up by precision evidence alone.

    ``integrity_strikes_per_tier`` (issue #21, configurable) sets how many
    permanent integrity strikes lower the ceiling one tier.  Default 1 — the
    classical matrūk bias: one proven integrity impugnment caps immediately.
    """

    def __init__(
        self,
        integrity_strikes_per_tier: int = 1,
        *,
        reliable_threshold: float = 0.90,
        acceptable_threshold: float = 0.75,
        weak_threshold: float = 0.60,
    ):
        self._states: dict[tuple[str, str], BetaState] = {}
        self.integrity_strikes_per_tier = integrity_strikes_per_tier
        self.reliable_threshold = reliable_threshold
        self.acceptable_threshold = acceptable_threshold
        self.weak_threshold = weak_threshold

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

        Note: this stores a Beta prior for ``get_state()`` introspection only.
        The authoritative grading path is ``evaluate_transition``, which
        recomputes the posterior from the evidence log and its own
        ``_SEED_PRIOR_MEAN`` mapping (issue #90); it does not read ``_states``.
        """
        alpha = prior_mean * prior_weight
        beta = (1.0 - prior_mean) * prior_weight
        key = (narrator_id, domain)
        # No +1 Laplace term: the prior mean already encodes the belief, and
        # adding a Beta(1,1) term on top would silently shift a RELIABLE
        # prior (0.96) down toward ACCEPTABLE (issue #90-class double-count).
        self._states[key] = BetaState(alpha=alpha, beta=beta)

    def evaluate_transition(
        self,
        current_grade: NarratorGrade,
        evidence_history: list[dict[str, object]],
        new_evidence: dict[str, object],
        *,
        is_compromised: bool = False,
    ) -> NarratorGrade:
        """Compute new narrator grade from evidence.

        Note: This method signature matches the TransitionPolicy protocol
        but the Bayesian approach uses its own internal state rather than
        counting from the evidence_history list. For the protocol interface,
        we derive the grade from accumulated evidence counts.

        For full Bayesian usage, use get_state().update() and get_state().to_grade()
        directly through the calibration loop.
        """
        evidence_type = EvidenceType(str(new_evidence.get("evidence_type", "")))
        action = EvidenceAction(str(new_evidence.get("action", EvidenceAction.NEUTRAL.value)))

        # Version bump resets
        if evidence_type == EvidenceType.VERSION_BUMP:
            return NarratorGrade.UNGRADED

        # REJECTED is sticky only when integrity-driven (quarantine →
        # COMPROMISED).  Only an explicit human-review taʿdīl restores it to
        # WEAK.  A *precision*-driven REJECTED is recoverable (issue #40): the
        # narrator fell on the Beta posterior, not on a permanent impugnment,
        # so it must be able to climb back on precision evidence.
        if current_grade == NarratorGrade.REJECTED and is_compromised:
            if evidence_type == EvidenceType.HUMAN_REVIEW and action == EvidenceAction.TADIL:
                return NarratorGrade.WEAK
            return NarratorGrade.REJECTED

        # A VERSION_BUMP is an epoch boundary: evidence before the latest bump
        # belongs to the prior version and must not count.
        history = _epoch_evidence(evidence_history)
        all_evidence = [*history, new_evidence]

        # Integrity (ʿadālah) jarḥ — JARH with axis != PRECISION — accumulates
        # permanently and imposes a ceiling.  Precision (ḍabṭ) evidence drives
        # the recoverable Beta posterior, which is then clamped to that ceiling.
        integrity_jarh = sum(1 for e in all_evidence if _is_integrity_jarh(e))
        integrity_cap = _integrity_cap(integrity_jarh, self.integrity_strikes_per_tier)

        # Issue #90: an operator-assigned seed (register(grade=...) followed by a
        # BOOTSTRAP_SEED marker) must survive as a prior, not collapse to WEAK on
        # the first recompute. The seed grade rides in the BOOTSTRAP_SEED evidence
        # metadata; here it seeds the Beta prior with _SEED_PRIOR_WEIGHT
        # pseudo-observations. Real observations then update it (a seeded RELIABLE
        # narrator caught by a JARH still falls).
        seed_grade: NarratorGrade | None = None
        for e in all_evidence:
            if str(e.get("evidence_type", "")) == EvidenceType.BOOTSTRAP_SEED.value:
                meta = e.get("metadata", {}) or {}
                raw = meta.get("__seed_grade__")
                if raw:
                    with contextlib.suppress(ValueError):
                        seed_grade = NarratorGrade(str(raw))

        positive = sum(
            1
            for e in all_evidence
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
            and str(e.get("evidence_type", "")) != EvidenceType.BOOTSTRAP_SEED.value
        )
        precision_adverse = sum(
            1
            for e in all_evidence
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.JARH
            and EvidenceAxis(str(e.get("axis", EvidenceAxis.UNSPECIFIED.value)))
            == EvidenceAxis.PRECISION
            and str(e.get("evidence_type", "")) != EvidenceType.BOOTSTRAP_SEED.value
        )

        prior_alpha = prior_beta = 1.0
        if seed_grade in _SEED_PRIOR_MEAN:
            m = _SEED_PRIOR_MEAN[seed_grade]
            prior_alpha = m * _SEED_PRIOR_WEIGHT
            prior_beta = (1.0 - m) * _SEED_PRIOR_WEIGHT

        state = BetaState(
            alpha=prior_alpha + float(positive),
            beta=prior_beta + float(precision_adverse),
        )
        state.total_evidence = positive + precision_adverse

        return _clamp_to_cap(
            state.to_grade(
                reliable_threshold=self.reliable_threshold,
                acceptable_threshold=self.acceptable_threshold,
                weak_threshold=self.weak_threshold,
            ),
            integrity_cap,
        )


class CalibratedThresholdPolicy:
    """Threshold-based policy with thresholds LEARNED from calibration data.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  Swap freely.

    Rather than hardcoding (3 adverse, 5 positive), these thresholds are
    calibrated from historical performance data via the §8 experiment
    methodology.  The thresholds can be set per-domain and per-narrator-type.

    Shares the sliding-window + edge-trigger ratchet fix of
    ``ThresholdTransitionPolicy`` (issue #9 finding #1): counts are taken over
    the last ``window`` evidence entries, and a transition fires only on the
    kind of evidence that just arrived. The window defaults to
    ``max(downgrade_threshold, upgrade_sustained_count)`` so both branches stay
    reachable whatever the calibrated thresholds are.
    """

    def __init__(
        self,
        downgrade_threshold: int = 5,
        upgrade_sustained_count: int = 10,
        upgrade_min_corroborated: int = 5,
        window: int | None = None,
        integrity_strikes_per_tier: int | None = None,
    ):
        self.downgrade_threshold = downgrade_threshold
        self.upgrade_sustained_count = upgrade_sustained_count
        self.upgrade_min_corroborated = upgrade_min_corroborated
        self.window = (
            max(downgrade_threshold, upgrade_sustained_count) if window is None else window
        )
        self.integrity_strikes_per_tier = integrity_strikes_per_tier

    def evaluate_transition(
        self,
        current_grade: NarratorGrade,
        evidence_history: list[dict[str, object]],
        new_evidence: dict[str, object],
        *,
        is_compromised: bool = False,
    ) -> NarratorGrade:
        """Compute new narrator grade from evidence (see ``threshold_transition``)."""
        return threshold_transition(
            current_grade,
            evidence_history,
            new_evidence,
            downgrade_threshold=self.downgrade_threshold,
            upgrade_sustained_count=self.upgrade_sustained_count,
            upgrade_min_corroborated=self.upgrade_min_corroborated,
            window=self.window,
            integrity_strikes_per_tier=self.integrity_strikes_per_tier,
            is_compromised=is_compromised,
        )


class ThresholdTransitionPolicy:
    """Threshold jarḥ–taʿdīl transition policy over a sliding evidence window.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  Swap freely.  The framework default is
    ``BayesianTransitionPolicy``; this policy is retained as a simple,
    interpretable alternative.

    Rules:
    - Downgrade fires when adverse evidence *within the recent window* crosses
      a threshold.
    - Upgrade requires sustained corroborated accuracy *within the recent
      window* (N positive evals).
    - Version bump resets to UNGRADED.
    - ʿAdālah COMPROMISED → REJECTED (active containment).
    - REJECTED is sticky — requires explicit human review to restore.

    **Ratchet fix (issue #9 finding #1) — sliding window + edge trigger.**
    The original policy counted adverse (jarḥ) evidence over the narrator's
    *entire* history and checked the downgrade branch on every call. Two
    independent defects combined into a ratchet: (a) the adverse count never
    decayed, so it was monotonic; and (b) the downgrade was *level*-triggered,
    firing on every subsequent call — including pure taʿdīl — while the count
    stayed above threshold. Together they marched every narrator
    RELIABLE → ACCEPTABLE → WEAK → REJECTED with no path to recovery, and left
    the upgrade branch unreachable.

    Both defects are fixed here:

    1. **Sliding window.** Adverse and favorable counts are taken over only the
       last ``window`` evidence entries, so stale jarḥ ages out and sustained
       good behaviour can recover a narrator.
    2. **Edge trigger.** A downgrade fires only when the *arriving* evidence is
       a jarḥ, and an upgrade only when the arriving evidence is a taʿdīl. A
       transition is driven by the evidence that just arrived, not by counts
       left standing in the window from earlier calls.

    A narrator that *keeps* producing adverse evidence still reaches REJECTED,
    so active containment is preserved.

    **Axis split (issue #9 conceptual follow-up) — ʿadālah does not forget.**
    A pure sliding window forgets *all* jarḥ, including integrity (ʿadālah)
    strikes — which silently reintroduces the fabricator-rehabilitation path
    the framework exists to prevent. The tradition permits recovery only for
    *precision* (ḍabṭ), never for integrity. So evidence carries an
    ``EvidenceAxis``:

    - **Integrity jarḥ** (INTEGRITY, or UNSPECIFIED by conservative default)
      accumulates over the narrator's *entire* history and never ages out. Each
      threshold's worth lowers a permanent ceiling one tier; enough force
      REJECTED. This axis is intentionally a ratchet.
    - **Precision jarḥ** (explicitly PRECISION-tagged) is windowed and
      recoverable, exactly as the base ratchet fix intends.

    **Integrity dominates:** the permanent integrity ceiling caps the grade, and
    the windowed precision recovery only operates *below* that cap. Precision
    taʿdīl can never lift a grade held down by an integrity strike. The two axes
    are never averaged.

    A production deployment would calibrate these thresholds and the window via
    the §8 gated-vs-ungated served-error experiment.  The constants here are
    reference defaults, not validated values.
    """

    # Reference thresholds (not empirically calibrated — see paper §8)
    DOWNGRADE_THRESHOLD: int = 3  # adverse events to trigger downgrade
    UPGRADE_SUSTAINED_COUNT: int = 5  # positive events for upgrade eligibility
    UPGRADE_MIN_CORROBORATED: int = 3  # of those, must be corroboration outcomes

    # Default window: the smallest that still admits the reference upgrade rule
    # (needs UPGRADE_SUSTAINED_COUNT recent favorable events). Chosen so the
    # policy trades no magic number for another — see class docstring.
    DEFAULT_WINDOW: int = 5

    def __init__(self, window: int | None = None, integrity_strikes_per_tier: int | None = None):
        """Args:
        window: How many of the most recent evidence entries count toward
            the transition. Older evidence ages out. Defaults to
            ``DEFAULT_WINDOW`` (5). Must be >= ``UPGRADE_SUSTAINED_COUNT`` for
            the upgrade branch to remain reachable.
        integrity_strikes_per_tier: How many permanent integrity (ʿadālah)
            strikes lower the ceiling one tier. Defaults to
            ``DOWNGRADE_THRESHOLD`` (issue #21); set to 1 for a strict
            single-proven-lie-caps-immediately standard.
        """
        self.window = self.DEFAULT_WINDOW if window is None else window
        self.integrity_strikes_per_tier = integrity_strikes_per_tier

    def evaluate_transition(
        self,
        current_grade: NarratorGrade,
        evidence_history: list[dict[str, object]],
        new_evidence: dict[str, object],
        *,
        is_compromised: bool = False,
    ) -> NarratorGrade:
        """Compute the new narrator grade (see ``threshold_transition``)."""
        return threshold_transition(
            current_grade,
            evidence_history,
            new_evidence,
            downgrade_threshold=self.DOWNGRADE_THRESHOLD,
            upgrade_sustained_count=self.UPGRADE_SUSTAINED_COUNT,
            upgrade_min_corroborated=self.UPGRADE_MIN_CORROBORATED,
            window=self.window,
            integrity_strikes_per_tier=self.integrity_strikes_per_tier,
            is_compromised=is_compromised,
        )
