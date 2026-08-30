"""Co-failure calibration — measure correlated failure between two narrators.

This is the measurement half of issue #54. The corroboration engine prices the
*unobservable* shared-blind-spot risk with a flat prior (``shared_blind_spot_prior``).
The only *observable* signature of that risk is **co-failure**: how often two
nominally-independent narrators are *both wrong together* on claims whose truth is
corpus-verifiable.

Given a labeled eval set (each claim marked CONTRADICTION or CONSISTENT against a
corpus) and the wrong/right verdicts of two narrators, this module computes the
double-fault rate (P both wrong together) and Yule's Q (error association). The
double-fault rate is the grounded per-pair prior that should replace the flat guess;
Q tells you whether the errors are *correlated* (a shared blind spot) or merely
co-incident with each narrator's individual error rate.

Honesty invariants:
- This is a *re-runnable measurement* (evidence, not assumption) — store it like the
  affirmation-gate eval records, pinned to an eval-set hash.
- Absence of observed co-failure is NOT proof of independence: the floor is the
  chance product ``err_a * err_b``, never zero. The prior only lowers, never zeroes.
- The output is a structural statistic (a rate over a labeled set), never a
  claim-level confidence.

Pure and side-effect-free; no optional dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoFailureStats:
    """Per-pair co-failure statistics over a labeled eval set.

    ``double_fault_rate`` is P(both narrators wrong together) over the whole set —
    the grounded shared-blind-spot prior. ``q_statistic`` is Yule's Q (+1 = perfectly
    positively associated errors, 0 = independent, -1 = negatively associated).
    """

    n_cases: int
    both_wrong: int
    a_wrong_only: int
    b_wrong_only: int
    both_right: int
    double_fault_rate: float
    q_statistic: float
    err_a: float
    err_b: float

    def prior(self, *, floor: float | None = None) -> float:
        """The shared-blind-spot prior for this pair.

        The double-fault rate, floored at the chance product ``err_a * err_b`` so a
        small sample with zero observed co-failure is not mistaken for independence.
        """
        chance = self.err_a * self.err_b
        floor = chance if floor is None else max(chance, floor)
        return max(self.double_fault_rate, floor)


def compute_co_failure(
    verdicts: list[tuple[bool, bool]],
) -> CoFailureStats:
    """Compute co-failure stats from (narrator_a_wrong, narrator_b_wrong) pairs.

    ``verdicts`` is a list of (a_wrong, b_wrong) booleans, one per labeled claim.
    The claims must already be corpus-verifiable (the caller holds the ground truth).
    """
    n = len(verdicts)
    if n == 0:
        return CoFailureStats(
            n_cases=0,
            both_wrong=0,
            a_wrong_only=0,
            b_wrong_only=0,
            both_right=0,
            double_fault_rate=0.0,
            q_statistic=0.0,
            err_a=0.0,
            err_b=0.0,
        )

    both_wrong = sum(1 for aw, bw in verdicts if aw and bw)
    a_wrong_only = sum(1 for aw, bw in verdicts if aw and not bw)
    b_wrong_only = sum(1 for aw, bw in verdicts if not aw and bw)
    both_right = n - both_wrong - a_wrong_only - b_wrong_only

    double_fault_rate = both_wrong / n
    err_a = (both_wrong + a_wrong_only) / n
    err_b = (both_wrong + b_wrong_only) / n

    # Yule's Q: (ad - bc) / (ad + bc), where a=both_wrong, d=both_right,
    # b=a_wrong_only, c=b_wrong_only. Q is undefined (0) when ad + bc == 0.
    ad = both_wrong * both_right
    bc = a_wrong_only * b_wrong_only
    q_statistic = (ad - bc) / (ad + bc) if (ad + bc) else 0.0

    return CoFailureStats(
        n_cases=n,
        both_wrong=both_wrong,
        a_wrong_only=a_wrong_only,
        b_wrong_only=b_wrong_only,
        both_right=both_right,
        double_fault_rate=double_fault_rate,
        q_statistic=q_statistic,
        err_a=err_a,
        err_b=err_b,
    )
