# ISNAD

ISNAD grades who handled a claim in an AI pipeline (the transmitters and the chain) and can export each verdict as an audit record you can sign and verify.

## Install

```bash
pip install isnad
```

## 30-second example

```python
from isnad import Registry, grade
from isnad.types import NarratorGrade

reg = Registry()
reg.register("openstax", "physics", grade=NarratorGrade.RELIABLE)
reg.register("pdf-scraper", "physics", grade=NarratorGrade.UNGRADED)
reg.register("ingest-model", "physics", grade=NarratorGrade.ACCEPTABLE)

verdict = grade("p = mv", ["openstax", "pdf-scraper", "ingest-model"], reg, domain="physics")
print(verdict.why)
# claim 'p = mv' → chain DAIF (weakest: pdf-scraper, ungraded)
```

A new pipeline starts with every narrator UNGRADED, so nothing serves; seed grades with `Registry.seed()`.

## Read next

- [Quickstart](quickstart.md) — add ISNAD to a LangChain agent in five minutes.
- [Concepts](concepts.md) — the isnād–rijāl model.
- [Compliance](compliance.md) — the evidence ISNAD produces for AI governance frameworks.
- [Architecture](ARCHITECTURE.md) — the module map.
- [Critics](critics.md) — content critics and their measured recall.
- [ISNAD-Bench results](https://github.com/alizahidraja/isnad/blob/v3.2.0/bench/docs/RESULTS.md)
