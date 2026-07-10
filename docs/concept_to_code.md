# Isnād–Rijāl Framework: Concept → Code Mapping

This document maps each concept from the paper "Grading the Narrators" (Raja, 2026)
to its implementation in this repository.

> **Full architecture diagram:** [`ARCHITECTURE.drawio`](ARCHITECTURE.drawio) — 3 tabs:
> 1. System Architecture (all modules, layers, relationships)
> 2. Claim Lifecycle (end-to-end data flow & decision routing)
> 3. Validation Matrix (what's proven, partial, and not yet done)

## Architecture overview

The framework has five core components, plus the decision matrix that combines them:

```
                        ┌──────────────────────────┐
                        │    Decision Matrix        │
                        │  (core/decision.py)       │
                        │  chain_grade × verdict    │
                        │  → Action                 │
                        └──────────┬─────┬──────────┘
                                   │     │
                    ┌──────────────┘     └──────────────┐
                    ▼                                   ▼
        ┌───────────────────┐              ┌───────────────────┐
        │  Chain Grading     │              │  Matn Criticism   │
        │ (core/grading.py)  │              │  (matn.py,        │
        │ RefinedWeakestLink │              │   critics/*.py)   │
        └─────────┬─────────┘              └───────────────────┘
                  │
     ┌────────────┼────────────────┐
     ▼            ▼                ▼
┌─────────┐ ┌──────────┐  ┌─────────────────┐
│ Chain   │ │Registry  │  │ Corroboration   │
│ Engine  │ │ (rijāl)  │  │ (mutābaʿāt)    │
│(core/   │ │(core/    │  │(core/corroborati│
│chain.py)│ │registry. │  │on.py)           │
└─────────┘ │py)       │  └─────────────────┘
            └──────────┘
```

## Paper section → module mapping

### §4.1 Narrators and Chains

| Concept | Module | Key classes/functions |
|---|---|---|
| Narrator types (source, scraper, model, human) | `isnad/types.py` | `NarratorType` enum |
| Transmission chain | `isnad/core/chain.py` | `Chain`, `ChainLinkSpec` |
| Transform type (destructive/generative/pass-through) | `isnad/types.py` | `TransformType` enum |
| Completeness (ittiṣāl) | `isnad/core/chain.py` | `Chain.is_complete`, `Chain.chain_status` |
| Chain storage | `isnad/core/chain.py` | `store_claim()`, `get_chain_from_db()` |
| Claim normalization + hashing | `isnad/core/chain.py` | `normalize_claim_text()`, `make_claim_id()` |

### §4.2 Narrator Registry & jarḥ–taʿdīl

| Concept | Module | Key classes/functions |
|---|---|---|
| Narrator grade (ordinal tiers) | `isnad/types.py` | `NarratorGrade` enum |
| Domain-conditioned key | `isnad/core/registry.py` | `Registry` — key is `(narrator_id, domain)` |
| ʿAdālah (integrity axis) | `isnad/types.py` | `AdalahGrade` enum |
| Ḍabṭ (precision axis) | `isnad/types.py` | `DabtGrade` enum |
| jarḥ–taʿdīl state machine | `isnad/core/registry.py` | `Registry.record_evidence()` |
| Bayesian transition policy (DEFAULT) | `isnad/core/registry.py` | `BayesianTransitionPolicy` (Beta posterior → grade) |
| Threshold transition policy (legacy fallback) | `isnad/core/registry.py` | `ThresholdTransitionPolicy` |
| Calibrated threshold policy | `isnad/core/registry.py` | `CalibratedThresholdPolicy` |
| Pluggable transition protocol | `isnad/types.py` | `TransitionPolicy` protocol |
| Evidence log (immutable) | `isnad/core/registry.py` | `Narrator.evidence_log`, `NarratorEvidence` (ORM) |
| Version bump reset | `isnad/core/registry.py` | `Registry.bump_version()` |
| Quarantine (mawḍūʿ containment) | `isnad/core/registry.py` | `Registry.quarantine()` |

### §4.3 Corroboration (mutābaʿāt)

| Concept | Module | Key classes/functions |
|---|---|---|
| Independent-chain upgrade | `isnad/core/corroboration.py` | `evaluate_corroboration()` |
| CorroborationEngine | `isnad/core/corroboration.py` | `.evaluate()`, `.evaluate_direct()` |
| Capped upgrade policy (info-theoretic) | `isnad/core/corroboration.py` | `CappedCorroborationPolicy` |
| Minimum-grade gate | `isnad/core/corroboration.py` | `CappedCorroborationPolicy.MIN_GATE_GRADE` |
| Correlation detection (madār) | `isnad/core/corroboration.py` | `SharedLineageDetector` |
| Independence score | `isnad/core/corroboration.py` | `SharedLineageDetector.compute_independence_score()` |
| Finding corroborating claims | `isnad/core/corroboration.py` | `find_corroborating_claims()` |

### §4.4 Dual Criticism & Decision Matrix

| Concept | Module | Key classes/functions |
|---|---|---|
| Content criticism protocol | `isnad/critics/base.py` | `ContentCritic` protocol |
| Deterministic critic (reference stub) | `isnad/matn.py` | `DeterministicRuleCritic` |
| EmbeddingCritic (TF-IDF — DEFAULT) | `isnad/critics/embedding.py` | `EmbeddingCritic`, `TFIDFIndex` |
| LocalNLICritic (DeBERTa cross-encoder) | `isnad/critics/nli.py` | `LocalNLICritic` |
| HybridCritic (MiniLM → NLI, 2-stage) | `isnad/critics/nli.py` | `HybridCritic` |
| LLMCritic (Anthropic Claude) | `isnad/critics/llm.py` | `LLMCritic` |
| Decision matrix | `isnad/core/decision.py` | `decide()`, `describe_action()` |
| Action routing | `isnad/types.py` | `Action` enum |
| Review queue | `isnad/models.py` | `ReviewQueue` (ORM) |

### §5 Reference Schema

| Concept | Module | Key classes/functions |
|---|---|---|
| rijal_claims table | `isnad/models.py` | `RijalClaim` (ORM) |
| narrator_registry table | `isnad/models.py` | `NarratorRegistry` (ORM) |
| chain_links (normalized) | `isnad/models.py` | `ChainLink` (ORM) |
| narrator_evidence table | `isnad/models.py` | `NarratorEvidence` (ORM) |
| review_queue table | `isnad/models.py` | `ReviewQueue` (ORM) |
| JSONB narrator_chain | `isnad/models.py` | `RijalClaim.narrator_chain` |
| Lifecycle (supersession) | `isnad/models.py` | `RijalClaim.valid_from/valid_until/superseded_by` |
| Pydantic DTOs | `isnad/models.py` | `ChainLinkDTO`, `NarratorDTO`, `EvidenceDTO`, `ReviewQueueItemDTO` |
| Database session | `isnad/storage/sqlalchemy.py` | `get_session()`, `init_db()`, `get_engine()` |
| Persistence protocol | `isnad/storage/base.py` | `RegistryPersistence` protocol |
| Alembic migrations | `alembic/` | Initial migration: all 5 tables + indexes |

## Pluggable strategy extension points

Each open parameter from the paper (§4.2/§4.3) maps to a Python protocol:

| Paper concept | Protocol | Default implementation |
|---|---|---|
| Chain grading strategy | `GradingStrategy` | `RefinedWeakestLink` |
| Transition policy (jarḥ–taʿdīl) | `TransitionPolicy` | `BayesianTransitionPolicy` |
| Corroboration policy | `CorroborationPolicy` | `CappedCorroborationPolicy` |
| Correlation detection | `CorrelationDetector` | `SharedLineageDetector` |
| Content criticism | `ContentCritic` | `EmbeddingCritic` (TF-IDF) |

To provide a custom implementation, create a class implementing the protocol and pass it:

```python
from isnad.core.grading import grade_chain
from isnad.types import NarratorGrade, TransformType

class MyGradingStrategy:
    def compute_chain_grade(self, link_narrator_grades, link_transform_types,
                            is_complete, *, corroboration_support=False):
        # custom logic here
        ...

result = grade_chain(
    grades, transforms, is_complete=True,
    strategy=MyGradingStrategy(),
)
```

## Data flow

```
1. Claim ingested → Chain built (core/chain.py)
     → normalize_claim_text() + SHA-256 → claim_id
     → ChainLinkSpec per link (narrator_id, step, transform_type, trace_id)
     → store_claim() → DB
2. Chain links looked up in Registry (core/registry.py)
     → Registry.get_grade(narrator_id, domain) per link
     → BayesianTransitionPolicy (Beta posterior → grade)
3. Chain grade computed (core/grading.py) ← Registry grades
     → RefinedWeakestLink walks chain link-by-link
     → DESTRUCTIVE → hard floor | GENERATIVE → can repair | PASS_THROUGH → min
4. Content criticized independently (critics/*.py) ← Corpus
     → EmbeddingCritic (TF-IDF cosine) or HybridCritic (MiniLM → NLI)
     → ContentVerdict: CONSISTENT | CONTRADICTION | UNVERIFIABLE
5. Corroboration evaluated (core/corroboration.py) ← Other claims
     → CorroborationEngine checks independence, min grade gate, effective weight
     → DAIF → HASAN (capped, never reaches SAHIH)
6. Decision matrix routes action (core/decision.py) ← chain_grade + content_verdict
     → 4×2 matrix → Action: SERVE | SERVE_WITH_CAVEAT | REVIEW | QUARANTINE | REJECT
7. Action executed: serve / review / quarantine
8. Evidence logged back to Registry (jarḥ–taʿdīl loop closes)
     → POST /v1/evidence → Registry.record_evidence()
     → Narrator grades evolve with evidence over time
```

## Module structure (src/isnad/)

```
isnad/
├── __init__.py            Public API re-exports
├── types.py               All enums, protocols, ordinal types
├── models.py              Pydantic DTOs + SQLAlchemy ORM (5 tables)
├── matn.py                DeterministicRuleCritic (reference stub)
├── core/                  Core engine
│   ├── chain.py           Chain, ChainLinkSpec, store_claim()
│   ├── registry.py        Registry, RegistryDB, BayesianTransitionPolicy
│   ├── grading.py         RefinedWeakestLink, grade_chain()
│   ├── corroboration.py   CorroborationEngine, SharedLineageDetector
│   └── decision.py        decide(), describe_action() (4×2 matrix)
├── critics/               Content criticism
│   ├── base.py            ContentCritic protocol
│   ├── embedding.py       EmbeddingCritic (TF-IDF — DEFAULT, zero-deps)
│   ├── nli.py             LocalNLICritic, HybridCritic (DeBERTa + MiniLM)
│   ├── llm.py             LLMCritic (Anthropic Claude, retrieval-augmented)
│   └── eval.py            Critic evaluation harness
├── api/                   FastAPI service
│   ├── app.py             create_app() factory
│   ├── auth.py            API key authentication
│   ├── dependencies.py    DI: get_db(), get_registry(), get_critic()
│   └── endpoints/
│       ├── claims.py      POST/GET /v1/claims
│       ├── narrators.py   POST/GET /v1/narrators, POST /v1/evidence
│       └── health.py      /v1/health, /metrics (Prometheus)
├── cli/                   CLI entry point
│   └── main.py            isnad serve | isnad seed
├── storage/               Persistence layer
│   ├── base.py            RegistryPersistence protocol
│   └── sqlalchemy.py      SQLAlchemy engine, session, init_db()
└── integrations/
    └── langchain/         LangChain integration
        ├── tracer.py      IsnadTracer (callback handler)
        ├── decorator.py   @isnad_track decorator
        └── helpers.py     seed_registry(), CriticAdapter
```
