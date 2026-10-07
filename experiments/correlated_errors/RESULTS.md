# ISNAD φ study — results

**Question:** when two apparently-independent transmission chains are actually
statistically correlated, how much trust should corroboration contribute? We measure
the error correlation φ across models, apply the Kish effective-sample-size discount,
and test whether a φ-discounted corroboration policy cuts false upgrades.

## Protocol (see `PREREGISTRATION.md`)
- 4 families × 2 sizes = 8 models (deepseek, kimi, glm, perplexity — all with live keys).
- **378-fact corpus** (378 hard numeric facts; the 8 `md_pcXX` post-cutoff facts were dropped — see corrections).
- Temperature 0 (kimi = 1, a disclosed provider deviation); max_tokens 2048.
- Error = parsed answer differs from oracle by relative > 1e-6, OR (for an oracle of 0) by absolute > 1e-9; missing/refused/truncated answers are errors (counted separately).
- φ = phi coefficient on binary error vectors; Kim same-wrong reported separately.
- Kish `n_eff = k/(1+(k−1)φ̄)` + cluster-bootstrap 95% CI (resample by claim).
- Retention: a model is kept only if it covers ≥90% of facts AND its error rate is in [1%, 99%].
- Primary endpoint — **AMENDED (post-audit)**: the pre-committed "matched coverage" endpoint is
  not applicable (see Experiment B/C below); the amended primary endpoint is the false-upgrade gap
  at the 2-vote corroboration bar, reported as a step function.

## Preliminary result — 64-fact corpus (sweep C, BEFORE the expansion)
> **This is preliminary and unstable** (only 8 post-cutoff facts carry error signal;
> the 56 well-known facts are ~0-error). Reported for transparency, superseded below.

- **φ̄ = 0.77** across all parseable pairs (8 models, 64/64 parsed).
- The 64-fact "perplexity is the most independent family" finding **did NOT replicate** on the
  larger corpus — it was an artifact of the tiny error set.

## Post-audit corrections (20-person panel → BLOCKER → fixed; brutal 7-auditor panel → 2 more → fixed; final small-things pass)
The first 393-fact numbers (φ̄=0.5667, n_eff=1.611, −65%) were audited by a 20-person panel and
found corrupted by several bugs, all fixed and re-run. A follow-up 7-auditor brutal panel found
two more, both fixed offline. The number to cite is the 378-fact result below.

1. **Sign parser (BLOCKER)** — the regex dropped leading minus signs, so every negative-oracle
   fact was spuriously scored wrong for ALL models. Fixed: regex accepts `+`, `-`, U+2212, U+2013, U+2012.
2. **Kish strength formula (BLOCKER)** — `1 + (m−1)·n_eff/k` over-credited unanimity ~2.3×.
   Fixed: `strength(m) = m/(1+(m−1)φ̄)`, which equals `n_eff` at m=k.
3. **B/C endpoint (BLOCKER)** — the earlier −65% compared naive@100% vs discounted@68% coverage.
   With the corrected formula the comparison is a **step function** (the 2-vote bar is unreachable),
   so matched-coverage is not applicable — reported honestly below.
4. **Oracle fixes** — neutron mean-lifetime 14.6, standard gravity 9.80665, Pluto 1.303, Sun diameter
   1,391,400, Venus −4.92, France (metropolitan) 66.4M. Dropped Milky Way star count, ISS altitude,
   Pleiades count, Dead Sea ×2, Mariana, Etna (no fixed oracle). 393 → **386 facts**.
5. **Unicode minus sign U+2212 (BLOCKER, brutal panel)** — the `[+-]?` fix only matched ASCII, so
   perplexity/sonar's `"−273.15"` (absolute zero) was still parsed as `"273.15"`. Fixed by
   normalizing U+2212/en-dash/figure-dash to ASCII `-` and a **targeted offline re-parse** (NOT a
   full re-parse — the stored `raw` is truncated to 200 chars and reasoning models put the answer
   after long reasoning).
6. **Fabricated post-cutoff oracles (BLOCKER, brutal panel)** — the 8 `md_pcXX` facts carried
   fabricated/unverifiable oracles (e.g. "Knicks most recent championship" = `2026`, real answer
   1973). Dropped. 386 → **378 facts** (378 hard, 0 post-cutoff).
7. **Exclusion logic** — the 7 free-tier models were never re-run against this corpus; they are
   excluded by the coverage rule (<90% coverage), never "100% parse-failure".
8. **Truncated reasoning answers (final small-things pass)** — reasoning models that hit
   `max_tokens` (`finish_reason == "length"`) were previously scored by a "last number in the
   reasoning" heuristic that lifted garbage numbers from mid-reasoning (e.g. kimi-k3 `hard-a065`
   → `"777"`). Those 87 rows are now treated as **unparseable** (`answer_value = null`,
   `error = "truncated (finish_reason=length)"`) and counted separately in `stats.json`
   (`truncated_count`). The headline is essentially unchanged (φ̄ 0.5599 before/after), because the
   truncated answers were already scored wrong; only 10 of 87 had previously parsed to a "correct"
   value. Per-model truncated counts: deepseek-reasoner 31, glm-5.3 3, kimi-k2.6 46, kimi-k3 7.

## Corrected result — 378-fact corpus

**φ̄ = 0.5599 · n_eff = 1.626 · 95% CI [1.531, 1.741]** (k = 8; all 8 models retained with
coverage 1.000 — no exclusions).

