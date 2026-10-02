# Model-drift leaderboard — LIVE results (#71)

**Narrator:** `deepseek-flash` · **Critic:** `deepseek-v4-pro` · **date:** 2026-09-11
**Calls:** 1300 · **tokens:** 140714 in / 380791 out · **cost:** $0.24968 (cap $2.00)
**dataset_sha256:** `53e319c33cb0e599…`

## Aggregate (all facts)

| Depth | hallucination_rate (oracle) | served_error_rate (real critic) |
|---|---|---|
| 1 | 0.077 | 0.000 |
| 2 | 0.092 | 0.167 |
| 3 | 0.061 | 0.500 |
| 4 | 0.061 | 0.000 |
| 5 | 0.061 | 0.250 |

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
| 1 | 0.625 | 0.000 | 8 |
| 2 | 0.750 | 0.333 | 8 |
| 3 | 0.500 | 0.333 | 8 |
| 4 | 0.500 | 0.000 | 8 |
| 5 | 0.500 | 0.200 | 8 |

> **n = 8** — `pc09` ("11 world records ratified in 2026") is excluded as ill-posed
> mid-year. The rates above re-derive the committed n=9 run by dropping `pc09`; the
> pinned corpus hash is unchanged (53e319c3…).

## Oracle cross-check (independent LLM audit)

agreement rate: **0.967** (29/30) — same model family as the critic under test — a sanity check, not independent ground truth.

## Honest limits

- **Cross-model critic:** narrator is `deepseek-flash`, critic is `deepseek-v4-pro` —
  the self-critique confound is removed, but a model is still lenient on its own
  family, so served_error_rate remains optimistic.
- **Truncated calls: 36** (`finish_reason=length`) — recorded and rendered as
  "unverifiable", never silently dropped.
- **Single provider / single model.** No cross-family comparison yet.
- **temperature = 0.0**: drift is deterministic knowledge error, not sampling noise.
- **Oracle definition:** any numeric deviation at the canonical value's precision
  (rounding, unit change) counts as drift; a more-precise correct answer is faithful.
- **Cost** is derived from the API's token counts × the disclosed V4-Flash rate card
  ($0.14/M in, $0.28/M out); the raw token totals are the ground truth.

Reproduce: `DEEPSEEK_API_KEY=… uv run python -m experiments.model_drift.live --audit`.
