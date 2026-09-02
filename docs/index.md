# ISNAD

**Grades the transmitters and the chain, not just the claim.**

Open-source **LLM provenance**, **agent trust**, and an **AI audit trail** for RAG and
multi-agent systems. Apache-2.0, permanently. `pip install isnad`.

Every claim your pipeline produces carries a verifiable **weakest-link trust grade** and
a **tamper-evident audit record** — so you can answer the question that hallucination
detectors and observability tools skip: *who handled this claim, in what order, and how
much do we trust each one?*

```python
from isnad import Registry, grade
from isnad.types import NarratorGrade

reg = Registry()
reg.register("openstax", "physics", grade=NarratorGrade.RELIABLE)
reg.register("pdf-scraper", "physics", grade=NarratorGrade.UNGRADED)
reg.register("ingest-model", "physics", grade=NarratorGrade.ACCEPTABLE)

verdict = grade("p = mv", ["openstax", "pdf-scraper", "ingest-model"], reg, domain="physics")
print(verdict.why)
# claim 'p = mv' -> chain DAIF (weakest: pdf-scraper, ungraded)
```

> **Proof it works:** ISNAD's weakest-link rule reproduces **1,200 years of scholar
> chain verdicts at Cohen's κ = 0.87** across 575,060 graded hadith chains. (For context:
> scholars disagree with *each other* on narrator grades at κ = 0.33 — a different task.)

## Why ISNAD

Most AI trust tooling records *what* happened. ISNAD grades *who* transformed the claim
and *how much to trust the chain that carried it* — then exports the whole judgment as a
tamper-evident record for governance review.

| Capability | ISNAD | LangSmith (observability) | RAGAS (eval) | OpenLineage (lineage) |
| --- | --- | --- | --- | --- |
| Grades the **chain** (who handled the claim) | ✅ | ❌ | ❌ | ⚠️ |
| Grades the **transmitters** (living rijāl registry) | ✅ | ❌ | ❌ | ❌ |
| Tamper-evident audit record (SHA-256 / Merkle / signatures) | ✅ | ⚠️ | ❌ | ❌ |
| Evidence artifacts, not conformity | ✅ | ❌ | ❌ | ❌ |
| Refuses numeric confidence (no over-claiming) | ✅ | ⚠️ | ❌ | ✅ |
| Reproducible benchmark (κ = 0.87 on 575k chains) | ✅ | ❌ | ❌ | ❌ |
| Self-hostable / offline | ✅ | ✅ | ✅ | ✅ |

✅ yes · ⚠️ partial · ❌ no

## The honesty contract

ISNAD does **not** emit numeric confidence. It emits an **ordinal grade** (reliable →
acceptable → weak → rejected → ungraded) plus the **evidence** that produced it. Priors are
labeled *Estimated*; observations are labeled *Supported*; a grade with no evidence is
labeled *unvalidated* — never silently promoted. This is the moat: **evidence artifacts,
not conformity.**

## Start here

* [Getting Started](getting-started.md) — install and grade your first chain
* [Provenance](provenance.md) — the audit contract
* [CLI Reference](cli-reference.md) — every command
* [Architecture](ARCHITECTURE.md) — how it's built

## Links

[:fontawesome-brands-github: GitHub](https://github.com/alizahidraja/isnad) ·
[:fontawesome-solid-book: Paper](https://arxiv.org/abs/2607.24117) ·
[:fontawesome-solid-box: PyPI](https://pypi.org/project/isnad/) ·
[:fontawesome-brands-npm: npm verifier](https://www.npmjs.com/package/isnad)
