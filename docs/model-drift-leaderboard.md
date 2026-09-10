# Model-drift leaderboard (#71)

How does a claim's **hallucination rate** grow as it passes through an increasingly
**deep multi-agent chain** — and how well does ISNAD's chain-grade + content-critic +
decision-matrix pipeline **catch** that hallucination at each depth?

The methodology is **preregistered** (frozen before any result):
[`experiments/model_drift/PREREGISTRATION.md`](../experiments/model_drift/PREREGISTRATION.md).

## Current results (offline mode)

[`experiments/model_drift/results/RESULTS.md`](../experiments/model_drift/results/RESULTS.md)

| Depth | hallucination_rate (oracle) | served_error_rate (perfect critic) | served_error_rate (empty critic) |
|---|---|---|---|
| 1 | 0.167 | 0.000 | 1.000 |
| 2 | 0.417 | 0.000 | 1.000 |
| 3 | 0.583 | 0.000 | 1.000 |
| 4 | 0.667 | 0.000 | 1.000 |
| 5 | 0.750 | 0.000 | 1.000 |

**What this shows (honestly):** hallucination rate grows monotonically with depth
(0.17 → 0.75 under the preregistered 0.25/hop corruption). A **perfect** critic → the
decision matrix catches 100% (served-error 0 — this row verifies the plumbing, not
critic quality). A **useless** critic (always UNVERIFIABLE) → every hallucinated claim
is served with caveat (served-error 1.0). The real, open question — how well a *real*
critic sits between those two extremes — is the live phase.

## Reproduce

```bash
uv run python -m experiments.model_drift.run --seed 0
```

Output is deterministic (byte-identical across runs), with every row carrying exact
provenance (model/provider, temperature, seed, dataset SHA-256).

## Hard limits

- **Offline mode only.** Live multi-family numbers require paid API keys and incur cost;
  they are a separate keyed phase. Cells not actually run are rendered "not run".
- Single seed dataset (12 facts) across 6 domains; the `offline-drift` injector is a
  deterministic stand-in, not a real model.
- The metric does **not** claim general hallucination-detection superiority (#71).
