# Isnād–Rijāl Framework

**Grade the narrators, not just log them.** Claim-level provenance for multi-agent knowledge systems.

[![CI](https://github.com/alizahidraja/isnad/actions/workflows/ci.yml/badge.svg)](https://github.com/alizahidraja/isnad/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![DOI: 10.5281/zenodo.21211291](https://zenodo.org/badge/DOI/10.5281/zenodo.21211291.svg)](https://doi.org/10.5281/zenodo.21211291)

---

## 60-second quickstart

```python
from isnad import Registry, Chain, ChainLinkSpec, grade_chain, decide
from isnad.types import NarratorGrade, TransformType, ContentVerdict
from isnad.matn import DeterministicRuleCritic

# Build a transmission chain: source → scraper → model
chain = Chain([
    ChainLinkSpec("openstax-v3", 0, domain="physics"),
    ChainLinkSpec("pdf-scraper", 1, transform_type=TransformType.DESTRUCTIVE),
    ChainLinkSpec("ingest-model", 2, transform_type=TransformType.GENERATIVE),
])

# Two narrators are ungraded → HASAN tier
reg = Registry()
reg.register("openstax-v3", "physics", grade=NarratorGrade.RELIABLE)
reg.register("pdf-scraper", "physics", grade=NarratorGrade.UNGRADED)
reg.register("ingest-model", "physics", grade=NarratorGrade.UNGRADED)

# Grade the chain
grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
transforms = [l.transform_type for l in chain.links]
cg = grade_chain(grades, transforms, is_complete=True)

# Content criticism (fully decoupled from chain grading)
cv = DeterministicRuleCritic().evaluate("p = h/λ", "p = h/lambda", ["p = mv"])

# Decision matrix: HASAN × CONTRADICTION → REVIEW
action = decide(cg, cv)
print(f"Chain: {cg.value.upper()} | Content: {cv.value} | Action: {action.value}")
# Output: Chain: HASAN | Content: CONTRADICTION | Action: review
```

📄 **Paper:** ["Grading the Narrators"](https://doi.org/10.5281/zenodo.21211291) — Ali Zahid Raja (2026)  
📋 **Companion gist:** [Schema & design notes](https://gist.github.com/alizahidraja/56beaadf493976182f38aa602b8958e2)

---

## Install

```bash
git clone https://github.com/alizahidraja/isnad.git && cd isnad
make install    # uv sync
make test       # 90 tests, zero config, SQLite fallback
make demo       # Paper's worked example (§4.5)
make check      # lint + type-check + test
```

No database required for pure-logic tests. PostgreSQL is optional (`docker compose up`, set `ISNAD_DATABASE_URL`).

---

## What problem does this solve?

In modern AI pipelines, a factual claim passes through many hands — a scraper extracts it, a model compiles it, another serves it — and each hand can drop, distort, or invent. Existing provenance tools record *what* happened. They don't grade *who* transformed the claim, so they can't tell you how much to trust the result.

This framework adapts classical Islamic hadith transmission science — one of history's most rigorous pre-modern epistemologies — into a Python library for AI systems. The core insight: **the trustworthiness of a claim is a function of the graded reliability of every individual who transmitted it**. Claims carry complete chains (isnād); transmitters are graded in a living registry (rijāl); chains are graded by their weakest link; independent corroboration can upgrade; and content is criticized independently of transmission quality.

---

## Concept → module mapping

| Concept | What it does | Module |
|---|---|---|
| **isnād** (chain) | Ordered, gap-checked transmission chain per claim | `isnad/chain.py` |
| **rijāl** (registry) | Graded narrator store per (narrator, domain) | `isnad/registry.py` |
| **jarḥ–taʿdīl** | Evidence-driven state machine for narrator grades | `isnad/registry.py` |
| **ittiṣāl/munqaṭiʿ** | Completeness as epistemic property (gap → DAIF) | `isnad/chain.py` |
| **Weakest-link grading** | Chain grade = refined minimum over narrators | `isnad/grading.py` |
| **mutābaʿāt** | Independent-chain corroboration with correlation detection | `isnad/corroboration.py` |
| **matn criticism** | Content evaluated independently of chain quality | `isnad/matn.py` |
| **Decision matrix** | 4×2 (chain × content) → action router | `isnad/matrix.py` |
| **ʿadālah / ḍabṭ** | Integrity and precision as two distinct axes | `isnad/types.py` |

---

## Pluggable strategies

The paper deliberately leaves certain transition arithmetic open (§4.2/§4.3). These are exposed as swappable interfaces:

| Strategy | Protocol | Default | What it decides |
|---|---|---|---|
| `GradingStrategy` | `isnad/types.py` | `RefinedWeakestLink` | How link grades combine into a chain grade |
| `TransitionPolicy` | `isnad/types.py` | `ThresholdTransitionPolicy` | How evidence moves narrators between ordinal states |
| `CorroborationPolicy` | `isnad/types.py` | `CappedCorroborationPolicy` | How independent chains upgrade a claim |
| `CorrelationDetector` | `isnad/types.py` | `SharedLineageDetector` | Whether two chains are truly independent |
| `ContentCritic` | `isnad/types.py` | `DeterministicRuleCritic` | Content contradiction detection |

**Swap one in one line:**

```python
from isnad import grade_chain, RefinedWeakestLink

class MyStrategy:
    def compute_chain_grade(self, grades, transforms, is_complete, *, corroboration_support=False):
        # Your logic here
        ...

result = grade_chain(grades, transforms, is_complete=True, strategy=MyStrategy())
```

---

## Status — what this does and does not validate

**This implements:** the framework's architecture, grading logic, and all pluggable strategy interfaces. It passes 90+ tests enforcing every epistemic commitment from the paper, including the paper's worked example (§4.5) as an end-to-end integration test.

**This does NOT constitute:** the end-to-end empirical validation (gated-vs-ungated served-error study) that the paper scopes as future work (§8). The registry bootstrapping, transition-policy thresholds, and corroboration arithmetic are reference defaults — not empirically calibrated values. Deployers should run the §8 experiment against their own pipelines.

**Reference stubs** are docstring-labeled:
- `DeterministicRuleCritic` — hardcoded pattern matching; production needs semantic/LLM critic.
- `LLMCritic` — reference Anthropic integration; needs batching, caching, ensemble for production.
- `SharedLineageDetector` — exact-match heuristics; production needs structured model lineage data.
- Seed-grade bootstrapping — designed but not yet implemented (see §7 of paper).

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Especially welcome:

1. **New `CorrelationDetector`** using embedding similarity or model-card lineage data.
2. **Seed-grade bootstrapper** that initializes narrator grades from published benchmark accuracies.
3. **Domain-specific `ContentCritic`** with formula canonicalization (physics, medicine, law).
4. **Calibrated `TransitionPolicy`** from your own pipeline's §8 experiment data.
5. **Pipeline adapters** for LangChain, CrewAI, or Autogen tracing.

---

## Citation

If you use this software, cite the paper:

```bibtex
@software{raja2026isnad,
  author       = {Ali Zahid Raja},
  title        = {Isnād–Rijāl Framework: Claim-Level Provenance in Multi-Agent Knowledge Systems},
  year         = 2026,
  doi          = {10.5281/zenodo.21211291},
  url          = {https://doi.org/10.5281/zenodo.21211291},
  orcid        = {0009-0003-7875-4590},
}
```

> A dedicated software DOI will be added after the first Zenodo release.  
> GitHub's "Cite this repository" button is powered by [`CITATION.cff`](CITATION.cff).

---

## License

Code: [Apache 2.0](LICENSE) · Paper & docs: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
