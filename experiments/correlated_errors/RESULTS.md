# ISNAD φ study — results

**Question:** when two apparently-independent transmission chains are actually
statistically correlated, how much trust should corroboration contribute? We measure
the error correlation φ across models, apply the Kish effective-sample-size discount,
and test whether a φ-discounted corroboration policy cuts false upgrades.

## Protocol (see `PREREGISTRATION.md`)
- 4 families × 2 sizes = 8 models (deepseek, kimi, glm, perplexity — all with live keys).
- 393-fact corpus: 385 hard numeric facts + 8 post-cutoff (ids `md_pcXX` stable).
- Temperature 0 (kimi = 1, a disclosed provider deviation); max_tokens 2048.
- Error = parsed answer differs from oracle by relative > 1e-6 (or missing/refused).
- φ = phi coefficient on binary error vectors; Kim same-wrong reported separately.
- Kish `n_eff = k/(1+(k−1)φ̄)` + cluster-bootstrap 95% CI (resample by claim).
- Exclusion: models outside [1%, 99%] error-rate band dropped from φ pairs AND `k`.

## Preliminary result — 64-fact corpus (sweep C, BEFORE the expansion)
> **This is preliminary and unstable** (only 8 post-cutoff facts carry error signal;
> the 56 well-known facts are ~0-error). Reported for transparency, superseded below.

- **φ̄ = 0.77** across all parseable pairs (8 models, 64/64 parsed).
- **Same-family φ ≈ 0.85–1.0** (deepseek 0.89, glm 0.89, kimi 0.89, perplexity 0.85).
- **Cross-family within {deepseek, glm, kimi} ≈ 0.85–0.93** — these three "competing"
  vendors err together.
- **Cross-family vs perplexity ≈ 0.65–0.75** — perplexity is the only semi-independent
  family (it errs differently).
- **Kish n_eff ≈ 1.2** for 8 models → ~6.7× over-crediting if independence is assumed.

## Preliminary finding
## Final result — 393-fact corpus (the number to cite)

**φ̄ = 0.5667 · n_eff = 1.611 · 95% CI [1.515, 1.724]** (k = 8, all 8 models retained;
7 broken free-tier models excluded at 100% parse-failure per the pre-reg [1%,99%] band).

### Per-model error rates (all within [1%, 99%], none excluded)
| model | error rate |
|---|---|
| glm-5.3 | 25.4% |
| deepseek-chat | 26.0% |
| glm-5.3-flash | 26.2% |
| kimi-k3 | 29.0% |
| deepseek-reasoner | 31.6% |
| kimi-k2.6 | 32.6% |
| perplexity-sonar-pro | 35.9% |
| perplexity-sonar | 40.7% |

### φ breakdown
- **Same-family φ:** deepseek 0.532 · glm 0.614 · kimi 0.643 · perplexity 0.706.
- **Cross-family φ range:** 0.394 (glm-5.3 ↔ perplexity-sonar) to 0.723 (deepseek-reasoner ↔ kimi-k3).
- **The 64-fact "perplexity is the most independent family" finding did NOT replicate.** On 393
  facts perplexity has the *highest* same-family φ (0.706) and cross-family φ comparable to the
  others. The 64-fact conclusion was an artifact of the tiny error set. Corrected here.

### Headline
ISNAD's madār assumption (disjoint narrators ⇒ independent) is violated: **8 nominally-independent
transmitters carry only 1.61 effective votes** (~5× over-crediting; the preliminary 64-fact run
suggested ~6.7×, but 1.61 is the stable 393-fact estimate the paper should cite).

## Experiment B/C — false-upgrade reduction

At threshold = 2 (corroboration by ≥2 disjoint routes):

| policy | false-upgrade rate | coverage | risk | upgrades |
|---|---|---|---|---|
| naive (assumes independence) | 23.4% | 100% | 23.4% | 393 |
| φ-discounted | 8.1% | 68.4% | 11.9% | 269 |

**Δfalse-upgrade = −15.3 pp (−65% relative)**, at the cost of 31.6% coverage (the discount correctly
refuses the "corroboration" that is actually a correlated duplicate of a wrong answer).
Δrisk = −11.5 pp.

*Caveat:* these are not yet at exactly-matched coverage (naive is quoted at 100% coverage); a
threshold sweep for matched-coverage comparison is a follow-up, but the direction is monotone and
locked by `tests/test_correlated_errors.py`.
## Deviations & caveats
- **kimi temperature=1** (provider rejects temperature=0) — disclosed in the prereg.
- The 64-fact preliminary φ is **not** a stable estimate; the 393-fact corpus is the
  number the paper should cite.
- `results/*.json` is gitignored (reproducible); `corpus.json`, `stats.json`, and the
  `.py` files are committed.
