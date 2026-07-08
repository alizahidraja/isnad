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

from isnad.types import (
    EvidenceAction,
    EvidenceType,
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

    All other rules (upgrade requires sustained corroborated accuracy,
    REJECTED is sticky, version bump resets, human review can restore)
    match the framework's default ThresholdTransitionPolicy.
    """

    def __init__(
        self,
        downgrade_threshold: int = 3,
        upgrade_sustained_count: int = 5,
        upgrade_min_corroborated: int = 3,
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
        """Compute new narrator grade given history and new evidence.

        Args:
            current_grade: Current ordinal grade.
            evidence_history: Prior evidence entries.
            new_evidence: New evidence to incorporate.

        Returns:
            New NarratorGrade after transition.
        """
        evidence_type = EvidenceType(str(new_evidence.get("evidence_type", "")))
        action = EvidenceAction(str(new_evidence.get("action", EvidenceAction.NEUTRAL.value)))

        # --- Version bump → reset ---
        if evidence_type == EvidenceType.VERSION_BUMP:
            return NarratorGrade.UNGRADED

        # --- REJECTED is sticky ---
        if current_grade == NarratorGrade.REJECTED:
            if evidence_type == EvidenceType.HUMAN_REVIEW and action == EvidenceAction.TADIL:
                return NarratorGrade.WEAK
            return NarratorGrade.REJECTED

        # --- Count adverse and favorable events ---
        adverse_count = sum(
            1 for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.JARH
        )
        favorable_count = sum(
            1 for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
        )
        corroborated_favorable = sum(
            1 for e in evidence_history
            if EvidenceAction(str(e.get("action", ""))) == EvidenceAction.TADIL
            and EvidenceType(str(e.get("evidence_type", ""))) == EvidenceType.CORROBORATION_OUTCOME
        )

        if action == EvidenceAction.JARH:
            adverse_count += 1
        elif action == EvidenceAction.TADIL:
            favorable_count += 1
            if evidence_type == EvidenceType.CORROBORATION_OUTCOME:
                corroborated_favorable += 1

        # --- Downgrade: adverse evidence crosses CONFIGURABLE threshold ---
        if adverse_count >= self.downgrade_threshold:
            downgrade_map = {
                NarratorGrade.RELIABLE: NarratorGrade.ACCEPTABLE,
                NarratorGrade.ACCEPTABLE: NarratorGrade.WEAK,
                NarratorGrade.WEAK: NarratorGrade.REJECTED,
                NarratorGrade.UNGRADED: NarratorGrade.WEAK,
            }
            return downgrade_map.get(current_grade, NarratorGrade.WEAK)

        # --- Upgrade: sustained corroborated accuracy ---
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
