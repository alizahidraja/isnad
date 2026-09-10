"""Deterministic, non-circular ground-truth oracle for the model-drift leaderboard (#71).

Labels each generated claim as `faithful` / `hallucinated` / `unverifiable` using ONLY
the fact corpus's (correct_value, wrong_values) — never the critic under test. This is
the independence guarantee that makes the measured hallucination rate trustworthy.
"""

from __future__ import annotations

from enum import Enum

from isnad.types import ContentVerdict

from experiments.model_drift.dataset import FACT_CORPUS, Fact


class GroundTruth(Enum):
    FAITHFUL = "faithful"
    HALLUCINATED = "hallucinated"
    UNVERIFIABLE = "unverifiable"


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def label_claim(claim: str, fact: Fact) -> GroundTruth:
    """Label a claim against its source fact (deterministic)."""
    c = _norm(claim)
    correct = _norm(fact.correct_value)
    if correct in c:
        return GroundTruth.FAITHFUL
    for wrong in fact.wrong_values:
        if _norm(wrong) in c:
            return GroundTruth.HALLUCINATED
    return GroundTruth.UNVERIFIABLE


def label_claim_many(claim: str, fact: Fact) -> tuple[GroundTruth, ContentVerdict]:
    """Label + map to the ISNAD content verdict for the decision matrix.

    A HALLUCINATED claim is a CONTRADICTION of the ground truth; a FAITHFUL claim is
    CONSISTENT; UNVERIFIABLE stays UNVERIFIABLE. This is what the pipeline's `decide`
    should agree with if the critic is honest.
    """
    gt = label_claim(claim, fact)
    verdict = {
        GroundTruth.FAITHFUL: ContentVerdict.CONSISTENT,
        GroundTruth.HALLUCINATED: ContentVerdict.CONTRADICTION,
        GroundTruth.UNVERIFIABLE: ContentVerdict.UNVERIFIABLE,
    }[gt]
    return gt, verdict


def find_fact(fact_id: str) -> Fact:
    for f in FACT_CORPUS:
        if f.fact_id == fact_id:
            return f
    raise KeyError(f"unknown fact_id {fact_id}")
