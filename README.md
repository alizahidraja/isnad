# Isnād–Rijāl Framework

**Grade the narrators, not just log them.** Claim-level provenance for multi-agent knowledge systems — adapted from classical hadith transmission science.

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

## 60-Second Quickstart

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

---

## What's Validated vs. What's Not

| Component                     | Status              | Notes                                                                 |
| ----------------------------- | ------------------- | --------------------------------------------------------------------- |
| **Bayesian grading**          | ✅ Default           | Beta-distribution replaces hardcoded thresholds; ISNAD_POLICY env override |
| **Weakest-link quarantine**   | ✅ Validated         | 100% of REJECTED narrator claims correctly blocked                    |
| **jarḥ–taʿdīl discovery**     | ✅ Partial           | Correctly identifies bad narrators; good ones need seed grades        |
| **Seed-grade bootstrapping**  | ✅ Validated         | Pre-grading sources/models improves coverage from ~5% to ~10%; critical for non-zero serving; ISNAD_SEED_CONFIG env var |
| **Corroboration (mutābaʿāt)** | ✅ Empirically validated | 603/603 (100%) on Wikipedia; 104/104 (100%) on physics textbooks; 8/8 negative controls pass; madār detection blocks correlated chains |
| **Content criticism**         | ✅ Functional        | EmbeddingCritic (TF-IDF) catches contradictions offline; HybridCritic (NLI) + LLMCritic available |
| **Semantic matching**         | ✅ Validated         | Cross-source embedding matching (MiniLM) across Wikipedia and physics corpora |
| **LangChain integration**     | ✅ Ready             | IsnadTracer callback handler, seed_registry helper, 9 integration tests pass |
| **Confidence-gating**         | ❌ Useless           | Self-confidence scores uncorrelated with defects                      |
| **Evidence provenance**       | ✅ Implemented       | `evidence_provenance()` reports whether a grade is prior-derived (benchmark) or observation-backed (audit/corroboration) — issue #6 |

### Evidence provenance — assumption vs. observation (issue #6)

A narrator's grade can come from a **population prior** (a benchmark seed or
an eval harness: "this model class is ~85% accurate") or from **observed
in-pipeline instances** (a post-hoc audit, or independent-chain corroboration:
"we watched THIS transmitter's claims survive or fail").  Classical rijāl
graded on observed instances, never priors.

```python
reg = Registry()
reg.record_evidence("model:gpt-4o", "physics", EvidenceType.BOOTSTRAP_SEED, EvidenceAction.TADIL)
s = reg.evidence_provenance("model:gpt-4o", "physics")
s.prior_only          # True — an unvalidated assumption
s.observation_backed  # False — no observed instance yet
```

`prior_only == True` is the state issue #6 flags as dangerous: however
confident the prior looks, it is not evidence about this transmission.  The
framework does not change how it grades — it makes the *assumption vs.
observation* distinction visible.

The honesty box is a feature. We tell you exactly what works, what's limited,
and where you need to supply your own components.

### Endpoint identity (model version drift)

For **model narrators**, grades are keyed by **`alias@version`** when a chain link
supplies a resolved version (e.g. `ingest-model-v3@2.0`). Deploying a new model
behind the same service name creates a **new registry identity** — track record
does **not** carry forward. That reset is intentional (paper §4.2).

- Register with `model_version` via the API or `Registry.register_versioned()`
- Pass `version` on each chain link (or use `@version` in seed keys for LangChain)
- Legacy alias-only registrations still work when `version` is omitted, `unknown`, or a non-resolved tag (`latest`, `dev`, `canary`)

Demo: `uv run python examples/endpoint_identity_drift_demo.py`

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
from isnad.critics import EmbeddingCritic, LLMCritic

critic = EmbeddingCritic()                            # offline, fast
critic = LLMCritic(api_key="sk-...")                  # LLM-backed, higher quality
```

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

**Question:** does the trust layer change the output trajectory on identical
queries — visibly, per-query, not just in aggregate?

[`experiments/verified_vs_unverified/`](experiments/verified_vs_unverified/) runs six
hand-authored queries through an identical pipeline with the trust layer **off**
then **on**, and reports what each produced:

| Outcome | Scenarios |
|---------|-----------|
| **Caught** | weak-narrator corruption, ʿilal contradiction |
| **Missed (honestly)** | stale-grade drift (#4), fabricated-clean chain (#11) |
| **Recovered** | DAIF chain upgraded by corroboration |

**2 caught, 2 missed, 0 false positives** — deterministic, no LLM or API keys.
The miss cases are the point: they map to the two open issues the framework
hasn't yet solved, shown as prominently as the successes.

```bash
python experiments/verified_vs_unverified/run.py
```

---

## Experimental Validation — Semantic Corroboration (§8)

**Status: Empirically validated on real data.**

The framework's most distinctive contribution — independent-chain corroboration
(*mutābaʿāt*) — has been validated on **two corpora of increasing difficulty:**

| Corpus | Sources | Matches | Fire Rate | Difficulty |
|---|---|---|---|---|
| **Wikipedia** (v2) | Regular + Simple English (30 topics) | 603 | 100% | Easy — natural paraphrasing |
| **Physics Textbooks** (v3) | OpenStax Vol.1 + Crowell (2 books) | 104 | 100% | Hard — formal prose, fewer overlaps |

**Combined: 603 + 104 = 707 claim pairs tested across both corpora. 100% corroboration fire rate. 8/8 negative controls. Zero false positives. Source URLs for every claim.**

### Key Findings

1. **Corroboration fires on semantically-matched cross-source data** — different text,
   same meaning, genuinely independent sources
2. **Independence detector correctly identifies madār** — chains with shared model families
   or upstream sources are blocked from upgrade
3. **HASAN cap enforced** — corroboration never falsely reaches SAHIH
4. **Information-theoretic weights calibrated** — effective weight scales with chain quality
   (1.5 for single HASAN corroborator, 2.5+ for multiple)

### Reproduce

```bash
cd experiments/corroboration_v2
pip install isnad sentence-transformers scikit-learn requests
python run.py               # Fetch Wikipedia + semantic match + corroborate
python negative_controls.py  # Verify all 8 gates
python analyze.py            # Statistical analysis
```

Full methodology, results, negative controls, and paper gap analysis in:
- [`experiments/corroboration_v2/README.md`](experiments/corroboration_v2/README.md)
- [`experiments/PAPER_GAP_ANALYSIS.md`](experiments/PAPER_GAP_ANALYSIS.md)

---

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
