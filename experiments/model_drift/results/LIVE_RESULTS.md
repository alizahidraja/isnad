# Model-drift leaderboard — LIVE results (#71)

**Model:** `deepseek-flash` · **temperature:** 0.0 · **date:** 2026-09-11
**Calls:** 1300 · **tokens:** 123192 in / 291860 out · **cost:** $0.09897 (cap $2.00)
**dataset_sha256:** `53e319c33cb0e599…`

## Aggregate (all facts)

| Depth | hallucination_rate (oracle) | served_error_rate (real critic) |
|---|---|---|
| 1 | 0.061 | 0.000 |
| 2 | 0.061 | 0.000 |
| 3 | 0.077 | 0.400 |
| 4 | 0.077 | 0.400 |
| 5 | 0.061 | 0.000 |

## By difficulty tier

### Easy facts

| Depth | hallucination_rate | served_error_rate | n |
|---|---|---|---|
| 1 | 0.000 | n/a | 8 |
| 2 | 0.000 | n/a | 8 |
| 3 | 0.000 | n/a | 8 |
| 4 | 0.000 | n/a | 8 |
| 5 | 0.000 | n/a | 8 |

### Medium facts

| Depth | hallucination_rate | served_error_rate | n |
|---|---|---|---|
| 1 | 0.000 | n/a | 20 |
| 2 | 0.000 | n/a | 20 |
| 3 | 0.000 | n/a | 20 |
| 4 | 0.000 | n/a | 20 |
| 5 | 0.000 | n/a | 20 |

### Hard facts

| Depth | hallucination_rate | served_error_rate | n |
|---|---|---|---|
| 1 | 0.000 | n/a | 28 |
| 2 | 0.000 | n/a | 28 |
| 3 | 0.000 | n/a | 28 |
| 4 | 0.000 | n/a | 28 |
| 5 | 0.000 | n/a | 28 |

### Postcutoff facts

| Depth | hallucination_rate | served_error_rate | n |
|---|---|---|---|
| 1 | 0.444 | 0.000 | 9 |
| 2 | 0.444 | 0.000 | 9 |
| 3 | 0.556 | 0.400 | 9 |
| 4 | 0.556 | 0.400 | 9 |
| 5 | 0.444 | 0.000 | 9 |

## Oracle cross-check (independent LLM audit)

agreement rate: **0.900** (27/30) — same model family as the critic under test — a sanity check, not independent ground truth.

## Honest limits

- **Self-critique:** the narrator and critic are the SAME model (`deepseek-flash`);
  a model is often lenient on its own output, so served_error_rate is optimistic.
- **Single provider / single model.** No cross-family comparison yet.
- **temperature = 0.0**: drift is deterministic knowledge error, not sampling noise.
- **Oracle definition:** any numeric deviation at the canonical value's precision
  (rounding, unit change) counts as drift; a more-precise correct answer is faithful.
- **Cost** is derived from the API's token counts × the disclosed V4-Flash rate card
  ($0.14/M in, $0.28/M out); the raw token totals are the ground truth.

Reproduce: `DEEPSEEK_API_KEY=… uv run python -m experiments.model_drift.live --audit`.
