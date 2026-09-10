# Model-drift leaderboard — committed results (#71)

**Generated:** 2026-09-10 · **seed:** 0 · **corruption_probability:** 0.25 · **dataset_sha256:** `6a79fe02c63e6dff…`

The **hallucination rate** (ground-truth oracle) grows with chain depth. The
**served-error rate** is how often the pipeline still SERVEs a hallucinated claim.

| Depth | hallucination_rate | served_error_rate (perfect critic) | served_error_rate (empty critic) |
|---|---|---|---|
| 1 | 0.167 | 0.000 | 1.000 |
| 2 | 0.417 | 0.000 | 1.000 |
| 3 | 0.583 | 0.000 | 1.000 |
| 4 | 0.667 | 0.000 | 1.000 |
| 5 | 0.750 | 0.000 | 1.000 |

## Reading the numbers

- **hallucination_rate** is the ground truth (oracle), independent of the critic.
- **served_error_rate (perfect critic)** is the pipeline's ceiling: the decision
  matrix catches 100% by construction — this row verifies the harness plumbing,
  not critic quality.
- **served_error_rate (empty critic)** is the negative control: a useless critic
  (always UNVERIFIABLE) serves every hallucinated claim with caveat.
- **No-gating baseline:** 1.0 (serve-everything serves every hallucinated claim by construction).

## Honest limits

- **Offline mode only.** Live multi-family numbers require paid API keys and incur
  cost; they are a separate keyed phase. Cells that were not actually run are
  rendered "not run", never fabricated.
- Single seed dataset (12 facts). The `offline-drift` injector is a deterministic
  stand-in for a real model, preregistered at corruption_probability = 0.25.
- The metric does **not** claim general hallucination-detection superiority.

Reproduce: `uv run python -m experiments.model_drift.run --seed 0`.
