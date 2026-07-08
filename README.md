# Isnād–Rijāl Framework

**Grade the narrators, not just log them.** Claim-level provenance for multi-agent knowledge systems — adapted from classical hadith transmission science.

[![CI](https://github.com/alizahidraja/isnad/actions/workflows/ci.yml/badge.svg)](https://github.com/alizahidraja/isnad/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![DOI: 10.5281/zenodo.21211290](https://zenodo.org/badge/DOI/10.5281/zenodo.21211290.svg)](https://doi.org/10.5281/zenodo.21211290)

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

# Seed-grade known narrators (required for coverage — see §8 experiment)
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
from isnad.integrations.langchain import IsnadTracer, seed_registry
from isnad.critics import EmbeddingCritic

reg = seed_registry({"source:docs": "reliable", "model:gpt-4o": "acceptable"})
tracer = IsnadTracer(registry=reg, critic=EmbeddingCritic())
chain.invoke("What is F=ma?", config={"callbacks": [tracer]})
print(tracer.report())
```

---

## What's Validated vs. What's Not

| Component                     | Status              | Notes                                                                 |
| ----------------------------- | ------------------- | --------------------------------------------------------------------- |
| **Bayesian grading**          | ✅ Default           | Beta-distribution replaces hardcoded thresholds; ISNAD_POLICY env override |
| **Weakest-link quarantine**   | ✅ Validated         | 100% of REJECTED narrator claims correctly blocked                    |
| **jarḥ–taʿdīl discovery**     | ✅ Partial           | Correctly identifies bad narrators; good ones need seed grades        |
| **Seed-grade bootstrapping**  | ✅ Validated         | Pre-grading sources/models enables practical coverage; ISNAD_SEED_CONFIG env var |
| **Corroboration (mutābaʿāt)** | ✅ Wired + tested    | Fires on 2+ independent chains; madār detection blocks correlated chains |
| **Content criticism**         | ✅ Functional        | EmbeddingCritic (TF-IDF) catches contradictions offline; HybridCritic (NLI) + LLMCritic available |
| **Confidence-gating**         | ❌ Useless           | Self-confidence scores uncorrelated with defects                      |
| **Coverage (with critic)**    | ~50%                 | Up from ~10% with the stub; 36% consistent, 4% contradiction on corpus |

The honesty box is a feature. We tell you exactly what works, what's limited,
and where you need to supply your own components.

---

## Concept → Module Map

| Concept                       | What it does                                         | Module                     |
| ----------------------------- | ---------------------------------------------------- | -------------------------- |
| **isnād** (chain)             | Ordered, gap-checked transmission chain per claim    | `isnad/core/chain.py`      |
| **rijāl** (registry)          | Graded narrator store per (narrator, domain)         | `isnad/core/registry.py`   |
| **jarḥ–taʿdīl**               | Evidence-driven state machine for narrator grades    | `isnad/core/registry.py`   |
| **Bayesian grading**          | Beta-distribution narrator grades (default)          | `isnad/core/registry.py`   |
| **ittiṣāl**                   | Completeness as epistemic property (gap → DAIF)      | `isnad/core/chain.py`      |
| **Weakest-link grading**      | Chain grade = refined minimum over narrators         | `isnad/core/grading.py`    |
| **mutābaʿāt** (corroboration) | Independent-chain upgrade + madār detection          | `isnad/core/corroboration.py` |
| **matn criticism**            | Content evaluated independently of chain quality     | `isnad/critics/`           |
| **Decision matrix**           | 4×2 (chain × content) → action router                | `isnad/core/decision.py`   |
| **Persistence**               | SQLAlchemy-backed registry (swap via protocol)       | `isnad/storage/`           |
| **API**                       | FastAPI service with DI + Prometheus metrics         | `isnad/api/`               |
| **CLI**                       | `isnad serve` | `isnad seed`                        | `isnad/cli/`               |
| **ʿadālah / ḍabṭ**            | Integrity and precision as two distinct axes         | `isnad/types.py`           |

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
- Corroboration on a warm-grade corpus (the §8 experiment showed it's gated on warm grades)

---

## Ecosystem

- 🌐 **Site:** https://alizahidraja.com/isnad
- 📄 **Paper (DOI):** https://doi.org/10.5281/zenodo.21211290
- 💾 **Software (DOI):** https://doi.org/10.5281/zenodo.21216873
- 📦 **PyPI:** https://pypi.org/project/isnad/
- 📝 **Companion gist:** https://gist.github.com/alizahidraja/56beaadf493976182f38aa602b8958e2
- 🧪 **§8 Experiment & results:** [`experiments/s8_gated_vs_ungated/`](experiments/s8_gated_vs_ungated/)
- 🔌 **LangChain integration:** [`src/isnad/integrations/langchain/`](src/isnad/integrations/langchain/)
- 📊 **Critic evaluation:** [`src/isnad/critics/CRITIC_EVAL.md`](src/isnad/critics/CRITIC_EVAL.md)

---

## Citation

```bibtex
@article{raja2026grading,
  author  = {Ali Zahid Raja},
  title   = {Grading the Narrators: An Isnād–Rijāl Framework for
             Claim-Level Provenance in Multi-Agent Knowledge Systems},
  year    = 2026,
  doi     = {10.5281/zenodo.21211290},
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
