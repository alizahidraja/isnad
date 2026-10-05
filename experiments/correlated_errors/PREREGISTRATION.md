# ISNAD φ study — pre-registration

**Committed: 2026-10-05.** The full sweep runs only after this file is committed.
This is the protocol, frozen before any model call on the full corpus.

## Scientific question
When two apparently-independent transmission chains are actually statistically
correlated, how much trust should corroboration contribute? Measure whether ISNAD's
madār assumption (disjoint narrators ⇒ independent) holds, and (in Experiment C) test
whether a φ-discounted corroboration policy cuts false upgrades.

## Models (AMENDED 2026-10-05 — 4 families × 2 sizes, 8 total)
The roster changed twice, for provider-key reality:

1. **Earlier plan** (change.md): OpenAI / Anthropic / Google. Blocked — OpenAI had no
   credits, Anthropic a low balance, Qwen an invalid key.
2. **Scaffold pre-reg** (before sweep A): google / nvidia / deepseek / poolside via the
   OpenRouter free tier. Blocked — the shared free pool rate-limited (0 parseable answers
   on the full sweep).
3. **Final roster** (sweep C onward) — all with live keys, all parsing 64/64 in sweep C:

| family | small | large |
|---|---|---|
| deepseek (direct key) | deepseek-chat | deepseek-reasoner |
| kimi (Moonshot) | kimi-k2.6 | kimi-k3 |
| glm (Zhipu) | glm-5.3-flash | glm-5.3 |
| perplexity | sonar | sonar-pro |

## Corpus (AMENDED 2026-10-05 — 378 facts)
`corpus.json` — 378 hard numeric facts (`corpus_hard.HARD_FACTS`) with NO post-cutoff facts.
Domains: astronomy 72, chemistry 75, geography 71, physics 45, history 40, sports 30,
demographics 25, biology 10, recent 10.

Every fact has a fixed, verifiable oracle (CODATA/PDG/IAU/NASA/CRC/Wikipedia-level) and a
`source` tag. Uncertain oracles were dropped, not estimated: 7 facts with range/observer/
time-varying oracles (Milky Way star count, ISS altitude, Pleiades count, Dead Sea ×2,
Mariana Trench, Mount Etna) were removed after the 20-person panel's oracle audit, along
with 6 value fixes (neutron mean-lifetime, standard gravity 9.80665, Pluto 1.303, Sun
diameter 1,391,400, Venus −4.92, France-metropolitan 66.4M).

**CORRECTION (brutal panel, 2026-10-05):** the 8 post-cutoff `md_pcXX` facts were DROPPED.
Their oracles were fabricated/unverifiable (e.g. "Knicks most recent championship" oracle
`2026`, real answer 1973; uncited 2026 Olympics medals + future world records) — they came
from the model-drift *hallucination probe*, whose oracles are invented, and violate this
corpus's fixed-verifiable-oracle contract. 386 → **378 facts** (378 hard, 0 post-cutoff).

## Prompt + sampling
- Prompt: "Answer the following question with just the numeric value (no units, no prose): {question}"
- temperature 0 · max_tokens 2048 (reasoning models emit reasoning_content that eats max_tokens).
- **AMENDMENT (disclosed deviation):** kimi (Moonshot) reasoning models reject
  `temperature=0` ("only 1 is allowed for this model"), so kimi runs at
  `temperature=1`; every other provider stays at `temperature=0`. Recorded in
  ``runner.py`` (``_TEMPERATURE``) — a provider-constraint deviation, not protocol drift.
- Retry 429/5xx with exponential backoff; record the failure if 5 attempts exhaust.
- The number parser accepts an optional leading sign (`[+\-\u2012\u2013\u2212]?\d+…`) — required for
  the 5 negative-oracle facts (−273.15, −195.8, −1.46, −63, −4.92), all FIXED constants.
  **CORRECTION (brutal panel, 2026-10-05):** the earlier fix only matched ASCII `+`/`-`;
  perplexity/sonar emitted U+2212 MINUS SIGN for `hard-p002` and it was still parsed as a
  positive number. The parser now normalizes U+2212 / U+2013 (en-dash) / U+2012 (figure
  dash) to ASCII `-`, and a targeted offline re-parse fixed the one affected cell.

## Error definition
A model's answer is an **error** iff its parsed number (last number in `content`, or in
`reasoning`/`reasoning_content` when content is empty) differs from `oracle_value` by
relative > 1e-6, OR (for `oracle_value == 0`) by absolute > 1e-9. Missing/refused answers
are errors, but a fact *absent from a model's result file* is treated as MISSING (excluded
from denominators), never an error.

## φ definition
Per model pair, the **phi coefficient** on the two binary error indicator vectors:
φ = (ad−bc) / √((a+b)(c+d)(a+c)(b+d)) where a = both wrong, b = i wrong & j right,
c = i right & j wrong, d = both right. Equals Pearson r on the 0/1 indicators.
Separately report the **same-wrong conditional agreement** P(same wrong value | both wrong)
— Kim's statistic, NOT the same quantity as φ. Same-wrong is judged by **numeric equality**
of the two parsed answers (`float(u) == float(v)`), never raw-string equality; two
missing/refused answers do NOT count as "same wrong value".

## Aggregation
Mean pairwise φ̄ across all pairs → **Kish n_eff = k / (1 + (k−1)φ̄)**, with a
**cluster-bootstrap 95% CI (resample by claim, NOT iid)**, 1000 draws, seed 0, percentile
by linear interpolation. φ̄ is computed from full-precision per-pair φ (never from rounded
values), and `k` is the number of RETAINED models.

**Corroboration strength** (Experiment C): `strength(m) = m / (1 + (m−1)φ̄)` — Kish's exact
equicorrelation form, equal to `n_eff` at m=k. φ=0 reduces it to the naive count `m`.

## Primary endpoint (Experiment C, after A)
Δfalse-upgrade rate between naive corroboration (assumes independence) and φ-discounted
corroboration, at **matched coverage**. **CORRECTION (2026-10-05):** with the measured
φ̄>0, the discounted policy's maximum strength is `n_eff < 2`, so the 2-vote bar is
UNREACHABLE and coverage is a step function (full at threshold 1, zero at threshold ≥2) —
matched coverage is not applicable and the step itself is the honest primary result.
Secondary: Δcoverage, Δrisk.

## Exclusion rules
A model is kept for the φ matrix and for `k` only if it **covers ≥90% of the corpus facts**
AND its **error rate is in [1%, 99%]** (φ is unstable at the boundary). Exclusions are
disclosed in `stats.json` (``excluded`` map, with the reason).

## Commit policy
The 8 per-model `results/*.json` files ARE committed so φ̄ / n_eff / false-upgrade recompute
from a fresh clone without live API keys. `corpus.json`, `stats.json`, `experiment_bc.json`,
the `.py` files, and this file are committed.
