# Isnād–Rijāl Framework: Concept → Code Mapping

This document maps each concept from the paper "Grading the Narrators" (Raja, 2026) to its implementation in this repository.

## Architecture overview

The framework has five core components, plus the decision matrix that combines them:

```
┌─────────────────────────────────────────────────────────┐
│                    Decision Matrix                       │
│               (isnad/matrix.py)                          │
│   chain_grade × content_verdict → Action                 │
└──────────────────┬──────────────────┬───────────────────┘
                   │                  │
        ┌──────────┴──────┐  ┌───────┴──────────┐
        │  Chain Grading   │  │  Matn Criticism   │
        │ (isnad/grading)  │  │  (isnad/matn)     │
        └────────┬─────────┘  └──────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───┴───┐  ┌────┴────┐  ┌────┴──────────┐
│Chain  │  │Registry │  │Corroboration   │
│Engine │  │(rijāl)  │  │(mutābaʿāt)     │
└───────┘  └─────────┘  └───────────────┘
```

## Paper section → module mapping

### §4.1 Narrators and Chains

| Concept | Module | Key classes/functions |
|---|---|---|
| Narrator types (source, scraper, model, human) | `isnad/types.py` | `NarratorType` enum |
| Transmission chain | `isnad/chain.py` | `Chain`, `ChainLinkSpec` |
| Transform type (destructive/generative) | `isnad/types.py` | `TransformType` enum |
| Completeness (ittiṣāl) | `isnad/chain.py` | `Chain.is_complete`, `Chain.chain_status` |
| Chain storage | `isnad/chain.py` | `store_claim()`, `get_chain_from_db()` |
| Claim normalization + hashing | `isnad/chain.py` | `normalize_claim_text()`, `make_claim_id()` |

### §4.2 Narrator Registry & jarḥ–taʿdīl

| Concept | Module | Key classes/functions |
|---|---|---|
| Narrator grade (ordinal tiers) | `isnad/types.py` | `NarratorGrade` enum |
| Domain-conditioned key | `isnad/registry.py` | `Registry` — key is `(narrator_id, domain)` |
| ʿAdālah (integrity axis) | `isnad/types.py` | `AdalahGrade` enum |
| Ḍabṭ (precision axis) | `isnad/types.py` | `DabtGrade` enum |
| jarḥ–taʿdīl state machine | `isnad/registry.py` | `Registry.record_evidence()` |
| Transition policy (pluggable) | `isnad/types.py`, `isnad/registry.py` | `TransitionPolicy` protocol, `ThresholdTransitionPolicy` |
| Evidence log (immutable) | `isnad/registry.py` | `Narrator.evidence_log`, `NarratorEvidence` (ORM) |
| Version bump reset | `isnad/registry.py` | `Registry.bump_version()` |
| Quarantine (mawḍūʿ containment) | `isnad/registry.py` | `Registry.quarantine()` |

### §4.3 Corroboration (mutābaʿāt)

| Concept | Module | Key classes/functions |
|---|---|---|
| Independent-chain upgrade | `isnad/corroboration.py` | `evaluate_corroboration()` |
| Capped upgrade policy | `isnad/corroboration.py` | `CappedCorroborationPolicy` |
| Minimum-grade gate | `isnad/corroboration.py` | `CappedCorroborationPolicy.MIN_GATE_GRADE` |
| Correlation detection (madār) | `isnad/corroboration.py` | `SharedLineageDetector` |
| Correlation discount | `isnad/corroboration.py` | Independence score → weight |
| Finding corroborating claims | `isnad/corroboration.py` | `find_corroborating_claims()` |

### §4.4 Dual Criticism & Decision Matrix

| Concept | Module | Key classes/functions |
|---|---|---|
| Content criticism protocol | `isnad/types.py`, `isnad/matn.py` | `ContentCritic` protocol |
| Deterministic critic (stub) | `isnad/matn.py` | `DeterministicRuleCritic` |
| LLM-backed critic (reference) | `isnad/matn.py` | `LLMCritic` |
| Decision matrix | `isnad/matrix.py` | `decide()`, `describe_action()` |
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
| Pydantic DTOs | `isnad/models.py` | `ChainLinkDTO`, `NarratorDTO`, `EvidenceDTO` |
| Database session | `isnad/db.py` | `get_session()`, `init_db()` |
| Alembic migrations | `alembic/` | Initial migration: all 5 tables + indexes |

## Pluggable strategy extension points

Each open parameter from the paper (§4.2/§4.3) maps to a Python protocol or ABC:

| Paper concept | Protocol | Default implementation |
|---|---|---|
| Chain grading strategy | `GradingStrategy` | `RefinedWeakestLink` |
| Transition policy (jarḥ–taʿdīl) | `TransitionPolicy` | `ThresholdTransitionPolicy` |
| Corroboration policy | `CorroborationPolicy` | `CappedCorroborationPolicy` |
| Correlation detection | `CorrelationDetector` | `SharedLineageDetector` |
| Content criticism | `ContentCritic` | `DeterministicRuleCritic` |

To provide a custom implementation, create a class implementing the protocol and pass it:

```python
from isnad.grading import grade_chain
from isnad.types import NarratorGrade, TransformType

class MyGradingStrategy:
    def compute_chain_grade(self, link_narrator_grades, link_transform_types, is_complete):
        # custom logic here
        ...

result = grade_chain(
    grades, transforms, is_complete=True,
    strategy=MyGradingStrategy(),
)
```

## Data flow

```
1. Claim ingested → Chain built (chain.py)
2. Chain links looked up in Registry (registry.py)
3. Chain grade computed (grading.py) ← Registry grades
4. Content criticized independently (matn.py) ← Corpus
5. Corroboration evaluated (corroboration.py) ← Other claims
6. Decision matrix routes action (matrix.py) ← chain_grade + content_verdict
7. Action executed: serve / review / quarantine
8. Evidence logged back to Registry (jarḥ–taʿdīl loop closes)
```
