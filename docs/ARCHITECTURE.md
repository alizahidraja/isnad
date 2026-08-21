# ISNAD Architecture — Complete Guide

> For anyone who wants to understand, extend, or contribute to the ISNAD
> framework.  Start here.

---

## Table of Contents

1. [The Big Picture: Four Independent Loops](#the-big-picture-four-independent-loops)
2. [Module Map: What Lives Where](#module-map-what-lives-where)
3. [Loop 1: The Chain (isnād)](#loop-1-the-chain-isnād)
4. [Loop 2: The Registry (rijāl)](#loop-2-the-registry-rijāl)
5. [Loop 3: Chain Grading (weakest-link)](#loop-3-chain-grading-weakest-link)
6. [Corroboration (mutābaʿāt)](#corroboration-mutābaʿāt)
7. [Loop 4: Content Criticism (matn)](#loop-4-content-criticism-matn)
8. [The Decision Matrix](#the-decision-matrix)
9. [Grade Freshness & Time Decay](#grade-freshness--time-decay)
10. [Narrator Identity & Versioning](#narrator-identity--versioning)
11. [Persistence Layer](#persistence-layer)
12. [API Layer](#api-layer)
13. [CLI](#cli)
14. [Trace Capture (LangChain)](#trace-capture-langchain)
15. [Trace Schema v0.1](#trace-schema-v01)
16. [Chain Viewer](#chain-viewer)
17. [LangChain Integration (older tracer + decorator)](#langchain-integration-older-tracer--decorator)
18. [The Full End-to-End Flow](#the-full-end-to-end-flow)
19. [Where to Start Contributing](#where-to-start-contributing)

---

## The Big Picture: Four Independent Loops

ISNAD is not one pipeline.  It is **four independent loops** that intersect
at the decision matrix:

```
┌──────────────────────┐      ┌──────────────────────┐
│   LOOP 1: CHAIN      │      │   LOOP 2: REGISTRY   │
│   (isnād)            │      │   (rijāl)            │
│                      │      │                      │
│  Every claim carries │      │  Every transmitter   │
│  its full path:      │      │  has a graded record │
│  source → scraper    │      │  per (narrator,      │
│  → model → output    │      │  domain)             │
└──────────┬───────────┘      └───────────┬──────────┘
           │                              │
           │      grades_for_chain()      │
           └──────────────┬───────────────┘
                          │
                 ┌────────▼─────────┐
                 │  LOOP 3: GRADE   │
                 │  (weakest-link)  │
                 │                  │
                 │  Walk chain      │
                 │  link-by-link,   │
                 │  floor = min()   │
                 │  refined by      │
                 │  transform type  │
                 └────────┬─────────┘
                          │
            ┌─────────────┼──────────────┐
            │             │              │
     ┌──────▼──────┐ ┌───▼────┐  ┌──────▼──────────┐
     │  CORROB.    │ │ CHAIN  │  │  LOOP 4: MATN   │
     │  (mutābaʿāt)│ │ GRADE  │  │  (content crit) │
     │             │ │        │  │                 │
     │  Independent│ │ ṣaḥīḥ  │  │  consistent /   │
     │  chains     │ │ ḥasan  │  │  contradiction  │
     │  upgrade    │ │ ḍaʿīf  │  │  / unverifiable │
     │  the grade  │ │ mawḍūʿ │  │                 │
     └──────┬──────┘ └───┬────┘  └──────┬──────────┘
            │             │             │
            └─────────────┼─────────────┘
                          │
                 ┌────────▼────────┐
                 │ DECISION MATRIX │
                 │  4×2 router     │
                 │                 │
                 │ chain × content │
                 │ → serve/review  │
                 │ /quarantine     │
                 └─────────────────┘
```

Every loop is pluggable via a Python Protocol.  Swap any strategy without
touching the others.

---

## Module Map: What Lives Where

```
src/isnad/
├── __init__.py                  Public API re-exports
├── types.py                     All enums, Protocols, ordinal types
├── models.py                    Pydantic DTOs + SQLAlchemy ORM models
├── matn.py                      DeterministicRuleCritic (simple stub)
│
├── core/                        ── The engine ──
│   ├── chain.py                 Chain + ChainLinkSpec construction
│   ├── registry.py              Narrator store, jarḥ–taʿdīl, freshness
│   ├── grading.py               Weakest-link chain grade computation
│   ├── corroboration.py         Independent-chain upgrade + madār detection
│   ├── decision.py              4×2 matrix: chain × content → action
│   ├── identity.py              alias@version resolution
│   └── volatility.py            Grade TTL / stale window / expiry
│
├── critics/                     ── Content criticism ──
│   ├── base.py                  ContentCritic Protocol
│   ├── embedding.py             TF-IDF cosine similarity critic
│   ├── nli.py                   HybridCritic (MiniLM + DeBERTa NLI)
│   ├── llm.py                   LLM-backed critic (Anthropic)
│   └── eval.py                  Evaluation harness for critics
│
├── storage/                     ── Persistence ──
│   ├── base.py                  RegistryPersistence Protocol
│   └── sqlalchemy.py            SQLAlchemy session management
│
├── api/                         ── REST API ──
│   ├── app.py                   FastAPI app factory
│   ├── auth.py                  API key auth
│   ├── dependencies.py          DI / state management
│   └── endpoints/
│       ├── claims.py            Claim grading + version drift
│       ├── narrators.py         Registry CRUD
│       └── health.py            Health + Prometheus /metrics
│
├── cli/                         ── CLI ──
│   └── main.py                  isnad serve, isnad seed
│
├── trace/                       ── Trace schema ──
│   ├── __init__.py              Public API
│   └── schema.py                TraceV01, TransmitterNode, Grade, etc.
│
├── integrations/
│   └── langchain/               ── LangChain integration ──
│       ├── callback.py          IsnadCallbackHandler (tree-based, sync+async)
│       ├── tracer.py            IsnadTracer (older, flat-list, report())
│       ├── helpers.py           seed_registry(), CriticAdapter
│       └── decorator.py         @isnad_track decorator

viewer/
└── index.html                   Self-contained chain viewer (3 fixtures)

fixtures/
├── 1-clean-chain.json           Ṣaḥīḥ chain, verified independent
├── 2-weak-extraction.json       Ḍaʿīf chain, verified origin
├── 3-false-corroboration.json   5 transmitters, 1 source (madār)
└── isnad_trace_v0.1.schema.json  Auto-emitted JSON Schema

examples/
├── isnad_langchain_demo.py      Runnable demo (no API keys)
├── langchain_demo.py            Older LangChain demo
└── worked_example.py            Paper's worked example

docs/
├── trace-schema.md              Schema spec with PROV mapping
├── ARCHITECTURE.drawio          Architecture diagram (3 tabs)
└── concept_to_code.md           Concept → module mapping

tests/                           ~200 tests across 22 files
```

---

## Loop 1: The Chain (isnād)

**File:** `core/chain.py`

Every claim carries its full ordered transmission path.

**`ChainLinkSpec`** — one transformation step:
| Field | Type | Meaning |
|-------|------|---------|
| `narrator_id` | `str` | Who transmitted (e.g. `"model:gpt-4o"`) |
| `step` | `int` | Zero-indexed position in chain |
| `version` | `str` | Model version, `"unknown"` if unresolved |
| `transform_type` | `TransformType` | `DESTRUCTIVE` / `GENERATIVE` / `PASS_THROUGH` |
| `trace_id` | `str` | Ops trace identifier |
| `domain` | `str` | Domain tag for per-domain grading |
| `confidence` | `float?` | Optional numeric metadata (NOT the grade) |

**`Chain`** — ordered list of links:
- `is_complete` — checks step continuity. `{0,1,2}` = complete, `{0,2}` = gap = munqaṭiʿ.
- `chain_status` — `COMPLETE` or `MUNQATI`.
- `narrator_ids` — ordered list of narrator identifiers.

**Completeness is epistemic.**  A chain with a gap is *munqaṭiʿ* and
automatically capped at ḍaʿīf regardless of narrator quality.  This comes
directly from hadith methodology — "we don't know what happened in that gap."

**How it connects:**
- `grades_for_chain(registry, chain)` — looks up each link's grade in the registry
- `store_claim(session, ...)` — persists to `rijal_claims` + `chain_links` tables
- `make_claim_id(text)` — deterministic SHA-256 claim_id for deduplication
- `normalize_claim_text(text)` — lowercase, strip, collapse whitespace

---

## Loop 2: The Registry (rijāl)

**Files:** `core/registry.py` (store: Narrator, Registry, RegistryDB),
`core/policies.py` (grading arithmetic: transition policies), `core/volatility.py` (freshness)

The computational equivalent of the classical rijāl compendium — a living,
evidence-driven registry of transmitter reliability.

### Key design decisions

**1. Domain-conditioned grading.**  The key is `(narrator_id, domain)` —
never just `narrator_id`.  A model precise on physics may be unreliable on
medicine.  Classical scholars did this too.

**2. Two axes per narrator.**  `adalah` (ʿadālah — integrity/manipulation-
resistance) and `dabt` (ḍabṭ — precision/error-rate) are stored separately:
- `AdalahGrade`: `HIGH` / `ACCEPTABLE` / `SUSPECT` / `COMPROMISED` / `UNASSESSED`
- `DabtGrade`: `HIGH` / `ACCEPTABLE` / `LOW` / `UNASSESSED`
- `NarratorGrade`: `RELIABLE` / `ACCEPTABLE` / `WEAK` / `REJECTED` / `UNGRADED`

The NarratorGrade is a composite that combines both axes at lookup time, but
the raw axes are preserved for diagnostic use.

**3. The jarḥ–taʿdīl state machine.**  Narrator grades evolve through named
evidence types, not formulas:

| Evidence type | What triggers it |
|---------------|-----------------|
| `EVAL_HARNESS` | Per-narrator evaluation harness result |
| `POST_HOC_AUDIT` | Audit of served claims |
| `CORROBORATION_OUTCOME` | Corroboration/contradiction with other chains |
| `HUMAN_REVIEW` | Human reviewer verdict |
| `VERSION_BUMP` | Model version change → reset to UNGRADED |
| `BOOTSTRAP_SEED` | Initial seed grade from benchmarks |

Each event is logged immutably.  The `TransitionPolicy` (pluggable Protocol)
decides whether the grade changes.

**4. Three transition policies (all in `core/policies.py`):**
- `ThresholdTransitionPolicy` — sliding window + edge trigger; 3 jarḥ = downgrade, 5 taʿdīl = upgrade
- `BayesianTransitionPolicy` (default) — Beta(α, β) per narrator; posterior mean → grade
- `CalibratedThresholdPolicy` — thresholds learned from calibration data

All three threshold policies share `threshold_transition`, which also encodes
the axis split (issue #9 follow-up): integrity (ʿadālah) jarḥ is permanent and
never ages out; precision (ḍabṭ) jarḥ is windowed and recoverable.

**5. REJECTED is sticky.**  Only explicit human review can restore from
REJECTED.  This is active containment, not a passive label.

### Narrator class

```
Narrator(
    narrator_id: str,
    domain_tag: str,
    narrator_type: NarratorType,  # SOURCE | SCRAPER | MODEL | HUMAN
    grade: NarratorGrade,
    adalah_grade: AdalahGrade,
    dabt_grade: DabtGrade,
    known_error_rate: float?,      # NULL = uncalibrated
    model_version: str?,
    model_family: str?,            # for madār detection
    upstream_source: str?,         # for shared-ancestry detection
    is_active: bool,
    graded_at: datetime?,          # freshness clock start
    valid_until: datetime?,        # freshness clock end
    evidence_log: list[dict],
)
```

### Registry class — key methods

| Method | What it does |
|--------|-------------|
| `register(narrator_id, domain, ...)` | Create or return existing narrator |
| `get(narrator_id, domain)` | Look up by composite key |
| `effective_grade(narrator_id, domain, now)` | Time-decayed grade with freshness status |
| `get_grade(narrator_id, domain)` | Effective grade, UNGRADED if unknown |
| `get_grade_for_link(narrator_id, domain, version)` | Resolve alias@version first |
| `get_metadata(narrator_id, domain)` | model_family, upstream_source for correlation detection |
| `record_evidence(...)` | Log evidence, re-evaluate grade via TransitionPolicy |
| `bump_version(...)` | Model version bump → reset to UNGRADED |
| `quarantine(...)` | Set REJECTED + COMPROMISED, deactivate |
| `flag_contradiction(...)` | Independent-chain contradiction → jarḥ evidence |
| `record_survival(...)` | Claim survived independent (endorsed) verification → taʿdīl; tazkiyah-guarded, claim-scoped dedup (issue #25) |
| `evidence_provenance(...)` | Report whether a grade is prior-derived or observation-backed (issue #6) |
| `renew_grade(...)` | Extend freshness window (corroboration proxy) |

### RegistryDB — persistence wrapper

Wraps `Registry` with SQLAlchemy: `load()` reads from DB, `flush()` writes
back.  Implements `RegistryPersistence` Protocol — swap for Redis, DynamoDB.

---

## Loop 3: Chain Grading (weakest-link)

**File:** `core/grading.py`

Combines per-link narrator grades into a single chain grade.  The rule:
**weakest link caps trust**, refined by transform type.

### The algorithm (RefinedWeakestLink)

```
floor = SAHIH  (start at best possible)

for each link in chain:
    if link is DESTRUCTIVE (extraction, chunking):
        floor = min(floor, link_grade)
        // Permanent floor. Nothing downstream recovers lost info.

    elif link is GENERATIVE (synthesis model):
        if corroborated AND grade >= ACCEPTABLE:
            floor = link_grade
            // Can REPAIR upstream damage (raise floor)
            // OR introduce corruption (lower floor)
        else:
            floor = min(floor, link_grade)

    else (PASS_THROUGH):
        floor = min(floor, link_grade)

if chain is incomplete (munqaṭiʿ):
    return DAIF

if any narrator is REJECTED:
    return MAWDU
```

### Why generative links can repair

The destructive/generative distinction comes from classical hadith:
- *riwāya bi-l-lafẓ* (verbatim transmission) — can only lose information
- *riwāya bi-l-maʿnā* (transmission by meaning) — transmitter's competence enters the chain

A scraper that drops tables (destructive) can only lose information.  A
synthesis model with broad pre-training (generative) *might* repair upstream
noise — but only when corroboration supports the repair.  The algorithm
gives generative links a conditional repair capability gated on corroboration,
while destructive links are permanent floors.

### Pluggable

`GradingStrategy` Protocol.  Swap `RefinedWeakestLink` for any implementation.

---

## Corroboration (mutābaʿāt)

**File:** `core/corroboration.py`

When multiple *independent* chains assert the same claim, trust can be
upgraded.  This is *mutābaʿāt* from hadith science.

### Independence detection (SharedLineageDetector)

```
Check 1: Shared narrator IDs?         → score = 0.0 (hard correlation)
Check 2: Shared model family?         → penalty = 0.4 per shared family
Check 3: Shared upstream source?      → penalty = 0.3 per shared source
Threshold: score ≥ 0.8                → considered independent
```

**The madār problem:** Naive set-disjointness of narrator IDs is explicitly
wrong.  Two chains with no shared narrators can still be correlated — same
base model family, same upstream source, one chain reading the other's output.
The detector catches this via shared upstream sources.

### Corroboration upgrade (CappedCorroborationPolicy)

- **Never reaches SAHIH** via corroboration alone (capped at HASAN)
- **At most one tier** upgrade
- **Minimum-grade gate**: at least one corroborating chain must be HASAN+
- **Information-theoretic**: combined error = ∏ p_i (multiplicative reduction)
- **Effective weight**: log-reduction / log(p_hasan). Must reach 2.0 for upgrade.

### CorroborationEngine

Operational engine: finds corroborating chains by exact text match or
pre-matched via `evaluate_direct()`.  Validated on Wikipedia + physics
textbooks (707 claim pairs, 100% fire rate, 8/8 negative controls).

---

## Loop 4: Content Criticism (matn)

**Files:** `critics/base.py`, `critics/embedding.py`, `critics/nli.py`, `critics/llm.py`

Evaluates whether a claim contradicts the existing corpus — *independent of
chain quality*.  This is *naqd al-matn* from hadith science.

### Protocol

```python
class ContentCritic(Protocol):
    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str,
    ) -> ContentVerdict: ...
```

Returns `CONSISTENT` / `CONTRADICTION` / `UNVERIFIABLE`.

### Implementations

| Critic | Mechanism | Quality | Requires |
|--------|-----------|---------|----------|
| `DeterministicRuleCritic` | Pattern matching | Stub (UNVERIFIABLE on real text) | Nothing |
| `EmbeddingCritic` | TF-IDF cosine similarity | Catches obvious contradictions | `scikit-learn` |
| `HybridCritic` | MiniLM retrieval → DeBERTa NLI | Good semantic coverage | `sentence-transformers` |
| `LocalNLICritic` | DeBERTa cross-encoder | Best offline quality | `sentence-transformers` |
| `LLMCritic` | LLM-prompted judgment | Highest quality | API key |

### Key principle

Chain grading and content criticism are **fully decoupled**.  They never read
each other's internals.  They combine only at the decision matrix.

---

## The Decision Matrix

**File:** `core/decision.py`

The 4×2 router: chain_grade × content_verdict → action.

```
                 CONSISTENT              CONTRADICTION
SAHIH            SERVE (cache)           REVIEW (ʿilal — highest-value case)
HASAN            SERVE_WITH_CAVEAT       REVIEW (hold; do not serve)
DAIF             REVIEW (seek corrob.)   QUARANTINE
MAWDU            REJECT_AND_QUARANTINE   REJECT_AND_QUARANTINE
```

**Three key defaults:**
1. Contradictions go to humans by default (LLMs are unreliable at reconciling
   competing evidence).
2. The ṣaḥīḥ × contradiction cell is the system's **most informative signal** —
   either a trusted source changed the world's state, or the corpus has a
   latent defect.
3. The mawḍūʿ tier is **active containment**, not passive labeling.  A source
   attempting prompt injection gets quarantined, not "low confidence."

---

## Grade Freshness & Time Decay

**Files:** `core/volatility.py`, `core/registry.py` (effective_grade)

A narrator grade is a truth-statement about a **window of time**, not a
permanent attribute.

### Three windows (VolatilityPolicy)

```
      graded_at ──────── stale_start ──────── valid_until ────────>
         │                    │                     │
         ├── FRESH ──────────┤── STALE ─────────────┤── EXPIRED ──
         │  grade as stored   │  downgraded 1 tier   │  UNGRADED
         │                    │  needs_recheck       │  needs_recheck
```

- `FRESH`: within TTL — grade used as-is
- `STALE`: in grace window — downgraded one tier, flagged `needs_recheck`
- `EXPIRED`: past best-before — reverts to UNGRADED
- `REJECTED` never decays (active containment)

### Stale downgrade path

```
RELIABLE → ACCEPTABLE → WEAK → UNGRADED
```

### Corroboration as freshness renewal

`renew_grade()` extends the window when independent chains keep agreeing —
corroboration is a proxy freshness signal.  `flag_contradiction()` is
event-driven invalidation: immediately logs jarḥ evidence.

---

## Narrator Identity & Versioning

**File:** `core/identity.py`

Grades are keyed by `alias@version`.  An endpoint alias ("gpt-4o") keeps its
name while the model behind it changes — a grade attached to the alias
silently survives the swap.  Resolving the version fixes this.

```
resolve_narrator_id("model:gpt-4o", "gpt-4o-2024-08-06")
→ "model:gpt-4o@gpt-4o-2024-08-06"
```

**Non-resolved tags:** `latest`, `dev`, `canary`, `unknown`, `""` are treated as
aliases, not versions.  They silently drift — the registry doesn't key on them.

**Version bump:** `bump_version()` resets the narrator to UNGRADED.  A model
version bump is a new narrator, not inherited reputation.

---

## Persistence Layer

**Files:** `storage/base.py`, `storage/sqlalchemy.py`, `models.py`

### Tables (SQLAlchemy ORM)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `rijal_claims` | One row per claim | claim_id, claim_text, narrator_chain (JSONB), chain_grade |
| `chain_links` | Normalized link table | claim_id (FK), step, narrator_id, version, transform_type |
| `narrator_registry` | One row per (narrator, domain) | narrator_id, domain_tag, grade, model_family, upstream_source |
| `narrator_evidence` | Append-only jarḥ–taʿdīl log | narrator_id, domain_tag (FK), evidence_type, action |
| `review_queue` | Claims awaiting human adjudication | claim_id, chain_grade, content_verdict, matrix_action |

### Database support

- **PostgreSQL** — production
- **SQLite** — development/testing (default, no server needed)

### RegistryPersistence Protocol

```python
class RegistryPersistence(Protocol):
    def load(self) -> None: ...
    def flush(self) -> None: ...
    def get_grade(self, narrator_id, domain_tag) -> NarratorGrade: ...
    def get_metadata(self, narrator_id, domain_tag) -> dict: ...
```

Swap for Redis, DynamoDB, etc.

---

## API Layer

**Files:** `api/app.py`, `api/endpoints/*.py`, `api/auth.py`, `api/dependencies.py`

FastAPI application with three endpoint groups:

### Endpoints

| Group | Prefix | Purpose |
|-------|--------|---------|
| Health | `/health`, `/metrics` | Liveness check + Prometheus metrics |
| Claims | `/api/claims` | Submit claim for grading, list claims, review queue |
| Narrators | `/api/narrators` | Register narrators, query grades, get evidence log |

### POST /api/claims (submit for grading)

Accepts a chain of link specs.  Runs the full pipeline:
1. Build chain from link specs
2. Look up grades from registry
3. Detect version drift (versioned link has no grade but sibling alias does)
4. Compute chain grade (weakest-link)
5. Check corroboration
6. Run content criticism
7. Route through decision matrix
8. Return verdict

### Dependency injection

`get_registry()` returns a cached `RegistryDB` instance.  Override via
`app.dependency_overrides` for testing.  API key auth via `auth.py`.

---

## CLI

**File:** `cli/main.py`

Two commands:

```bash
isnad serve              # Start API server (uvicorn)
isnad seed --config      # Seed narrators from ISNAD_SEED_CONFIG env var
```

Environment variables: `ISNAD_HOST`, `ISNAD_PORT`, `ISNAD_DATABASE_URL`,
`ISNAD_SEED_CONFIG`.

---

## Trace Capture (LangChain)

**File:** `integrations/langchain/callback.py`

Automatically instruments a LangChain pipeline to capture an `isnad_trace
v0.1` JSON document.

### IsnadCallbackHandler

```python
from isnad.integrations.langchain import IsnadCallbackHandler, seed_registry

reg = seed_registry({"source:my-docs": "reliable", "model:gpt-4o": "acceptable"})
handler = IsnadCallbackHandler(registry=reg, domain="physics")
chain.invoke("What is F=ma?", config={"callbacks": [handler]})
trace = handler.to_trace()  # isnad_trace v0.1 JSON
```

### How it works

1. Implements LangChain's `BaseCallbackHandler`
2. LangChain passes `run_id` and `parent_run_id` to every lifecycle method —
   the tree is free
3. `on_chain_start` → creates a transmitter node
4. `on_retriever_end` → records retrieved documents as `DocumentRef` (source +
   doc_id + content hash, NOT full content)
5. `on_llm_start` → captures model version from `ls_model_name` metadata;
   records prompt hash
6. `on_llm_end` → extracts output claim from response
7. `on_chain_end` → finalizes; `to_trace()` produces the JSON

### Tree reconstruction

`_build_chain()` walks from root (node with no parent) to leaves, assigning
steps in transmission order.  Nodes are ordered by position in the tree, not
by timestamp.

### Shared ancestry detection

`_detect_shared_ancestry()` checks four signals:
1. Shared narrator IDs
2. Overlapping document content hashes
3. Shared upstream sources
4. Shared model families

Returns `shared_ancestry_detected` if any found.

### Safety

- Every callback wrapped in try/except — never breaks the user's pipeline
- Content redacted by default (only hashes, not full text)
- Full content capture is opt-in (`capture_full_content=True`)

### Async support

`AsyncIsnadCallbackHandler` implements `AsyncCallbackHandler` — delegates to
the sync handler.

---

## Trace Schema v0.1

**File:** `trace/schema.py`, spec: `docs/trace-schema.md`

Versioned JSON contract between capture and rendering.  Aligned with W3C
PROV-DM and PROV-AGENT (arXiv 2508.02866).

### Key structures

| Model | Role | Key fields |
|-------|------|------------|
| `TraceV01` | Root document | claim_text, chain, corroborating_chains, chain_integrity, origin_strength, independence, contradictions, binding_constraint |
| `TransmitterNode` | One chain step | node_id, parent_ids, role, narrator_id, model_version, input_documents, output_claim, grade |
| `Grade` | Per-narrator score | chain_integrity, adalah, dabt, origin_strength, model_version, model_family, upstream_source |
| `DocumentRef` | Input provenance | source, doc_id, content_hash |
| `CorroborationVerdict` | Independence status | verified / unverified / shared_ancestry_detected |
| `ContradictionFlag` | Conflicting claims | claim_a, chain_a_node_ids, claim_b, chain_b_node_ids |

### Two axes, never collapsed

- `chain_integrity` — how soundly was the claim transmitted?  (ṣaḥīḥ/ḥasan/ḍaʿīf/mawḍūʿ)
- `origin_strength` — how trustworthy is the SOURCE?  (verified/attested/reputable/unknown/suspect/compromised)

A ḍaʿīf chain from a verified origin must be distinguishable from a ṣaḥīḥ
chain from an unknown origin.

### PROV mapping

| W3C PROV | isnad_trace v0.1 |
|----------|-----------------|
| `prov:Entity` | `DocumentRef` |
| `prov:Activity` | `TransmitterNode` |
| `prov:Agent` | `(narrator_id, role)` |

---

## Chain Viewer

**File:** `viewer/index.html`

Self-contained HTML component.  Open in any browser — no server needed.
Three hand-built fixtures demonstrate the framework's key signals.

### Design

- **Default state:** Collapsed.  One line: claim + band + binding constraint.
- **Expanded:** Origin → chain nodes → corroborating chains → diagnosis →
  validated/indicative table.
- **Weakest link** gets vermilion left-border with "BINDING CONSTRAINT" label.
- **`shared_ancestry_detected`** renders as a warning, not consensus.
- **Fixture 3** (false corroboration) is the default view.

### Discipline

- No numeric confidence (never `87.3`) — ordinal bands only
- No colour-alone encoding — badges always have text
- `prefers-reduced-motion` respected
- Keyboard focus visible
- Every view has "What's Validated vs. Indicative"

---

## LangChain Integration (older tracer + decorator)

**Files:** `integrations/langchain/tracer.py`, `helpers.py`, `decorator.py`

### IsnadTracer (older, flat-list)

Predecessor to `IsnadCallbackHandler`.  Produces a flat list of links (not a
tree from run_id).  Has a built-in `report()` method for human-readable output.
Still available for backward compatibility.

### seed_registry()

```python
reg = seed_registry({
    "source:my-docs": "reliable",
    "model:gpt-4o": "acceptable",
})
```

Builds a Registry from a simple dict.  Warm-start is **required** for
practical coverage — cold-start produces ~10% coverage.

### @isnad_track

Decorator for simple functions not using the full callback machinery:

```python
@isnad_track(registry=reg, narrator_id="my-model")
def answer_question(query: str) -> str:
    return llm.invoke(query)
```

### CriticAdapter

Wraps any callable as a ContentCritic.  Includes a reference LLM-backed
example using Anthropic.

---

## The Full End-to-End Flow

```
 1. Pipeline runs (LangChain, manual, PROV-AGENT)
         │
 2. Callback handler captures run_id/parent_run_id tree
         │
 3. to_trace() → isnad_trace v0.1 JSON
         │
 4. Registry looks up narrator grades per (narrator, domain)
    (time-decayed via effective_grade)
         │
 5. grade_chain() computes weakest-link with transform-type refinement
         │
 6. CorroborationEngine checks for independent corroborating chains
    (madār detection via SharedLineageDetector)
         │
 7. ContentCritic evaluates the claim against the corpus
    (independent of chain quality)
         │
 8. Decision matrix routes: serve / review / quarantine
         │
 9. Viewer renders the trace: collapsed → expanded → diagnosis
         │
10. Evidence feeds back into the registry (jarḥ–taʿdīl loop)
    (grade transitions, freshness renewal, version bumps)
```

Every step is pluggable.  Every parameter is a Protocol.  The framework makes
no claims it can't defend.

---

## Where to Start Contributing

### First-time contributors

1. **Read `types.py`** — understand the ordinal types, enums, and Protocols
2. **Run the demo:** `python examples/isnad_langchain_demo.py`
3. **Open the viewer:** open `viewer/index.html` in a browser, explore all 3
   fixtures
4. **Read the paper:** arXiv 2607.24117 — especially §4 (framework) and §8
   (validation)

### Good first issues

- Implement an alternative `ContentCritic` (sentence-transformers, CrewAI)
- Write a seed-grade bootstrapper from published benchmark data
- Extend semantic corroboration to multi-source corpora
- Add a new fixture demonstrating a specific failure mode

### Architecture-level contributions

- Swap `TransitionPolicy` for a new grading approach (beyond
  Bayesian/Threshold)
- Implement a new `CorrelationDetector` (embedding-based blind spot detection)
- Add cross-run corroboration to the callback handler
- Build a live viewer that fetches traces from a running API

### Key principles when contributing

- **Grades are ordinal, never numeric.**  No `87.3%`.  Use named bands.
- **Chain integrity and origin strength are separate axes.**  Never collapse
  them.
- **Independence is a first-class enum**, never a silent boolean.
- **Be honest about limits.**  If a mechanism is unvalidated, the UI and docs
  say so.
- **Everything is pluggable.**  Every strategy is a Protocol — swap without
  touching the rest.
