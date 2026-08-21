"""Parameterized TransitionPolicy for the §8 transition-threshold sweep.

Provides a configurable downgrade threshold so the sweep can test how
sensitivity to adverse evidence affects coverage without editing framework code.

USAGE (via the framework's pluggable interface):
    from isnad.core.registry import Registry
    from sweep_policy import ConfigurableTransitionPolicy

    policy = ConfigurableTransitionPolicy(downgrade_threshold=10)
    reg = Registry(transition_policy=policy)
    # Now use reg normally — all evidence flows through this policy

This is one instantiation of a parameter the framework leaves open
(see paper §4.2).  Swap freely.
"""

from __future__ import annotations

import sys
import os

_exp_dir = os.path.dirname(os.path.abspath(__file__))
if _exp_dir not in sys.path:
    sys.path.insert(0, _exp_dir)

from isnad.core.registry import threshold_transition
from isnad.types import (
    NarratorGrade,
    TransitionPolicy,
)


class ConfigurableTransitionPolicy:
    """Transition policy with configurable downgrade sensitivity.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  Swap freely.

    The only change from the default is DOWNGRADE_THRESHOLD — how many
    adverse evidence events are required to trigger a downgrade.  Higher
    values mean more evidence is needed before a narrator is penalized,
    reducing the cold-start over-penalization observed in the §8 experiment.

    All transition rules are shared with the framework's threshold policy family
    via ``threshold_transition`` — including the issue #9 ratchet fix
    (sliding-window + edge-trigger) and its axis-split follow-up (integrity jarḥ
    is permanent, precision jarḥ is windowed and recoverable). So raising
    ``downgrade_threshold`` is no longer the only lever against the §8.6 "more
    evidence reduced coverage" effect — that effect was the ratchet, not
    threshold miscalibration.
    """

    def __init__(
        self,
        downgrade_threshold: int = 3,
        upgrade_sustained_count: int = 5,
        upgrade_min_corroborated: int = 3,
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
    ) -> NarratorGrade:
        """Compute new narrator grade (see ``threshold_transition``)."""
        return threshold_transition(
            current_grade,
            evidence_history,
            new_evidence,
            downgrade_threshold=self.downgrade_threshold,
            upgrade_sustained_count=self.upgrade_sustained_count,
            upgrade_min_corroborated=self.upgrade_min_corroborated,
            window=self.window,
            integrity_strikes_per_tier=self.integrity_strikes_per_tier,
        )
