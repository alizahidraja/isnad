# Model-drift leaderboard — LIVE results (#71)

**Model:** `deepseek-flash` · **temperature:** 0.0 · **date:** 2026-09-10
**Calls:** 1120 · **tokens:** 105590 in / 135070 out · **cost:** $0.05260 (cap $2.00)
**dataset_sha256:** `d84890a07a18ba4f…`

## Aggregate (all facts)

| Depth | hallucination_rate (oracle) | served_error_rate (real critic) |
|---|---|---|
| 1 | 0.000 | 0.000 |
| 2 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 |
| 4 | 0.000 | 0.000 |
| 5 | 0.000 | 0.000 |

## By difficulty tier

### Easy facts

| Depth | hallucination_rate | served_error_rate | n |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 8 |
| 2 | 0.000 | 0.000 | 8 |
| 3 | 0.000 | 0.000 | 8 |
| 4 | 0.000 | 0.000 | 8 |
| 5 | 0.000 | 0.000 | 8 |

### Medium facts

| Depth | hallucination_rate | served_error_rate | n |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 20 |
| 2 | 0.000 | 0.000 | 20 |
| 3 | 0.000 | 0.000 | 20 |
| 4 | 0.000 | 0.000 | 20 |
| 5 | 0.000 | 0.000 | 20 |

### Hard facts

| Depth | hallucination_rate | served_error_rate | n |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 28 |
| 2 | 0.000 | 0.000 | 28 |
| 3 | 0.000 | 0.000 | 28 |
| 4 | 0.000 | 0.000 | 28 |
| 5 | 0.000 | 0.000 | 28 |

## Oracle cross-check (independent LLM audit)

agreement rate: **0.867** (26/30) — same model family as the critic under test — a sanity check, not independent ground truth.

## Honest limits

- **Self-critique:** the narrator and critic are the SAME model (`deepseek-flash`);
  a model is often lenient on its own output, so served_error_rate is optimistic.
- **Single provider / single model.** No cross-family comparison yet.
- **temperature = 0.0**: drift is deterministic knowledge error, not sampling noise.
- **Oracle definition:** any numeric deviation (rounding, unit change) counts as drift.
- **Cost** is derived from the API's token counts × the disclosed V4-Flash rate card
  ($0.14/M in, $0.28/M out); the raw token totals are the ground truth.

Reproduce: `DEEPSEEK_API_KEY=… uv run python -m experiments.model_drift.live --audit`.
