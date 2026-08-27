"""Two-axis ablation — prove ʿadālah/ḍabṭ split catches what a blended score misses (#124).

The framework's core distinct claim over a weighted DAG / subjective-logic /
truth-maintenance reputation system is the **two-axis split**:

- integrity (ʿadālah) jarḥ is *permanent* — it never ages out and imposes a
  ceiling the narrator can never rise above, however precise they are.
- precision (ḍabṭ) jarḥ is *windowed and recoverable* — a narrator who errs
  can climb back on sustained accuracy.

A single blended reputation score collapses these and averages a deliberate lie
into a long record of correct outputs — keeping a proven fabricator trusted.

This experiment demonstrates the difference **operationally**: it runs the
shipped two-axis `BayesianTransitionPolicy` and a `BlendedTransitionPolicy`
(the single-axis baseline: every jarḥ feeds one recoverable posterior, no
permanent ceiling) over *identical* evidence sequences, then routes the
resulting narrator grades through the real decision matrix to show the
serve/review/quarantine divergence.

Deterministic, self-contained: no API keys, no models, no corpus.

Scenario A — "the fabricator who is usually accurate":
    20 precision taʿdīl (correct outputs) → 1..3 integrity strikes (proven lies).
    The blended model averages the lies into 20 corrects and keeps trusting;
    the two-axis model caps the grade regardless of precision.

Scenario B — "the clumsy but honest narrator" (the inverse, for honesty):
    20 clean taʿdīl → 3 precision jarḥ (errors) → 10 more clean taʿdīl.
    The two-axis model *recovers* (precision is windowed); it must NOT be
    read as 'two-axis is just stricter everywhere' — it is stricter only on
    integrity, and equally recoverable on precision.

Usage:
    python experiments/two_axis_ablation/run.py

Honesty note: this demonstrates the SHIPPED DEFAULT — ``BayesianTransitionPolicy``
with ``integrity_strikes_per_tier=1`` (the classical matrūk standard: one proven
lie caps immediately).  The alternative ``=3`` (threshold-consistent) is a weaker
single-strike signal and is not what ships.  The ablation shows the default, not
an idealized configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from isnad.core.decision import decide
from isnad.core.policies import BayesianTransitionPolicy
from isnad.types import (
    Action,
    ChainGrade,
    ContentVerdict,
    EvidenceAction,
    EvidenceAxis,
    EvidenceType,
    NarratorGrade,
)

# ── The single-axis (blended) baseline ────────────────────────────────
#
# This is the ablation baseline: the SAME Bayesian arithmetic as the shipped
# two-axis policy, but with the axis split removed.  Every jarḥ — integrity
# or precision — feeds one recoverable Beta posterior.  There is no permanent
# ceiling, no distinction between a lie and an error.  A narrator's grade is
# the posterior mean over ALL evidence, blended.

# Narrator grade → chain grade mapping (from grading.py's _narrator_to_chain_grade)
_NARRATOR_TO_CHAIN: dict[NarratorGrade, ChainGrade] = {
    NarratorGrade.RELIABLE: ChainGrade.SAHIH,
    NarratorGrade.ACCEPTABLE: ChainGrade.HASAN,
    NarratorGrade.WEAK: ChainGrade.DAIF,
    NarratorGrade.REJECTED: ChainGrade.MAWDU,
    NarratorGrade.UNGRADED: ChainGrade.DAIF,
}


class BlendedTransitionPolicy:
    """Single-axis baseline: a blended Bayesian posterior over ALL evidence.

    This is NOT shipped in the framework — it exists only as the ablation
    comparator.  It is deliberately identical to ``BayesianTransitionPolicy``
    except that it ignores the ʿadālah/ḍabṭ axis: integrity jarḥ and precision
    jarḥ both feed the same recoverable posterior, and no permanent ceiling
    exists.  The independent variable is therefore exactly one thing: the
    axis split.
    """

    RELIABLE = 0.90
    ACCEPTABLE = 0.75
    WEAK = 0.60

    def __init__(self):
        self._positive = 0.0
        self._negative = 0.0

    def evaluate_transition(
        self,
        current_grade: NarratorGrade,
        evidence_history: list[dict[str, object]],
        new_evidence: dict[str, object],
        *,
        is_compromised: bool = False,
    ) -> NarratorGrade:
        action = EvidenceAction(str(new_evidence.get("action", EvidenceAction.NEUTRAL.value)))
        evidence_type = EvidenceType(str(new_evidence.get("evidence_type", "")))

        if evidence_type == EvidenceType.VERSION_BUMP:
            self._positive = self._negative = 0.0
            return NarratorGrade.UNGRADED

        if action == EvidenceAction.TADIL:
            self._positive += 1.0
        elif action == EvidenceAction.JARH:
            self._negative += 1.0

        # Beta(1,1) posterior mean = (positives + 1) / (positives + negatives + 2)
        mean = (self._positive + 1.0) / (self._positive + self._negative + 2.0)
        if mean >= self.RELIABLE:
            return NarratorGrade.RELIABLE
        if mean >= self.ACCEPTABLE:
            return NarratorGrade.ACCEPTABLE
        if mean >= self.WEAK:
            return NarratorGrade.WEAK
        return NarratorGrade.REJECTED


# ── Evidence builders ──────────────────────────────────────────────────


def _tadil_precision() -> dict[str, object]:
    return {
        "evidence_type": EvidenceType.CORROBORATION_OUTCOME.value,
        "action": EvidenceAction.TADIL.value,
        "axis": EvidenceAxis.PRECISION.value,
    }


def _jarh_precision() -> dict[str, object]:
    return {
        "evidence_type": EvidenceType.POST_HOC_AUDIT.value,
        "action": EvidenceAction.JARH.value,
        "axis": EvidenceAxis.PRECISION.value,
    }


def _jarh_integrity() -> dict[str, object]:
    return {
        "evidence_type": EvidenceType.HUMAN_REVIEW.value,
        "action": EvidenceAction.JARH.value,
        "axis": EvidenceAxis.INTEGRITY.value,
    }


def _run_policy(policy, events: list[dict[str, object]]) -> NarratorGrade:
    grade = NarratorGrade.UNGRADED
    for i, e in enumerate(events):
        grade = policy.evaluate_transition(grade, events[:i], e)
    return grade


# ── Scenario runners ───────────────────────────────────────────────────


@dataclass
class Scenario:
    name: str
    events: list[dict[str, object]]
    # the claim these narrators carried (identical for both policies)
    claim_text: str = "The momentum of a photon is p = h/λ."


def fabricator_scenario(n_integrity_strikes: int) -> Scenario:
    """Scenario A: high precision, then proven lies."""
    events = [_tadil_precision() for _ in range(20)]
    events += [_jarh_integrity() for _ in range(n_integrity_strikes)]
    return Scenario(
        name=f"fabricator (20 precision tadil + {n_integrity_strikes} integrity strike(s))",
        events=events,
    )


def clumsy_honest_scenario() -> Scenario:
    """Scenario B: clean record, a few errors, then recovery."""
    events = [_tadil_precision() for _ in range(20)]
    events += [_jarh_precision() for _ in range(3)]  # three honest errors
    events += [_tadil_precision() for _ in range(10)]  # sustained recovery
    return Scenario(
        name="clumsy-but-honest (20 tadil + 3 precision jarh + 10 tadil)", events=events
    )


# ── Result type ────────────────────────────────────────────────────────


@dataclass
class Result:
    scenario: str
    two_axis_grade: NarratorGrade
    two_axis_chain: ChainGrade
    two_axis_action: Action
    blended_grade: NarratorGrade
    blended_chain: ChainGrade
    blended_action: Action


def _chain_grade(grade: NarratorGrade) -> ChainGrade:
    return _NARRATOR_TO_CHAIN[grade]


def run_scenario(scenario: Scenario) -> Result:
    two_axis = BayesianTransitionPolicy(integrity_strikes_per_tier=1)
    blended = BlendedTransitionPolicy()

    ta_grade = _run_policy(two_axis, scenario.events)
    bl_grade = _run_policy(blended, scenario.events)

    # A single-narrator chain: source (reliable) → model (the narrator under test).
    # The chain grade is the weakest link = the model narrator's grade, mapped
    # to the chain tier. Content is CONSISTENT (the claim is not contradicted),
    # so the decision matrix routes on chain grade alone.
    ta_chain = _chain_grade(ta_grade)
    bl_chain = _chain_grade(bl_grade)
    ta_action = decide(ta_chain, ContentVerdict.CONSISTENT)
    bl_action = decide(bl_chain, ContentVerdict.CONSISTENT)

    return Result(
        scenario=scenario.name,
        two_axis_grade=ta_grade,
        two_axis_chain=ta_chain,
        two_axis_action=ta_action,
        blended_grade=bl_grade,
        blended_chain=bl_chain,
        blended_action=bl_action,
    )


def main() -> None:
    scenarios = [
        fabricator_scenario(1),
        fabricator_scenario(2),
        fabricator_scenario(3),
        clumsy_honest_scenario(),
    ]

    print("=" * 78)
    print("TWO-AXIS ABLATION (#124) — ʿadālah/ḍabṭ split vs blended reputation score")
    print("=" * 78)
    print()

    for s in scenarios:
        r = run_scenario(s)
        print(f"  {r.scenario}")
        print(f"    two-axis (Bayesian, strikes_per_tier=1):")
        print(
            f"        grade={r.two_axis_grade.value:10s}  chain={r.two_axis_chain.value:8s}  action={r.two_axis_action.value}"
        )
        print(f"    blended (single-axis baseline):")
        print(
            f"        grade={r.blended_grade.value:10s}  chain={r.blended_chain.value:8s}  action={r.blended_action.value}"
        )
        diverges = r.two_axis_action != r.blended_action
        print(f"    {'⚠️  DIVERGES' if diverges else '✓  same outcome'}")
        print()

    print("=" * 78)
    print("READING THE RESULT")
    print("=" * 78)
    print("  Scenario A (fabricator): the two-axis model caps the grade on the first")
    print("  integrity strike — one proven lie, however precise the narrator — while the")
    print("  blended model averages the lie into 20 correct outputs and keeps trusting.")
    print("  At 3 strikes the two-axis model reaches REJECTED → quarantine; the blended")
    print("  model still serves.")
    print()
    print("  Scenario B (clumsy-but-honest): the two-axis model RECOVERS the narrator on")
    print("  sustained precision — the split is NOT 'stricter everywhere', it is stricter")
    print("  on integrity and equally recoverable on precision. A pure ratchet that never")
    print("  forgave precision would be a different (worse) design, and this shows we did")
    print("  not build that.")
    print("=" * 78)


if __name__ == "__main__":
    main()
