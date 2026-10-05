# ISNAD φ study — pre-registration

**Committed: 2026-10-05.** The full sweep runs only after this file is committed.
This is the protocol, frozen before any model call on the full corpus.

## Scientific question
When two apparently-independent transmission chains are actually statistically
correlated, how much trust should corroboration contribute? Measure whether ISNAD's
madār assumption (disjoint narrators ⇒ independent) holds, and (in Experiment C) test
whether a φ-discounted corroboration policy cuts false upgrades.

## Models (AMENDED 2026-10-05 — 4 families × 2 sizes, 8 total)
The original roster (google/nvidia/deepseek/poolside via OpenRouter free tier) was
replaced after provider key reality: OpenAI (no credits), Anthropic (low balance),
Qwen (invalid key). The working roster — all with live keys, all parsing 64/64 in
sweep C — is:

| family | small | large |
|---|---|---|
| deepseek (direct key) | deepseek-chat | deepseek-reasoner |
| kimi (Moonshot) | kimi-k2.6 | kimi-k3 |
| glm (Zhipu) | glm-5.3-flash | glm-5.3 |
| perplexity | sonar | sonar-pro |

## Corpus (AMENDED 2026-10-05 — expanded 64 → 393)
`corpus.json` — 385 hard numeric facts (``corpus_hard.HARD_FACTS``) + the 8
post-cutoff facts from the model-drift corpus (ids ``md_pcXX`` kept stable).
Domains: astronomy 75, chemistry 75, geography 75, physics 45, history 40,
sports 30, demographics 25, biology 10, recent 10, post-cutoff 8. Every fact has a
fixed, verifiable oracle (CODATA/PDG/IAU/NASA/CRC/Wikipedia-level) and a ``source``
tag. Uncertain oracles were dropped, not estimated.

## Prompt + sampling
- Prompt: "Answer the following question with just the numeric value (no units, no prose): {question}"
- temperature 0 · max_tokens 2048 (reasoning models emit reasoning_content that eats max_tokens).
- **AMENDMENT (disclosed deviation):** kimi (Moonshot) reasoning models reject
  `temperature=0` ("only 1 is allowed for this model"), so kimi runs at
  `temperature=1`; every other provider stays at `temperature=0`. Recorded in
  ``runner.py`` (``_TEMPERATURE``) — a provider-constraint deviation, not protocol drift.
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
Any model with error rate < 1% or > 99% is excluded from its φ pairs AND from the
`k` used in `n_eff` (φ is unstable at the boundary), and the exclusion is disclosed
in `stats.json` (``excluded`` map).

## Commit policy
`results/*.json` is gitignored (raw model outputs are large + reproducible). `corpus.json`,
`stats.json`, the `.py` files, and this file are committed.
