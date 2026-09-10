# Model-drift leaderboard (#71)

How does a claim's **hallucination rate** grow as it passes through an increasingly
**deep multi-agent chain** (depth 1..5) — and how well does ISNAD's chain-grade +
content-critic + decision-matrix pipeline **catch** that hallucination at each depth?

The methodology is **preregistered** (frozen before any result):
[`experiments/model_drift/PREREGISTRATION.md`](https://github.com/alizahidraja/isnad/blob/main/experiments/model_drift/PREREGISTRATION.md).

## Live results — DeepSeek V4 Flash (`deepseek-flash`)

[`experiments/model_drift/results/LIVE_RESULTS.md`](https://github.com/alizahidraja/isnad/blob/main/experiments/model_drift/results/LIVE_RESULTS.md)
· raw: [`results/live_results.json`](https://github.com/alizahidraja/isnad/blob/main/experiments/model_drift/results/live_results.json)

65 facts (8 easy / 20 medium / 28 hard / 9 **post-cutoff**), temperature 0.0,
1,300 calls, **$0.099** total, 27 truncated calls (recorded, not hidden).

| Depth | hallucination_rate (oracle) | served_error_rate (real critic) |
|---|---|---|
| 1 | **0.061** | 0.000 |
| 2 | **0.061** | 0.000 |
| 3 | **0.077** | 0.400 |
| 4 | **0.077** | 0.400 |
| 5 | **0.061** | 0.000 |

All hallucination comes from the **post-cutoff** tier (facts after the model's
~mid-2026 training cutoff), where the model confidently states stale values — e.g.
the 400m hurdles world record as **45.94** (true: 45.80), the Knicks' last title as
**1973** (true: 2026), Spain's last World Cup as **2010** (true: 2026):

| Tier | hallucination_rate (depth 1) |
|---|---|
| easy / medium / hard | **0.000** (0 drift — well-known facts) |
| post-cutoff | **0.444–0.556** |

**Oracle cross-check (independent LLM audit):** 0.90 agreement (27/30). Ground-truth
labels come from an **LLM-free numeric oracle**, so the labels themselves cannot hallucinate.

### What this honestly shows
1. **Hallucination originates at memory-generation, not chain depth.** The rate is
   *flat* across depths 1..5 (the relay faithfully propagates whatever hop 1 produced).
   Deep multi-agent chains do **not** amplify hallucination here — the first hop does.
2. **The critic is mostly-but-not-fully reliable even with evidence in context** — and a
   stronger cross-model critic does not fix it: served_error_rate 0.0–0.4 with a
   `deepseek-flash` self-critic, 0.0–0.5 with a `deepseek-v4-pro` critic (both miss up to
   ~2 of 4–5 hallucinated claims).
3. **A frontier model does not drift on well-known facts** (0.000) — only on
   post-cutoff facts where it has no correct prior.

## Offline results (pipeline plumbing, deterministic)

[`experiments/model_drift/results/RESULTS.md`](https://github.com/alizahidraja/isnad/blob/main/experiments/model_drift/results/RESULTS.md)

| Depth | hallucination_rate (oracle) | served_error_rate (perfect critic) | served_error_rate (empty critic) |
|---|---|---|---|
| 1 | 0.167 | 0.000 | 1.000 |
| 2 | 0.417 | 0.000 | 1.000 |
| 3 | 0.583 | 0.000 | 1.000 |
| 4 | 0.667 | 0.000 | 1.000 |
| 5 | 0.750 | 0.000 | 1.000 |

## Reproduce

```bash
# offline (no keys): deterministic drift-injector stand-in
uv run python -m experiments.model_drift.run --seed 0

# live (DeepSeek): key from env, $2 hard cap, optional --audit
DEEPSEEK_API_KEY=… uv run python -m experiments.model_drift.live --audit
```

## Hard limits (stated, not hidden)

- **Self-critique (measured both ways)**: narrator is `deepseek-flash`; served_error_rate
  is reported for both a `deepseek-flash` self-critic (0.0–0.4) and a `deepseek-v4-pro`
  cross-model critic (0.0–0.5) — neither is a substitute for human adjudication.
- **Single provider / single model**; **temperature 0.0** (deterministic knowledge
  error, not sampling noise — a temperature>0 × multi-seed pass is the other next step).
- **Oracle is numeric and unit-blind**: a correct answer in another unit (26.2 miles)
  counts as drift, and a right number with a wrong unit is missed. Disclosed, not fixed.
- **Truncated calls** (finish_reason=length, when reasoning exhausts the token budget)
  are recorded and rendered as "unverifiable", never silently dropped.
- **Cost** is derived from token counts × the disclosed V4-Flash rate card
  ($0.14/M in, $0.28/M out); raw token totals are the ground truth.
- The metric does **not** claim general hallucination-detection superiority (#71).
