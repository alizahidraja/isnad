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
- Primary endpoint: Δfalse-upgrade at **matched coverage**.

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
found to be corrupted by several bugs, all now fixed. The corrected numbers are **PENDING a re-run**
on the 386-fact corpus; the qualitative finding survives.

1. **Sign parser (BLOCKER)** — the runner's number regex dropped leading minus signs, so every
   negative-oracle fact (absolute zero −273.15, Sirius −1.46, Venus −4.92, liquid-nitrogen −195.8,
   Mars −63) was spuriously scored wrong for ALL models, inflating φ̄. Fixed: regex accepts `[+-]?`.
2. **Kish strength formula (BLOCKER)** — `1 + (m−1)·n_eff/k` over-credited unanimity by ~2.3×.
   Fixed: `strength(m) = m/(1+(m−1)φ̄)`, which equals `n_eff` at m=k.
3. **Matched-coverage endpoint (BLOCKER)** — the −65% compared naive@100% coverage vs
   discounted@68% coverage, not the pre-registered matched coverage. Fixed: `matched_coverage_compare()`.
4. **Oracle fixes** — neutron half-life→mean lifetime (14.6), standard gravity 9.80665, Pluto 1.303,
   Sun diameter 1,391,400, Venus −4.92, France (metropolitan) 66.4M. Dropped Milky Way star count,
   ISS altitude, Pleiades count, Dead Sea ×2, Mariana, Etna (no fixed oracle). 393 → **386 facts**.
5. **Exclusion logic** — the 7 free-tier models were never re-run against this corpus (their result
   files carried foreign `md_eXX`/`md_hXX` ids). They are now excluded by the coverage rule
   (<90% coverage), never "100% parse-failure"; their stale files are deleted.

## Corrected result — 386-fact corpus (PENDING re-run)

**φ̄ = ████ · n_eff = ████ · 95% CI [███, ███]** — filled by the re-run.

*(Pre-correction, for reference only: φ̄=0.5667, n_eff=1.611, CI [1.515, 1.724].)*

### Per-model error rates — PENDING re-run

### Kim same-wrong table — PENDING re-run

## Experiment B/C — matched-coverage endpoint

Primary endpoint (pre-registered): Δfalse-upgrade at **matched coverage**. The discounted policy's
coverage at threshold 2 defines the target coverage; the naive policy is held to the same coverage,
and the two false-upgrade rates are compared at that matched coverage.

**PENDING re-run.** The pre-correction (unmatched) numbers were naive 23.4% @ 100% coverage vs
discounted 8.1% @ 68.4% coverage. Because naive's false-upgrade rate at a *reduced* coverage is
higher than its full-coverage average, the −65% headline is an upper bound; the matched-coverage
number is the primary endpoint and will be smaller.

## Deviations & caveats
- **kimi temperature=1** (provider rejects temperature=0) — disclosed in the prereg.
- **5 negative-oracle facts** (−273.15, −195.8, −1.46, −63, −4.92) are FIXED constants; they require
  the sign-aware parser and are kept.
- **`results/*.json` (the 8 real models) is committed** so φ̄/n_eff/false-upgrade recompute from a
  fresh clone without live API keys. `corpus.json`, `stats.json`, `experiment_bc.json`, and the
  `.py` files are committed too.
