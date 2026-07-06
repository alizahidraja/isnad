"""Isnād–Rijāl Framework.

Claim-level provenance for multi-agent knowledge systems, adapting classical
hadith-science methodology to grade transmitters (agents, models, scrapers)
rather than merely logging execution traces.

Quickstart (15 lines)::

    from isnad import Registry, Chain, ChainLinkSpec, grade_chain, decide
    from isnad.types import NarratorGrade, TransformType, ContentVerdict
    from isnad.matn import DeterministicRuleCritic

    chain = Chain([ChainLinkSpec("src", 0), ChainLinkSpec("model-v1", 1)])
    reg = Registry()
    reg.register("src", "physics", grade=NarratorGrade.RELIABLE)
    reg.register("model-v1", "physics", grade=NarratorGrade.UNGRADED)
    grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
    transforms = [l.transform_type for l in chain.links]
    cg = grade_chain(grades, transforms, is_complete=chain.is_complete)
    cv = DeterministicRuleCritic().evaluate("p=mv", "p=mv", ["p=h/lambda"])
    action = decide(cg, cv)
    print(f"Grade: {cg.value}, Verdict: {cv.value}, Action: {action.value}")
"""

__version__ = "1.0.0"
__author__ = "Ali Zahid Raja"

# Public API — re-exports for user convenience
# ruff: noqa: F401 (these are intentional re-exports)

from isnad.chain import Chain, ChainLinkSpec, make_claim_id, normalize_claim_text
from isnad.corroboration import (
    CappedCorroborationPolicy,
    SharedLineageDetector,
    evaluate_corroboration,
)
from isnad.grading import RefinedWeakestLink, grade_chain
from isnad.matn import DeterministicRuleCritic, LLMCritic
from isnad.matrix import decide, describe_action
from isnad.registry import Registry, ThresholdTransitionPolicy
from isnad.types import (
    Action,
    AdalahGrade,
    ChainGrade,
    ChainStatus,
    ContentVerdict,
    CorrelationDetector,
    CorroborationPolicy,
    DabtGrade,
    EvidenceAction,
    EvidenceType,
    GradingStrategy,
    NarratorGrade,
    NarratorType,
    TransformType,
    TransitionPolicy,
)

__all__ = [
    # chain
    "Chain",
    "ChainLinkSpec",
    "make_claim_id",
    "normalize_claim_text",
    # corroboration
    "CappedCorroborationPolicy",
    "SharedLineageDetector",
    "evaluate_corroboration",
    # grading
    "RefinedWeakestLink",
    "grade_chain",
    # matn
    "DeterministicRuleCritic",
    "LLMCritic",
    # matrix
    "decide",
    "describe_action",
    # registry
    "Registry",
    "ThresholdTransitionPolicy",
    # types
    "Action",
    "AdalahGrade",
    "ChainGrade",
    "ChainStatus",
    "ContentVerdict",
    "CorroborationPolicy",
    "CorrelationDetector",
    "DabtGrade",
    "EvidenceAction",
    "EvidenceType",
    "GradingStrategy",
    "NarratorGrade",
    "NarratorType",
    "TransformType",
    "TransitionPolicy",
]
