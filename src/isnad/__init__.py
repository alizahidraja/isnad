"""Isnad-Rijal Framework.

Claim-level provenance for multi-agent knowledge systems, adapting classical
hadith-science methodology to grade transmitters (agents, models, scrapers)
rather than merely logging execution traces.

Quickstart::

    from isnad import Registry, Chain, ChainLinkSpec, grade_chain, decide
    from isnad.types import NarratorGrade, TransformType, ContentVerdict
    from isnad.matn import DeterministicRuleCritic

    chain = Chain([ChainLinkSpec("src", 0), ChainLinkSpec("model-v1", 1)])
    reg = Registry()
    reg.register("src", "physics", grade=NarratorGrade.RELIABLE)
    reg.register("model-v1", "physics", grade=NarratorGrade.UNGRADED)
    grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
    cg = grade_chain(grades, [l.transform_type for l in chain.links],
                     is_complete=chain.is_complete)
    cv = DeterministicRuleCritic().evaluate("p=mv", "p=mv", ["p=h/lambda"])
    action = decide(cg, cv)
"""

__version__ = "1.0.3"
__author__ = "Ali Zahid Raja"

# Public API — re-exports
from isnad.core.chain import Chain, ChainLinkSpec, make_claim_id, normalize_claim_text
from isnad.core.corroboration import (
    CappedCorroborationPolicy,
    CorroborationEngine,
    SharedLineageDetector,
    evaluate_corroboration,
)
from isnad.core.decision import decide, describe_action
from isnad.core.grading import RefinedWeakestLink, grade_chain
from isnad.core.registry import (
    BayesianTransitionPolicy,
    Narrator,
    Registry,
    RegistryDB,
    ThresholdTransitionPolicy,
)
from isnad.critics import (
    ContentCritic,
    EmbeddingCritic,
    HybridCritic,
    LLMCritic,
    LocalNLICritic,
)
from isnad.matn import DeterministicRuleCritic
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
    # core — corroboration
    "CappedCorroborationPolicy",
    "CorroborationEngine",
    "SharedLineageDetector",
    "evaluate_corroboration",
    # core — decision
    "decide",
    "describe_action",
    # core — grading
    "RefinedWeakestLink",
    "grade_chain",
    "BayesianTransitionPolicy",
    "ThresholdTransitionPolicy",
    # core — registry
    "Narrator",
    "Registry",
    "RegistryDB",
    # critics
    "ContentCritic",
    "EmbeddingCritic",
    "HybridCritic",
    "LLMCritic",
    "LocalNLICritic",
    # matn
    "DeterministicRuleCritic",
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
