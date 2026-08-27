"""Tests for the two-axis ablation (#124).

Locks the ablation's key claims into CI so the experiment cannot silently drift:
- The two-axis model caps a high-precision narrator on a single integrity strike,
  while the blended single-axis baseline keeps trusting them.
- The two-axis model quarantines a narrator at 3 integrity strikes that the
  blended model still serves.
- The two-axis model RECOVERS a clumsy-but-honest narrator on sustained
  precision (the split is not "stricter everywhere").
"""

from __future__ import annotations

import os
import sys

# Add the experiment dir to sys.path so run.py is importable.
_exp_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments", "two_axis_ablation"
)
if _exp_dir not in sys.path:
    sys.path.insert(0, _exp_dir)

from run import (
    BlendedTransitionPolicy,
    fabricator_scenario,
    clumsy_honest_scenario,
    run_scenario,
)

from isnad.types import Action, NarratorGrade


def test_fabricator_one_strike_diverges() -> None:
    """One integrity strike caps the two-axis narrator, not the blended one."""
    r = run_scenario(fabricator_scenario(1))
    # Two-axis: capped below the blended baseline.
    assert r.two_axis_grade < r.blended_grade
    # The actions diverge: two-axis withholds full serve.
    assert r.two_axis_action != r.blended_action
    assert r.blended_action == Action.SERVE


def test_fabricator_three_strikes_quarantines() -> None:
    """Three integrity strikes → REJECTED → quarantine in two-axis; blended still serves."""
    r = run_scenario(fabricator_scenario(3))
    assert r.two_axis_grade == NarratorGrade.REJECTED
    assert r.two_axis_action == Action.REJECT_AND_QUARANTINE_NARRATOR
    # The blended model still only reaches ACCEPTABLE/HASAN — it never sees the
    # fabricator for what they are.
    assert r.blended_grade in (NarratorGrade.ACCEPTABLE, NarratorGrade.RELIABLE)
    assert r.blended_action not in (
        Action.QUARANTINE,
        Action.REJECT_AND_QUARANTINE_NARRATOR,
    )


def test_clumsy_honest_narrator_recovers() -> None:
    """Precision failure recovers identically in both models (the split is not
    'stricter everywhere' — integrity is permanent, precision is recoverable)."""
    r = run_scenario(clumsy_honest_scenario())
    assert r.two_axis_action == r.blended_action
    # Both recover to ACCEPTABLE/HASAN — not quarantined.
    assert r.two_axis_grade not in (NarratorGrade.REJECTED, NarratorGrade.WEAK)
