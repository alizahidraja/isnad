# ISNAD φ study — pre-registration

**Committed: 2026-10-05.** The full sweep runs only after this file is committed.
This is the protocol, frozen before any model call on the full corpus.

## Scientific question
When two apparently-independent transmission chains are actually statistically
correlated, how much trust should corroboration contribute? Measure whether ISNAD's
madār assumption (disjoint narrators ⇒ independent) holds, and (in Experiment C) test
whether a φ-discounted corroboration policy cuts false upgrades.

## Models (4 families × 2 sizes, 8 total)
| family | small | large |
|---|---|---|
| google | google/gemma-4-26b-a4b-it:free | google/gemma-4-31b-it:free |
| nvidia | nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free | nvidia/nemotron-3-super-120b-a12b:free |
| deepseek (direct key) | deepseek/deepseek-chat | deepseek/deepseek-reasoner |
| poolside | poolside/laguna-xs-2.1:free | poolside/laguna-s-2.1:free |

## Corpus
`corpus.json` — the model-drift `HARD_CORPUS` (64 facts after pc09's exclusion):
56 well-known facts (the agreement control) + 8 post-cutoff facts (the error signal).
Source filtering: §8 `claims.json` prose is NOT a clean oracle source and is excluded;
expanding the hard-facts subset toward ~400 is a follow-up step disclosed here.

## Prompt + sampling
- Prompt: "Answer the following question with just the numeric value (no units, no prose): {question}"
- temperature 0 · max_tokens 2048 (reasoning models emit reasoning_content that eats max_tokens).
- Retry 429/5xx with exponential backoff; record the failure if 5 attempts exhaust.

## Error definition
A model's answer is an **error** iff its parsed number (last number in `content`, or in
`reasoning`/`reasoning_content` when content is empty) differs from `oracle_value` by
relative > 1e-6 (or is missing/refused). Refusals/parse-failures are counted separately.

## φ definition
Per model pair, the **phi coefficient** on the two binary error indicator vectors:
φ = (ad−bc) / √((a+b)(c+d)(a+c)(b+d)) where a = both wrong, b = i wrong & j right,
c = i right & j wrong, d = both right. Equals Pearson r on the 0/1 indicators.
Separately report the **same-wrong conditional agreement** P(same wrong value | both wrong)
— Kim's statistic, NOT the same quantity as φ.

## Aggregation
Mean pairwise φ̄ across all pairs → **Kish n_eff = k / (1 + (k−1)φ̄)**, with a
**cluster-bootstrap 95% CI (resample by claim, NOT iid)**, 1000 draws, seed 0.

## Primary endpoint (Experiment C, after A)
Δfalse-upgrade rate between naive corroboration (assumes independence) and φ-discounted
corroboration, at matched coverage. Secondary: Δcoverage, Δrisk at matched coverage.

## Exclusion rules
Any model with error rate < 1% or > 99% is excluded from its φ pairs (φ is unstable at
the boundary) and the exclusion is disclosed in `stats.json`.

## Commit policy
`results/*.json` is gitignored (raw model outputs are large + reproducible). `corpus.json`,
`stats.json`, the `.py` files, and this file are committed.
