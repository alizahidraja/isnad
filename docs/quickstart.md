# Quickstart — add ISNAD to your LangChain agent in 5 minutes

ISNAD traces *who* transformed a claim and grades *how much* to trust the chain —
the provenance layer your agent is missing. Five minutes, three steps.

## What does ISNAD give my agent?

A tamper-evident transmission chain for every claim your agent produces: each hop is
recorded with an input/output hash, each narrator is graded for reliability, and the
whole chain resolves to one action — serve, caveat, review, or quarantine.

## Step 1 — Install

```bash
pip install "isnad[langchain]"        # Python ≥ 3.11, Apache-2.0
```

## Step 2 — Trace a chain with the tracer

Warm-start the narrator registry (rijāl), then attach the tracer to your existing
chain. It records the transmission chain (isnād) from LangChain's run tree.

```python
from isnad.integrations.langchain import IsnadTracer, seed_registry

# rijāl: narrator_id -> reliability grade (reliable / acceptable / weak / rejected)
reg = seed_registry({
    "source:my-docs":           "reliable",
    "model:gpt-4o@2024-08-06":  "acceptable",
    "model:gpt-4o-mini":        "weak",
}, domain="medical-qa")

tracer = IsnadTracer(registry=reg)
#   chain.invoke(input, config={"callbacks": [tracer]})   # your existing agent
print(tracer.report())            # the transmission chain with per-link grades
```

## Step 3 — Grade the chain and decide

```python
from isnad.core.chain import Chain, ChainLinkSpec, grades_for_chain, normalize_claim_text
from isnad.core.grading import grade_chain
from isnad.core.decision import decide
from isnad.matn import DeterministicRuleCritic
from isnad.types import TransformType

claim = "the recommended dosage is 5 mg daily"

chain = Chain([
    ChainLinkSpec("source:my-docs",           step=0, domain="medical-qa", transform_type=TransformType.PASS_THROUGH),
    ChainLinkSpec("model:gpt-4o@2024-08-06", step=1, domain="medical-qa", transform_type=TransformType.GENERATIVE),
    ChainLinkSpec("model:gpt-4o-mini",        step=2, domain="medical-qa", transform_type=TransformType.DESTRUCTIVE),
])

link_grades = grades_for_chain(reg, chain)
chain_grade = grade_chain(link_grades, [l.transform_type for l in chain.links], is_complete=chain.is_complete)
# weakest-link rule: the weak summarizer caps the chain

critic = DeterministicRuleCritic()   # swap in an LLM/embedding critic for real text
verdict = critic.evaluate(claim, normalize_claim_text(claim), ["the recommended dosage is 10 mg daily"])
action = decide(chain_grade, verdict)   # SERVE / SERVE_WITH_CAVEAT / REVIEW / QUARANTINE
```

## What did I just build?

A graded, hash-chained provenance record — **who** vouches for the claim and **how
much** the weakest narrator lets you trust it. It grades the transmission, never the
truth; your content critic owns the truth question, and ISNAD composes with it.

## What are the honest limits?

The bundled deterministic critic is a reference stub on real text — plug in an LLM or
embedding critic via `CriticAdapter` for practical coverage. Cold-start grades produce
near-zero coverage, so seed your known-reliable narrators first. Both limits are
stated up front, not hidden.

## Where next?

- [How isnād–rijāl maps to multi-agent provenance](concepts.md) — the idea.
- [Compliance mapping](compliance.md) — turn the audit trail into an audit you pass.
