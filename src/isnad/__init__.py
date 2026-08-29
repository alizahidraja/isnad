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
    grades = [reg.get_grade_for_link(l.narrator_id, l.domain, l.version) for l in chain.links]
    cg = grade_chain(grades, [l.transform_type for l in chain.links],
                     is_complete=chain.is_complete)
    cv = DeterministicRuleCritic().evaluate("p=mv", "p=mv", ["p=h/lambda"])
    action = decide(cg, cv)
"""

__version__ = "2.14.0"
__author__ = "Ali Zahid Raja"

# Public API — re-exports
from isnad.core.chain import (
    Chain,
    ChainLinkSpec,
    grades_for_chain,
    make_claim_id,
    normalize_claim_text,
)
from isnad.core.corroboration import (
    CappedCorroborationPolicy,
    CorroborationEngine,
    SharedLineageDetector,
    evaluate_corroboration,
)
from isnad.core.decision import decide, describe_action
from isnad.core.grading import RefinedWeakestLink, grade_chain
from isnad.core.identity import is_unknown_version, parse_narrator_id, resolve_narrator_id
from isnad.core.registry import (
    BayesianTransitionPolicy,
    CalibratedThresholdPolicy,
    Dispute,
    Narrator,
    Registry,
    RegistryDB,
    ThresholdTransitionPolicy,
    accuracy_to_grade,
    seed_from_benchmark,
)
from isnad.critics import (
    ContentCritic,
    EmbeddingCritic,
    HybridCritic,
    LLMCritic,
    LocalNLICritic,
)
from isnad.matn import DeterministicRuleCritic
from isnad.quick import Verdict, grade
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
    EvidenceProvenance,
    EvidenceType,
    GradingStrategy,
    NarratorGrade,
    NarratorType,
    Role,
    TransformType,
    TransitionPolicy,
    provenance_of,
)

__all__ = [
    # chain
    "Chain",
    "ChainLinkSpec",
    "grades_for_chain",
    "make_claim_id",
    "normalize_claim_text",
    # one-call convenience
    "Verdict",
    "grade",
    "is_unknown_version",
    "parse_narrator_id",
    "resolve_narrator_id",
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
    "CalibratedThresholdPolicy",
    "ThresholdTransitionPolicy",
    # core — registry
    "Narrator",
    "Registry",
    "RegistryDB",
    "Dispute",
    "accuracy_to_grade",
    "seed_from_benchmark",
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
    "EvidenceProvenance",
    "EvidenceType",
    "provenance_of",
    "GradingStrategy",
    "NarratorGrade",
    "NarratorType",
    "Role",
    "TransformType",
    "TransitionPolicy",
]
