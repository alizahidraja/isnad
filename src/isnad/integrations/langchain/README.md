# ISNAD × LangChain Integration

**Honest, early-stage.** Attach claim-level provenance to your LangChain/LangGraph
agent pipelines. The weakest-link quarantine works. The content critic needs your
help. Corroboration is untested.

## Install

```bash
pip install isnad[langchain]
```

## 5-Line Quickstart

```python
from isnad.integrations.langchain import IsnadTracer, seed_registry

reg = seed_registry({"source:my-docs": "reliable", "model:gpt-4o": "acceptable"})
tracer = IsnadTracer(registry=reg)
chain.invoke("What is F=ma?", config={"callbacks": [tracer]})
print(tracer.report())
```

## What You Get

- **Automatic chain capture:** Every LLM call, tool use, and retrieval step
  becomes an ISNAD narrator link with transform type and trace id.
- **Weakest-link grading:** One weak narrator caps the whole chain.
- **Quarantine:** REJECTED narrators block their claims automatically.
- **Review routing:** Claims with uncertain content or mid-tier narrators
  are routed for human review (or held until a critic clears them).

## ⚠ You Must Supply Two Things for Practical Coverage

### 1. A Content Critic

The bundled deterministic critic is a **non-functional reference stub** on real text.
It returns UNVERIFIABLE for everything that isn't an exact duplicate. Without a real
critic, all HASAN-tier claims are held for REVIEW instead of auto-served. Coverage
collapses to ~10% (the review budget).

**Fix:** Supply an LLM-backed or embedding-based critic:

```python
from isnad.integrations.langchain import CriticAdapter

# Option A: Wrap a callable
def my_critic(claim, corpus, domain):
    # Your logic — LLM call, embedding similarity, rule-based
    return ContentVerdict.CONSISTENT

critic = CriticAdapter(my_critic)
tracer = IsnadTracer(registry=reg, critic=critic)

# Option B: Use the reference LLM-backed critic
critic = CriticAdapter.llm_backed(api_key="sk-...")
tracer = IsnadTracer(registry=reg, critic=critic)
```

### 2. Warm-Start Grades

Without seed grades, the jarḥ–taʿdīl loop starts from UNGRADED and nearly all
claims are quarantined. Seed-grade your known-reliable narrators:

```python
reg = seed_registry({
    "source:my-docs": "reliable",      # trusted source
    "retriever:vector-db": "acceptable", # known-good retriever
    "model:gpt-4o": "acceptable",       # model you trust
    "model:untrusted": "weak",           # model you're testing
})
```

## Current Limitations (Read Before Using)

| Limitation | Status |
|---|---|
| **Content critic** | Default stub is non-functional on real text. Supply your own. |
| **Corroboration** | Experimentally UNTESTED on real corpora. Never successfully fired. |
| **Cold-start** | Coverage ≈ 0% without seed grades. Seed-grade your narrators. |
| **Error floor** | ACCEPTABLE narrators' fault rate leaks through. |
| **Single-domain** | Tested on physics only. External validity unknown. |

**Full §8 experiment results and limitations:**
[`experiments/s8_gated_vs_ungated/results/RESULTS.md`](../../../experiments/s8_gated_vs_ungated/results/RESULTS.md)

## API Reference

### `IsnadTracer(registry, critic=None, domain="general")`
LangChain `BaseCallbackHandler`. Attach to any chain run. Collects ISNAD chains
and produces a report.

### `isnad_track(registry, narrator_id, domain, transform_type)`
Decorator for simple functions. Records provenance without LangChain.

### `seed_registry(narrator_grades, domain="general")`
Build a warm-started Registry from a dict. Required for practical coverage.

### `CriticAdapter(evaluator)`
Wrap any callable as a ContentCritic. `CriticAdapter.llm_backed(api_key)` provides
a reference Anthropic-backed implementation.