### Per-model error rates (all within [1%, 99%], coverage 1.000)
| model | error rate |
|---|---|
| glm-5.3 | 20.90% |
| glm-5.3-flash | 21.43% |
| deepseek-chat | 23.02% |
| deepseek-reasoner | 27.78% |
| kimi-k3 | 28.04% |
| kimi-k2.6 | 29.10% |
| perplexity-sonar-pro | 35.19% |
| perplexity-sonar | 38.62% |

### φ breakdown
- **Same-family φ (4 pairs, mean 0.617):** deepseek 0.489 · glm 0.731 · kimi 0.560 · perplexity 0.690.
- **Cross-family φ (24 pairs, mean 0.550):** range 0.428 – 0.678.
- **Full φ range across all 28 pairs: 0.428 – 0.731** — every one is large and positive.
- **Headline:** 8 nominally-independent transmitters carry **~1.63 effective votes**
  (the madār independence assumption is violated ~4.9×).
- **Cross-family-only φ̄ = 0.550 → n_eff = 1.65** (vs same-family-only φ̄ = 0.617). The full
  φ̄ = 0.5599 mixes 4 same-vendor pairs with 24 cross-vendor pairs, slightly inflating φ̄ relative
  to a strict "independent vendors" framing — but the headline is robust either way: even
  cross-vendor-only, n_eff ≈ 1.65 ≪ 8.

*Caveat (Kish equicorrelation approximation):* φ̄ = 0.5599 is the mean over a heterogeneous
pairwise-φ matrix (range 0.43–0.73). Kish `n_eff = k/(1+(k−1)φ̄)` assumes a single equicorrelation
φ̄, so n_eff = 1.63 is an approximation, not an exact design effect; the bootstrap CI
[1.53, 1.74] reflects resampling uncertainty but not the equicorrelation-model uncertainty. A
variance-weighted design effect (allowing heterogeneous φ and per-model error variance) gives
n_eff ≈ 1.64, agreeing to ~0.3%.

*Caveat (rounding tolerance):* the 1e-6 relative tolerance scores uniform significant-figure
rounding as a "correlated error" — e.g. oracle −195.8 answered as −196 by all 8 models. So φ̄
partly reflects shared numeric-precision conventions, not only shared factual error. The
independence-violation conclusion is unaffected (the same rounding tolerance is applied to every
model and every pair), but φ̄ should not be read as pure "knowledge error" correlation.

### Kim same-wrong (reported separately from φ)
- Same-wrong conditional agreement P(same wrong value | both wrong) ranges **0.307 – 0.662**
  (mean 0.469) across the 28 pairs.
- Same-family same-wrong mean **0.561** vs cross-family mean **0.454** — models within a vendor
  family not only err together (φ) but also err the *same way* more often.
- Same-wrong is judged by **numeric equality** (`float(u) == float(v)`), never raw-string equality;
  two missing/refused answers never count as "same wrong value".

## Experiment B/C — the 2-vote bar (step-function result)

At the standard corroboration bar (≥2 independent routes):

| policy | false-upgrade rate | coverage | false upgrades |
|---|---|---|---|
| naive (assumes independence) | 21.16% | 99.7% | 80 / 378 |
| φ-discounted | 0.00% | 0% | 0 / 378 |

**The bar is unreachable under the discount.** The maximum corroboration strength is
`n_eff = 1.626 < 2`, so the discounted policy can never accumulate 2 effective votes.
Coverage is therefore a **step function** (full at threshold 1, zero at threshold ≥2) —
not a tunable trade-off — so the pre-committed "matched coverage" comparison does not
apply. The honest statement is the step itself:

> The naive policy's 21.2% false-upgrade rate is *entirely* "corroboration" that never
> actually reaches 2 effective independent votes. The φ-discount eliminates 100% of those
> false upgrades (21.2% → 0%) by refusing to count correlated routes as independent.

Naive threshold sweep (transparency — the coverage/risk curve):

| threshold | false-upgrade rate | coverage | risk |
|---|---|---|---|
| 1 | 21.43% | 100% | 21.4% |
| 2 | 21.16% | 99.7% | 21.2% |
| 3 | 19.84% | 97.9% | 20.3% |
| 4 | 14.81% | 89.4% | 16.6% |
| 5 | 10.85% | 80.4% | 13.5% |
| 6 | 6.08% | 70.6% | 8.6% |
| 7 | 3.97% | 60.6% | 6.6% |
| 8 | 1.06% | 48.4% | 2.2% |

Even at the naive policy's own strictest threshold (8 unanimous routes) its false-upgrade rate
(1.06%) is still strictly positive, while the φ-discount at threshold 2 already gives 0%
**(at 0% coverage)** — because the discount knows 8 routes ≈ 1.63 effective votes, below the
2-vote bar.

*Tie-break convention:* when two answers tie for the per-claim mode (e.g. a 4-vs-4 split),
`experiment_bc.policy()` resolves to the first-inserted value (`Counter.most_common(1)` insertion
order). At k=8 a tie requires ≥2 equal modes; the effect on the sweep is negligible.

## Deviations & caveats
- **kimi temperature=1** (provider rejects temperature=0) — disclosed in the prereg.
- **5 negative-oracle facts** (−273.15, −195.8, −1.46, −63, −4.92) are FIXED constants; they require
  the sign-aware parser (now Unicode-safe) and are kept.
- **Truncated reasoning answers** (`finish_reason == "length"`, 87 rows) are treated as unparseable
  and counted separately — see corrections item 8.
- **`results/*.json` (the 8 real models) is committed** so φ̄/n_eff/false-upgrade recompute from a
  fresh clone without live API keys. `corpus.json`, `stats.json`, `experiment_bc.json`, and the
  `.py` files are committed too.
