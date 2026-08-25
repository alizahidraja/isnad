# Isnād–Rijāl Framework

**ISNAD grades the sources behind every claim your AI system produces — and tells you what to do about it.** Every claim carries a complete transmission chain; every transmitter carries a reliability grade that moves with evidence; chains are graded by their weakest link and routed to an action: accept, review, or quarantine.

*(The name and the design descend from 1,200 years of hadith transmission science — the lineage is the reason to believe the design is sound, not a prerequisite for using it.)*

> **Paper:** [arXiv:2607.24117](https://arxiv.org/abs/2607.24117) | **Paper DOI:** [10.48550/arXiv.2607.24117](https://doi.org/10.48550/arXiv.2607.24117) | **Software DOI:** [10.5281/zenodo.21216873](https://doi.org/10.5281/zenodo.21216873)

[![CI](https://github.com/alizahidraja/isnad/actions/workflows/ci.yml/badge.svg)](https://github.com/alizahidraja/isnad/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-2607.24117-b31b1b.svg)](https://arxiv.org/abs/2607.24117)

**🌐 Full project home: https://alizahidraja.com/isnad**

---

## What & Why

In modern AI pipelines, a factual claim passes through many hands — a scraper
extracts it, a model compiles it, another serves it. Each hand can drop, distort,
or invent. Existing tools record *what* happened. ISNAD grades *who* transformed
the claim, so it can tell you **how much to trust the result**.

The framework adapts **hadith transmission science** — one of history's most
rigorous epistemologies, refined over twelve centuries — into a Python library
for AI systems. Every claim carries its complete chain of transmitters (isnād);
each transmitter is graded in a living registry (rijāl); chains are evaluated
by their weakest link; content is criticized independently of transmission
quality; and the two combine in a decision matrix that routes claims to
serve, review, or quarantine.

---

## Audit & Compliance Evidence

ISNAD can **export a tamper-evident audit record** for any graded claim — a
machine-readable artifact for governance record-keeping. One command:

```bash
isnad export --claim <id> --format json    # or jsonl|csv; --verify; --redact; --chain-log
```

Each record captures the full chain (who handled the claim, in order, as an
explicit **DAG** via `upstream_ids`), the weakest link, source-document hashes,
**human-oversight evidence**, the environment, and a SHA-256 integrity hash
over the RFC 8785-canonical form of its own payload — plus an optional
tamper-evident hash chain (no blockchain) and a PII-redaction hook.

**Who this is for:** teams running production AI who will be asked what their
system did and how they know. The record answers that question; it does not
answer "are we compliant?"

**ISNAD produces evidence artifacts; it does not confer conformity with any
regulation.** See [`docs/evidence-mapping.md`](docs/evidence-mapping.md) for an
*informational* (not legal) mapping of each field to the EU AI Act, ISO/IEC
42001, the NIST AI RMF, and the SDAIA framework — and the explicit statement of
what ISNAD deliberately does *not* provide.

```python
from isnad.audit import build_audit_record

record = build_audit_record(claim_id, session, registry)  # -> AuditRecord
assert record.integrity.record_hash == canonical_hash(record.to_dict(include_integrity=False))
```

Demos (no API keys): [`examples/audit_export_langchain.py`](examples/audit_export_langchain.py),
[`examples/multi_agent_handoff.py`](examples/multi_agent_handoff.py),
[`examples/multi_agent_dag.py`](examples/multi_agent_dag.py) (branching DAG +
the honest miss), [`examples/ci_gate.py`](examples/ci_gate.py) (fail a build on
a degraded chain).

---

## Scope and limitations

ISNAD grades **post-entry provenance** — who handled a claim after it entered
your pipeline and how much you trust them — not whether the upstream source or
the final answer is objectively true.

**What ISNAD covers:**

- Ordered transmission chains (isnād) and narrator grades (rijāl)
- Weakest-link chain grading and the serve / review / quarantine decision matrix
- Matn (content) criticism **against your existing corpus** — contradiction detection
- Corroboration when **independent** chains agree (with lineage / madār discounting)

**What ISNAD does not cover:**

- **Source legitimacy at the boundary** — ISNAD does not verify that a URL,
  publisher, or retriever `metadata["source"]` is authentic. Registry grades are
  **operator-assigned assertions**, not auto-verified facts.
- **Novel claim truth** — matn catches contradictions with known corpus; claims
  that are new and unverifiable are not auto-fact-checked against ground truth.
- **Faithful transmission of bad input** — a `RELIABLE` fake publisher plus a
  clean pipeline can yield a high chain grade. ISNAD reports faithful handling,
  not source truth.

**Boundary vetting is the operator's responsibility.** Before a source enters
the pipeline:

- Vet sources before registering them as `RELIABLE` (allowlists, domain
  verification, human onboarding)
- Register unknown sources as `UNGRADED` with `adalah=SUSPECT` until vetted
- Do not treat LangChain retriever source tags as verified identity — map URLs
  to pre-vetted narrator IDs
- Use matn, corroboration, and human review as **downstream** gates; they narrow
  risk but do not replace boundary vetting

See Component-level validation status and endpoint-identity behavior
in [What's Validated vs. What's Not](#whats-validated-vs-whats-not) and
[Endpoint identity](#endpoint-identity-model-version-drift) below.

---

## 30-Second Quickstart

```bash
pip install isnad
```

```python
from isnad import Registry, grade
from isnad.types import NarratorGrade

reg = Registry()
reg.register("openstax", "physics", grade=NarratorGrade.RELIABLE)
reg.register("pdf-scraper", "physics", grade=NarratorGrade.UNGRADED)
reg.register("ingest-model", "physics", grade=NarratorGrade.ACCEPTABLE)

verdict = grade("p = mv", ["openstax", "pdf-scraper", "ingest-model"], reg, domain="physics")
print(verdict.why)
# 'claim "p = mv" → chain DAIF (weakest: pdf-scraper, ungraded → ḍaʿīf by default)'
```

The full expert API (chain objects, critics, the decision matrix) is below.

## 60-Second Quickstart (expert API)

```bash
pip install isnad
```

```python
from isnad import Registry, Chain, ChainLinkSpec, grade_chain, decide
from isnad.types import NarratorGrade, ContentVerdict
from isnad.critics import EmbeddingCritic

# Build a chain: source → scraper → model
chain = Chain([
    ChainLinkSpec("openstax-textbook", 0, domain="physics"),
    ChainLinkSpec("pdf-scraper-v2", 1),
    ChainLinkSpec("ingest-model-v3", 2),
])

# Seed-grade known narrators (operator-assigned — see Scope and limitations)
reg = Registry()
reg.register("openstax-textbook", "physics", grade=NarratorGrade.RELIABLE)
reg.register("pdf-scraper-v2", "physics", grade=NarratorGrade.RELIABLE)
reg.register("ingest-model-v3", "physics", grade=NarratorGrade.ACCEPTABLE)

# Grade the chain
grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
transforms = [l.transform_type for l in chain.links]
chain_grade = grade_chain(grades, transforms, is_complete=True)

# Content criticism (now functional — embedding-based)
critic = EmbeddingCritic()
verdict = critic.evaluate("p = h/λ", "p = h/lambda", ["p = mv"])
action = decide(chain_grade, verdict)

print(f"Chain: {chain_grade.value.upper()} | Content: {verdict.value} | Action: {action.value}")
```

### LangChain Integration (5 lines)

```bash
pip install isnad[langchain]
```

```python
from isnad.integrations.langchain import IsnadCallbackHandler, seed_registry

reg = seed_registry({"source:docs": "reliable", "model:gpt-4o": "acceptable"})  # operator-assigned grades
handler = IsnadCallbackHandler(registry=reg, domain="physics")
chain.invoke("What is F=ma?", config={"callbacks": [handler]})
trace = handler.to_trace()  # isnad_trace v0.1 JSON
```

Also available: `IsnadTracer` (older flat-list reporter with built-in report()) and
`AsyncIsnadCallbackHandler` for async pipelines.

**The policy layer — `IsnadMiddleware`.** The callback *captures* traces; the
middleware *gates* claims — it grades each tool output and model response the
moment they enter the agent and blocks (quarantines) MAWDU chains. Framing:
*"PIIMiddleware stops sensitive data leaving; IsnadMiddleware stops untrustworthy
claims entering."*

```python
from isnad.integrations.langchain import IsnadMiddleware

mw = IsnadMiddleware(reg, domain="physics")  # wrap_tool_call grades + gates
```

See `examples/langchain_middleware_demo.py`. The listable shape is the
`langchain-isnad` PyPI package (see issue #63).

---

## What's Validated vs. What's Not

| Component                     | Status              | Notes                                                                 |
| ----------------------------- | ------------------- | --------------------------------------------------------------------- |
| **Bayesian grading**          | ✅ Default           | Beta-distribution replaces hardcoded thresholds; ISNAD_POLICY env override |
| **Weakest-link quarantine**   | ✅ Validated         | 100% of REJECTED narrator claims correctly blocked                    |
| **jarḥ–taʿdīl discovery**     | ✅ Partial           | Correctly identifies bad narrators; good ones need seed grades        |
| **Seed-grade bootstrapping**  | ✅ Validated         | Pre-grading sources/models improves coverage from ~5% to ~10%; critical for non-zero serving; ISNAD_SEED_CONFIG env var |
| **Corroboration (mutābaʿāt)** | ✅ Empirically validated | 603/603 (100%) on Wikipedia; 104/104 (100%) on physics textbooks; 8/8 negative controls pass; madār detection blocks correlated chains |
| **Content criticism**         | ✅ Functional        | Tiered: LLMCritic (~90% semantic, needs key) > HybridCritic/LocalNLI (~30–40%, offline) > EmbeddingCritic (word-overlap). `best_available_critic()` picks the best runnable one — see `docs/critics.md` |
| **Semantic matching**         | ✅ Validated         | Cross-source embedding matching (MiniLM) across Wikipedia and physics corpora |
| **LangChain integration**     | ✅ Ready             | IsnadTracer callback handler, seed_registry helper, 9 integration tests pass |
| **Confidence-gating**         | ❌ Useless           | Self-confidence scores uncorrelated with defects                      |
| **Evidence provenance**       | ✅ Implemented       | `evidence_provenance()` reports whether a grade is prior-derived (benchmark) or observation-backed (audit/corroboration) — issue #6 |
| **Survival primitive**        | ✅ Implemented       | `record_survival()` records that a claim survived independent (endorsed) verification — issue #25 |
| **Per-role precision**        | ✅ Implemented       | Precision (ḍabṭ) graded per (narrator, role, domain); integrity stays per-narrator — issue #3 |
| **Integrity ladder (Bayesian)** | ✅ Implemented     | Default policy enforces integrity strikes-per-tier — a permanent ʿadālah ceiling that precision cannot lift — issue #30 |
| **Precision recoverability**  | ✅ Implemented       | Precision-driven REJECTED is recoverable; only integrity (COMPROMISED) is sticky — issue #40 |
| **Period-sliced grades**      | ✅ Implemented       | `get_grade_as_of()` re-derives a narrator's grade at any past instant — the ikhtilāṭ remedy — issue #43 |
| **End-to-end benchmark**      | ✅ Measured          | Adversarial corruption-detection: weak narrators 100% caught, 0 false positives; the content critic is the binding constraint — issue #50 |
| **ISNAD-Bench (classical ground truth)** | ✅ Measured | Weakest-link grading vs 577,024 scholar-graded chains: Cohen's κ = 0.87 strict / 0.76 lenient (shuffled control 0.05); human ceiling = scholars-vs-scholars κ = 0.33; 88% of the remaining gap is mutābaʿa — `bench/docs/RESULTS.md` |

**Ungraded-narrator policy.** An *ungraded* narrator caps a chain at **ḍaʿīf** by
default — the classical treatment of a *majhūl* (unknown) narrator, whom scholars
judged weak. Pass `lenient_unknown=True` to `grade_chain(...)` to instead cap
at ḥasan (epistemic humility: no evidence → refuse ṣaḥīḥ, don't punish the
absence of a grade). ISNAD-Bench measures the gap between the two at 0.11 κ
(0.87 strict vs 0.76 lenient); the choice is documented, not hidden.

### Deep dives — the honesty box

The four hardest design decisions, and where the framework draws the line:

- **Evidence provenance** — a grade is either a *prior* (benchmark seed) or an
  *observation* (audit/corroboration). `evidence_provenance()` makes the
  distinction visible; priors are assumptions, not evidence. (issue #6)
- **Survival** — `record_survival()` records that a claim survived independent
  verification. Claim-scoped, tazkiyah-guarded (self-verified seals refused),
  and a precision signal only — it never rehabilitates a quarantined narrator.
  (issue #25)
- **Per-role precision** — precision (ḍabṭ) is graded per (narrator, role, domain);
  integrity (ʿadālah) stays per narrator — a model can extract faithfully yet
  over-reach when synthesizing. (issue #3) — `docs/rfc-issue3-role-grading.md`
- **Endpoint identity** — model grades are keyed `alias@version`; a version bump
  is a new narrator, not inherited reputation. (paper §4.2)

**Honest limits:** cold-start is worse per-role; integrity is domain-scoped, not
global; sub-quarantine integrity strikes are per-role (cross-role propagation is
future work). The honesty box is a feature — we say exactly what works, what is
limited, and where you supply your own components.

## ISNAD-Bench — measured against 1,200 years of ground truth

The strongest evidence ISNAD works is not a claim — it's a number.
**ISNAD-Bench** grades 577,024 real hadith chains (each graded by classical
scholars) with ISNAD's weakest-link rule and measures agreement:

| Quantity | Cohen's κ |
|---|---:|
| **ISNAD vs scholarly consensus** (strict default) | **0.871** |
| a single scholar vs consensus | 0.450 |
| scholars vs scholars (the human ceiling) | 0.331 |

**How to read it:** ISNAD reproduces the scholars' *consensus* at κ = 0.87 — not
because it is "better than the scholars" (they disagree with each other at
κ = 0.33), but because it faithfully implements their method. The benchmark is
preregistered, carries negative controls (shuffled grades → κ = 0.05), and
buckets every disagreement. Full write-up:
[`bench/docs/RESULTS.md`](bench/docs/RESULTS.md).

```bash
uv run python -m bench.run               # strict (default), full corpus
uv run python -m bench.run --lenient     # ungraded → ḥasan
uv run python -m bench.human_ceiling     # the human ceiling
uv run python -m bench.ikhtilat          # the mukhtaliṭūn (period-sliced grades)
```

The dataset (`emadjumaah/hadith-kg`, CC-BY-4.0, 1.6 GB) is gitignored and pinned
by SHA-256 — see [`bench/README.md`](bench/README.md) for the audit discipline
that produced this.

---

## Concept → Module Map

| Concept                       | What it does                                         | Module                     |
| ----------------------------- | ---------------------------------------------------- | -------------------------- |
| **isnād** (chain)             | Ordered, gap-checked transmission chain per claim    | `isnad/core/chain.py`      |
| **rijāl** (registry)          | Graded narrator store per (alias@version, domain)    | `isnad/core/registry.py`   |
| **jarḥ–taʿdīl**               | Evidence-driven state machine for narrator grades    | `isnad/core/policies.py`   |
| **Bayesian grading**          | Beta-distribution narrator grades (default)          | `isnad/core/policies.py`   |
| **Threshold policies**        | Sliding-window + edge-trigger + axis split           | `isnad/core/policies.py`   |
| **ittiṣāl**                   | Completeness as epistemic property (gap → DAIF)      | `isnad/core/chain.py`      |
| **Weakest-link grading**      | Chain grade = refined minimum over narrators         | `isnad/core/grading.py`    |
| **mutābaʿāt** (corroboration) | Independent-chain upgrade + madār detection          | `isnad/core/corroboration.py` |
| **matn criticism**            | Content evaluated independently of chain quality     | `isnad/critics/`           |
| **Decision matrix**           | 4×2 (chain × content) → action router                | `isnad/core/decision.py`   |
| **Persistence**               | SQLAlchemy-backed registry (swap via protocol)       | `isnad/storage/`           |
| **API**                       | FastAPI service with DI + Prometheus metrics         | `isnad/api/`               |
| **CLI**                       | `isnad serve` | `isnad seed`                        | `isnad/cli/`               |
| **ʿadālah / ḍabṭ**            | Integrity and precision as two distinct axes         | `isnad/types.py`           |

> 🗺️ **Full architecture diagram:** [`docs/ARCHITECTURE.drawio`](docs/ARCHITECTURE.drawio) — 3 tabs: System Architecture, Claim Lifecycle (data flow), and Validation Matrix (what's proven vs what's not). Open in [draw.io](https://app.diagrams.net/) or VS Code Draw.io extension.

---

## The Decision Matrix

|                         | Content CONSISTENT               | Content CONTRADICTION                          |
| ----------------------- | -------------------------------- | ---------------------------------------------- |
| **Ṣaḥīḥ** (sound chain) | **SERVE** — cache                | **REVIEW** — ʿilal signal (highest-value case) |
| **Ḥasan** (good chain)  | **SERVE WITH CAVEAT**            | **REVIEW** — hold, do not serve                |
| **Ḍaʿīf** (weak chain)  | **REVIEW** — seek corroboration  | **QUARANTINE**                                 |
| **Mawḍūʿ** (fabricated) | **REJECT + QUARANTINE NARRATOR** | **REJECT + QUARANTINE NARRATOR**               |

---

## Pluggable Strategies — Extend It

The framework leaves key parameters open by design (paper §4.2/§4.3). Swap any:

| Strategy              | Protocol                | Default                          | What to provide                       |
| --------------------- | ----------------------- | -------------------------------- | ------------------------------------- |
| `GradingStrategy`     | `isnad/types.py`        | `RefinedWeakestLink`             | How links combine into chain grade    |
| `TransitionPolicy`    | `isnad/types.py`        | `BayesianTransitionPolicy`       | Evidence → narrator grade transitions |
| `CorroborationPolicy` | `isnad/types.py`        | `CappedCorroborationPolicy`      | Independent chains → claim upgrade    |
| `CorrelationDetector` | `isnad/types.py`        | `SharedLineageDetector`          | True independence between chains      |
| `ContentCritic`       | `isnad/critics/base.py` | `HybridCritic` / `EmbeddingCritic` | Content contradiction detection       |

**Swap a critic in one line:**

```python
from isnad.critics import best_available_critic, EmbeddingCritic, LLMCritic

critic = best_available_critic()           # strongest offline critic (NLI if installed, else TF-IDF)
critic = best_available_critic(prefer_llm=True)  # use the LLM tier if a key is present
critic = EmbeddingCritic()                 # TF-IDF, always works, obvious contradictions
critic = LLMCritic(provider="openrouter", model="openai/gpt-4o-mini")  # any LLM via OpenRouter
```

Critic tiers are documented with their measured recall in
[`docs/critics.md`](docs/critics.md) — the honest headline is that the semantic
gap is solved by the LLM tier (~90%), while the no-key ceiling is NLI (~40%).

The LLM critic is **provider-agnostic** — OpenRouter, OpenAI, DeepSeek, Anthropic,
Gemini, Groq, Together, or any OpenAI-compatible endpoint (including a local
Ollama server).  Name a provider, or set `ISNAD_LLM_PROVIDER` + a key env var.
`list_providers()` enumerates the known providers.

**Good first issues:**
- Implement an alternative critic (sentence-transformers embedding, CrewAI integration)
- Seed-grade bootstrapper from published benchmark data
- Extend semantic corroboration to multi-source corpora (ArXiv, textbooks, news)

---

## Trace Capture & Chain Viewer

ISNAD ships a **capture → schema → viewer** pipeline that makes transmission
chains visible. The contract is [isnad_trace v0.1](docs/trace-schema.md) — a
versioned JSON schema aligned with W3C PROV-DM and PROV-AGENT (arXiv 2508.02866).

### Capture (LangChain callback)

```python
from isnad.integrations.langchain import IsnadCallbackHandler, seed_registry

reg = seed_registry({"source:my-docs": "reliable", "model:gpt-4o": "acceptable"})
handler = IsnadCallbackHandler(registry=reg, domain="physics")

# Attach to any LangChain/LangGraph pipeline
chain.invoke("What is F=ma?", config={"callbacks": [handler]})

trace = handler.to_trace()
print(trace.model_dump_json(indent=2))  # isnad_trace v0.1
```

Key properties:
- **Tree from run_id/parent_run_id** — LangChain already provides the tree;
  the handler reconstructs it without timestamps or heuristics.
- **Input provenance** — every retrieved document is recorded with source,
  doc_id, and content hash. Full content is redacted by default.
- **Model version captured** — resolved model version (e.g. `gpt-4o-2024-08-06`)
  from response metadata, not the endpoint alias. Records `null` explicitly when
  unavailable.
- **Shared ancestry detection** — overlapping retrieval sets, shared model
  families, or shared upstream sources are flagged as
  `shared_ancestry_detected`.
- **Never breaks your pipeline** — every callback is wrapped in try/except.
- **Async support** — `AsyncIsnadCallbackHandler` for async LangChain runs.

**Runnable demo** (no API keys required):
```bash
python examples/isnad_langchain_demo.py
```

### Viewer

Open `viewer/index.html` in a browser. Three hand-built fixtures demonstrate
the framework's key signals:

| Fixture | What it shows |
|---------|--------------|
| 1. Clean chain | Ṣaḥīḥ-tier chain, verified independent corroboration (OpenStax + HyperPhysics). Baseline. |
| 2. Weak extraction | Ḍaʿīf chain (gpt-3.5-turbo at 18% error rate) but **verified origin**. Two axes kept separate. |
| 3. False corroboration | Five transmitters across three chains, all tracing to one NOAA source. Renders as a **warning**, not consensus. |

The viewer renders fixture 3 by default — it is the most important case.

### What the viewer shows — and what it doesn't

**Validated signals** (mechanisms confirmed empirically or structurally):

| Signal | Status | Source |
|--------|--------|--------|
| Weakest-link chain grading | ✅ Validated | §8 experiment: 100% of REJECTED narrator claims correctly blocked |
| jarḥ–taʿdīl narrator discovery | ✅ Partial | Correctly identifies injected weak narrators; requires seed grades |
| Corroboration negative controls | ✅ Validated | 8/8 correctly rejected; madār detection blocks correlated chains |
| Two-axis separation (chain ≠ origin) | ✅ Structural | Schema enforces separate enums; viewer renders them independently |
| Tree reconstruction from run_id/parent_run_id | ✅ Structural | Tested: linear chains, siblings, missing parents handled safely |

**Indicative signals** (displayed honestly, not validated):

| Signal | Status | Honest limit |
|--------|--------|-------------|
| Independence detection | ⚠ Indicative | Structural only (shared doc hashes, upstream sources, model families). Does not detect correlated training data or shared model blind spots. |
| Narrator grades | ⚠ Indicative | Only calibrated where seed-grade data exists. Cold-start coverage is ~10%. |
| Corroboration fire rate | ⚠ Corpus-dependent | 100% on Wikipedia; rarely fires on dense technical corpora (5/20K). |
| Origin strength | ⚠ Indicative | Derived from ʿadālah grade. No cryptographic attestation (complementary: Live Verify). |
| Content verdict | ⚠ Not captured | The trace schema has space for `content_verdict` but the callback handler does not populate it — the bundled critic is a stub on real text. |

**What is NOT shown:**
- No numeric confidence (never `87.3`). Grades are ordinal bands: ṣaḥīḥ/ḥasan/ḍaʿīf/mawḍūʿ.
- No colour-alone confidence encoding. The viewer respects `prefers-reduced-motion` and visible keyboard focus.
- No collapsed axes. Chain integrity and origin strength are always separate.
- No implicit corroboration. `unverified` independence is not rendered as agreement.

---

## Live Verify Integration

ISNAD composes with [**Live Verify**](https://github.com/live-verify/live-verify) — Paul
Hammant's cryptographic document-attestation protocol. Live Verify seals a
document's **visible text** to an issuer's **domain** via a SHA-256 hash plus a
`verify:` lookup; anyone can confirm the document is unaltered and issuer-attested.

The two frameworks answer the same question from opposite ends of the pipeline.
A Live Verify seal is an **ideal high-trust narrator input** to an ISNAD chain:
its integrity axis (ʿadālah) is anchored by cryptography rather than by
accumulated track record — bootstrapping a source narrator to a high grade
**on day one**, solving the cold-start problem.

```python
from isnad.integrations.liveverify import verify_claim, register_sealed_source
from isnad.core.registry import Registry

result = verify_claim(
    "MSc Computer Science, Edinburgh University\n"
    "verify:degrees.ed.ac.uk/c"
)

reg = Registry()
sealed = register_sealed_source(reg, result, domain="education")
print(sealed.grade)   # RELIABLE — integrity anchored by crypto
print(sealed.adalah)  # HIGH
print(sealed.dabt)    # UNASSESSED — precision NOT claimed
```

**Honest limit:** Live Verify proves **authenticity**, not **truth**. The seal
anchors ʿadālah (integrity) and origin strength, but leaves ḍabṭ (precision)
unassessed and leaves content to the matn critic. A verified document can still
be a genuine, domain-attested lie.

See [`src/isnad/integrations/liveverify/`](src/isnad/integrations/liveverify/) —
including a byte-compatible normalization port held against Live Verify's own
cross-platform fixtures.

---

## Controlled A/B Demonstration

[`experiments/verified_vs_unverified/`](experiments/verified_vs_unverified/) runs
six hand-authored queries with the trust layer off vs on — **2 caught, 2 missed
(honestly), 0 false positives**. The miss cases map to the two open issues (#4,
#11). Deterministic, no API keys.

## Experimental Validation — Semantic Corroboration (§8)

Corroboration (*mutābaʿāt*) validated on two corpora: **707 claim pairs, 100%
fire rate, 8/8 negative controls, zero false positives** (Wikipedia 603/603,
physics textbooks 104/104). Methodology and paper-gap analysis:
`experiments/corroboration_v2/README.md` · `experiments/PAPER_GAP_ANALYSIS.md`.

## Ecosystem

- 🌐 **Site:** https://alizahidraja.com/isnad
- 📄 **Paper (arXiv):** https://arxiv.org/abs/2607.24117
- 📄 **Paper (DOI):** https://doi.org/10.48550/arXiv.2607.24117
- 💾 **Software (DOI):** https://doi.org/10.5281/zenodo.21216873
- 📦 **PyPI:** https://pypi.org/project/isnad/
- 📝 **Companion gist:** https://gist.github.com/alizahidraja/56beaadf493976182f38aa602b8958e2
- 🧪 **§8 Experiment & results:** [`experiments/s8_gated_vs_ungated/`](experiments/s8_gated_vs_ungated/)
- 🔬 **Semantic Corroboration v2 (Wikipedia):** [`experiments/corroboration_v2/`](experiments/corroboration_v2/)
- 📚 **Corroboration v3 (Physics Textbooks):** [`experiments/corroboration_v3/`](experiments/corroboration_v3/) — 104/104 on s8 corpus
- 🗺️ **Architecture Diagram:** [`docs/ARCHITECTURE.drawio`](docs/ARCHITECTURE.drawio) — 3 tabs: System, Data Flow, Validation Matrix
- 🔌 **LangChain integration:** [`src/isnad/integrations/langchain/`](src/isnad/integrations/langchain/)
- 🔏 **Live Verify integration:** [`src/isnad/integrations/liveverify/`](src/isnad/integrations/liveverify/) — consume a `verify:` seal as a high-trust narrator
- 🔗 **Trace schema spec:** [`docs/trace-schema.md`](docs/trace-schema.md) — v0.1 with PROV/PROV-AGENT mapping
- 👁️ **Chain viewer:** [`viewer/index.html`](viewer/index.html) — open in browser, renders all 3 fixtures
- 🧪 **A/B demonstration:** [`experiments/verified_vs_unverified/`](experiments/verified_vs_unverified/) — trust layer off vs on, per-query
- 🧪 **Trace capture demo:** [`examples/isnad_langchain_demo.py`](examples/isnad_langchain_demo.py) — runnable without API keys
- 📊 **Critic evaluation:** [`src/isnad/critics/CRITIC_EVAL.md`](src/isnad/critics/CRITIC_EVAL.md)
- 🛡️ **Security policy:** [`SECURITY.md`](SECURITY.md) — how to report a vulnerability; honesty is a security property
- ⚠️ **Threat model:** [`THREAT_MODEL.md`](THREAT_MODEL.md) — what ISNAD defends against and deliberately does not
- 🕵️ **Case study (xz backdoor as a sleeper narrator):** [`docs/case-study-xz-sleeper-narrator.md`](docs/case-study-xz-sleeper-narrator.md) — by Paul Hammant (Live Verify)
- ⏳ **Period-sliced grades (the ikhtilāṭ remedy):** [`docs/period-sliced-grades.md`](docs/period-sliced-grades.md) · demo: [`examples/sleeper_narrator_demo.py`](examples/sleeper_narrator_demo.py)
- 🎯 **Adversarial benchmark:** [`experiments/adversarial_benchmark/run.py`](experiments/adversarial_benchmark/run.py) — the honest "does it actually work?" number, including the misses

---

## Open problems

- **Chain independence** ([tracking issue](https://github.com/alizahidraja/isnad/issues/54)) — the framework's hardest unsolved problem, stated publicly: topology cannot prove two chains are independent, and no amount of structural checking fully discharges the assumption.

---

## Citation

```bibtex
@article{raja2026grading,
  author  = {Ali Zahid Raja},
  title   = {Grading the Narrators: An Isnād–Rijāl Framework for
             Claim-Level Provenance in Multi-Agent Knowledge Systems},
  year    = 2026,
  doi     = {10.48550/arXiv.2607.24117},
  eprint  = {2607.24117},
  archivePrefix = {arXiv},
}

@software{raja2026isnad,
  author  = {Ali Zahid Raja},
  title   = {Isnād–Rijāl Framework: Reference Implementation},
  year    = 2026,
  doi     = {10.5281/zenodo.21216873},
  orcid   = {0009-0003-7875-4590},
}
```

---

## About

Built by [Ali Zahid Raja](https://alizahidraja.com) · ORCID [0009-0003-7875-4590](https://orcid.org/0009-0003-7875-4590)

The rigor belongs to twelve centuries of muḥaddithūn. The transfer to AI
systems is the contribution claimed here. Built in public — collaborators welcome.

**License:** Code — Apache 2.0 · Paper & docs — CC BY 4.0
