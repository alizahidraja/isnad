# Model-drift leaderboard (#71)

How does a claim's **hallucination rate** grow as it passes through an increasingly
**deep multi-agent chain** (depth 1..5) — and how well does ISNAD's chain-grade +
content-critic + decision-matrix pipeline **catch** that hallucination at each depth?

The methodology is **preregistered** (frozen before any result):
[`experiments/model_drift/PREREGISTRATION.md`](../experiments/model_drift/PREREGISTRATION.md).

## Live results — DeepSeek V4 Flash (`deepseek-flash`)

[`experiments/model_drift/results/LIVE_RESULTS.md`](../experiments/model_drift/results/LIVE_RESULTS.md)
· raw: [`results/live_results.json`](../experiments/model_drift/results/live_results.json)

| Depth | hallucination_rate (oracle) | served_error_rate (real critic) |
|---|---|---|
| 1 | **0.000** | 0.000 |
| 2 | **0.000** | 0.000 |
| 3 | **0.000** | 0.000 |
| 4 | **0.000** | 0.000 |
| 5 | **0.000** | 0.000 |

- **56 facts** (8 easy / 20 medium / 28 hard), temperature 0.0, 1,120 calls, **$0.053** total.
- **Oracle cross-check (independent LLM audit):** 0.87 agreement (26/30). The 4
  disagreements are the auditor answering "unverifiable" on a correct claim — not
  hallucinations.
- Ground-truth labels come from an **LLM-free numeric oracle** (never an LLM), so the
  labels themselves cannot hallucinate.

**What this honestly shows:** a frontier model relays all 56 well-known facts correctly
through 5 hops — it does **not** drift on *training-data facts*. Hallucination of the
kind #71 wants to measure does **not** emerge from well-known facts; it requires
**post-training-cutoff or obscure** facts (where the model has no correct prior to
reproduce). That is the next corpus iteration.

## Offline results (pipeline plumbing, deterministic)

[`experiments/model_drift/results/RESULTS.md`](../experiments/model_drift/results/RESULTS.md)

| Depth | hallucination_rate (oracle) | served_error_rate (perfect critic) | served_error_rate (empty critic) |
|---|---|---|---|
| 1 | 0.167 | 0.000 | 1.000 |
| 2 | 0.417 | 0.000 | 1.000 |
| 3 | 0.583 | 0.000 | 1.000 |
| 4 | 0.667 | 0.000 | 1.000 |
| 5 | 0.750 | 0.000 | 1.000 |

A **perfect** critic → the decision matrix catches 100% (verifies the plumbing). A
**useless** critic → serves every hallucinated claim. The real critic sits between the
two — the live phase measures where.

## Reproduce

```bash
# offline (no keys): deterministic drift-injector stand-in
uv run python -m experiments.model_drift.run --seed 0

# live (DeepSeek): key from env, $2 hard cap, optional --audit
DEEPSEEK_API_KEY=… uv run python -m experiments.model_drift.live --audit
```

## Hard limits (stated, not hidden)

- **Live is single-model self-critique**: narrator and critic are both `deepseek-flash`,
  so served_error_rate is optimistic (models are lenient on their own output).
- **Well-known-fact corpus** → 0 drift on a frontier model. Inducing real hallucination
  requires post-cutoff/obscure facts (next iteration).
- **Oracle definition**: any numeric deviation (rounding, unit change, more precision)
  counts as drift — but only *at the canonical value's precision*; a more-precise
  correct answer (763.035 vs 763) is faithful.
- **Cost** is derived from the API's token counts × the disclosed V4-Flash rate card
  ($0.14/M in, $0.28/M out); raw token totals are the ground truth.
- The metric does **not** claim general hallucination-detection superiority (#71).
