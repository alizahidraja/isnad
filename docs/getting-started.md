# Getting Started

Install ISNAD and grade your first chain in under a minute.

## Install

```bash
pip install isnad
```

Requires **Python 3.12+**. Optional extras: `pip install isnad[langchain]` (LangChain
tracing) and `isnad[mcp]` (MCP server).

## 30 seconds to a verdict

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

The chain is capped by its **weakest link** — the ungraded scraper drags the whole
claim to DAIF, regardless of how reliable the other narrators are.

## Warm-start a registry

A fresh pipeline has no observations, so every narrator starts `UNGRADED` and every
claim routes to `REVIEW`. Seed the shipped evidence-sourced defaults to start warm
(these are *Estimated* priors, never *Supported* observations):

```python
from isnad import default_registry

reg = default_registry()          # ~39 evidence-sourced "Estimated" priors
entries = default_seed_entries()  # the same seeds, as data
```

Grades stay operator-local: override or ignore any shipped entry.

## Serve it over HTTP

```bash
isnad serve
```

Then `POST /v1/claims` to submit a claim + its chain, and read the graded surface at
`GET /v1/claims`. See [Onboard in a Day](onboard-in-a-day.md) for copy-paste recipes.

## Next steps

* [Provenance](provenance.md) — the audit contract
* [CLI Reference](cli-reference.md) — every command
* [Architecture](ARCHITECTURE.md) — how it's built
