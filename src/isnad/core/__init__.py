"""Core module — pure logic with zero heavy dependencies.

What lives here:
- registry.py  — Registry, Narrator, BayesianTransitionPolicy, ThresholdTransitionPolicy
- chain.py     — Chain, ChainLinkSpec, store_claim
- grading.py   — RefinedWeakestLink, grade_chain
- corroboration.py — CorroborationEngine, SharedLineageDetector, CappedCorroborationPolicy
- decision.py  — decide, describe_action (the decision matrix)

No fastapi, no sentence_transformers, no langchain imports allowed here.
Only stdlib + pydantic + sqlalchemy (for DTOs/storage).
"""

from isnad.core.registry import (
    BayesianTransitionPolicy,
    Narrator,
    Registry,
    RegistryDB,
    ThresholdTransitionPolicy,
)
from isnad.core.chain import (
    Chain,
    ChainLinkSpec,
    get_chain_from_db,
    hash_claim_text,
    make_claim_id,
    normalize_claim_text,
    store_claim,
)
from isnad.core.grading import RefinedWeakestLink, grade_chain
from isnad.core.corroboration import (
    CappedCorroborationPolicy,
    CorroborationEngine,
    SharedLineageDetector,
    evaluate_corroboration,
)
from isnad.core.decision import decide, describe_action

__all__ = [
    # registry
    "BayesianTransitionPolicy",
    "Narrator",
    "Registry",
    "RegistryDB",
    "ThresholdTransitionPolicy",
    # chain
    "Chain",
    "ChainLinkSpec",
    "get_chain_from_db",
    "hash_claim_text",
    "make_claim_id",
    "normalize_claim_text",
    "store_claim",
    # grading
    "RefinedWeakestLink",
    "grade_chain",
    # corroboration
    "CappedCorroborationPolicy",
    "CorroborationEngine",
    "SharedLineageDetector",
    "evaluate_corroboration",
    # decision
    "decide",
    "describe_action",
]
