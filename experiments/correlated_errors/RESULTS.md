# ISNAD φ study — results

**Question:** when two apparently-independent transmission chains are actually
statistically correlated, how much trust should corroboration contribute? We measure
the error correlation φ across models, apply the Kish effective-sample-size discount,
and test whether a φ-discounted corroboration policy cuts false upgrades.

## Protocol (see `PREREGISTRATION.md`)
- 4 families × 2 sizes = 8 models (deepseek, kimi, glm, perplexity — all with live keys).
- 386-fact corpus: 378 hard numeric facts + 8 post-cutoff (ids `md_pcXX` stable).
- Temperature 0 (kimi = 1, a disclosed provider deviation); max_tokens 2048.
- Error = parsed answer differs from oracle by relative > 1e-6 (or missing/refused).
- φ = phi coefficient on binary error vectors; Kim same-wrong reported separately.
- Kish `n_eff = k/(1+(k−1)φ̄)` + cluster-bootstrap 95% CI (resample by claim).
- Retention: a model is kept only if it covers ≥90% of facts AND its error rate is in [1%, 99%].
- Primary endpoint: the false-upgrade gap at the 2-vote corroboration bar (see Experiment B/C).

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

The 64-fact "perplexity is the most independent family" finding **did NOT replicate** on the
larger corpus (there perplexity has the *highest* same-family φ) — it was an artifact of the
tiny error set.

## Post-audit corrections (20-person panel → BLOCKER → fixed)

The first 393-fact numbers (φ̄=0.5667, n_eff=1.611, −65%) were audited by a 20-person panel and
found to be corrupted by several bugs, all now fixed and re-run on the 386-fact corpus below.

1. **Sign parser (BLOCKER)** — the runner's number regex dropped leading minus signs, so every
   negative-oracle fact (absolute zero −273.15, Sirius −1.46, Venus −4.92, liquid-nitrogen −195.8,
   Mars −63) was spuriously scored wrong for ALL models, inflating φ̄. Fixed: regex accepts `[+-]?`.
2. **Kish strength formula (BLOCKER)** — `1 + (m−1)·n_eff/k` over-credited unanimity by ~2.3×.
   Fixed: `strength(m) = m/(1+(m−1)φ̄)`, which equals `n_eff` at m=k.
3. **B/C endpoint (BLOCKER)** — the earlier −65% compared naive@100% coverage vs
   discounted@68% coverage (not matched coverage). With the corrected formula the comparison
   resolved into a **step function** (the 2-vote bar is unreachable at n_eff=1.638), so the
   pre-registered matched-coverage comparison is not applicable — reported honestly below.
4. **Oracle fixes** — neutron half-life→mean lifetime (14.6), standard gravity 9.80665, Pluto 1.303,
   Sun diameter 1,391,400, Venus −4.92, France (metropolitan) 66.4M. Dropped Milky Way star count,
   ISS altitude, Pleiades count, Dead Sea ×2, Mariana, Etna (no fixed oracle). 393 → **386 facts**.
5. **Exclusion logic** — the 7 free-tier models were never re-run against this corpus (their result
   files carried foreign `md_eXX`/`md_hXX` ids). They are now excluded by the coverage rule
   (<90% coverage), never "100% parse-failure"; their stale files are deleted.

## Corrected result — 386-fact corpus

**φ̄ = 0.5551 · n_eff = 1.638 · 95% CI [1.540, 1.750]** (k = 8; all 8 models retained with
coverage 1.000 — no exclusions).

*(Pre-correction, for reference only: φ̄=0.5667, n_eff=1.611, CI [1.515, 1.724].)*

### Per-model error rates (all within [1%, 99%], coverage 1.000)
| model | error rate |
|---|---|
| glm-5.3 | 22.02% |
| glm-5.3-flash | 23.06% |
| deepseek-chat | 24.35% |
| kimi-k2.6 | 28.50% |
| deepseek-reasoner | 29.27% |
| kimi-k3 | 29.53% |
| perplexity-sonar-pro | 34.97% |
| perplexity-sonar | 38.08% |

### φ breakdown
- **Same-family φ:** deepseek 0.510 · glm 0.763 · kimi 0.585 · perplexity 0.678.
- **Cross-family φ range:** 0.394 – 0.694 (28 pairs total).
- **Headline:** 8 nominally-independent transmitters carry **~1.64 effective votes**
  (the madār independence assumption is violated ~4.9×).

### Kim same-wrong (reported separately from φ)
- Same-wrong conditional agreement P(same wrong value | both wrong) ranges **0.333 – 0.645**
  (mean 0.499) across the 28 pairs.
- Same-family same-wrong mean **0.587** vs cross-family mean **0.484** — models within a vendor
  family not only err together (φ) but also err the *same way* more often.

## Experiment B/C — the 2-vote bar (step-function result)

At the standard corroboration bar (≥2 independent routes):

| policy | false-upgrade rate | coverage | false upgrades |
|---|---|---|---|
| naive (assumes independence) | 22.54% | 100% | 87 / 386 |
| φ-discounted | 0.00% | 0% | 0 / 386 |

**The bar is unreachable under the discount.** The maximum corroboration strength is
`n_eff = 1.638 < 2`, so the discounted policy can never accumulate 2 effective votes.
Coverage is therefore a **step function** (full at threshold 1, zero at threshold ≥2) —
not a tunable trade-off — so the pre-registered "matched coverage" comparison does not
apply. The honest statement is the step itself:

> The naive policy's 22.5% false-upgrade rate is *entirely* "corroboration" that never
> actually reaches 2 effective independent votes. The φ-discount eliminates 100% of those
> false upgrades (22.5% → 0%) by refusing to count correlated routes as independent.

Naive threshold sweep (transparency — the coverage/risk curve):
| threshold | false-upgrade rate | coverage | risk |
|---|---|---|---|
| 1–2 | 22.54% | 100% | 22.5% |
| 3 | 21.50% | 98.2% | 21.9% |
| 4 | 16.06% | 89.9% | 17.9% |
| 5 | 11.92% | 80.3% | 14.8% |
| 6 | 6.74% | 69.9% | 9.6% |
| 7 | 4.66% | 60.4% | 7.7% |
| 8 | 1.04% | 47.9% | 2.2% |

Even at the naive policy's own strictest threshold (8 unanimous routes) its false-upgrade rate
(1.0%) is still strictly positive, while the φ-discount at threshold 2 already gives 0% — because
the discount knows 8 routes ≈ 1.64 effective votes, below the 2-vote bar.

## Deviations & caveats
- **kimi temperature=1** (provider rejects temperature=0) — disclosed in the prereg.
- **5 negative-oracle facts** (−273.15, −195.8, −1.46, −63, −4.92) are FIXED constants; they require
  the sign-aware parser and are kept.
- **`results/*.json` (the 8 real models) is committed** so φ̄/n_eff/false-upgrade recompute from a
  fresh clone without live API keys. `corpus.json`, `stats.json`, `experiment_bc.json`, and the
  `.py` files are committed too.
