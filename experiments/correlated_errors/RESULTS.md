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
ISNAD's madār assumption (disjoint narrators ⇒ independent corroboration) is violated:
nominally-independent models carry far fewer effective independent votes than their
count. Same-family models are nearly identical in their errors; even cross-family,
three of four vendors correlate strongly.

## FINAL ~393-fact numbers — TODO (pending the full sweep)
- [ ] φ̄ (all pairs), same-family vs cross-family breakdown
- [ ] n_eff + cluster-bootstrap 95% CI
- [ ] per-model error rates + exclusions

## Experiment B/C — TODO (pending the full sweep)
- [ ] B (naive) vs C (φ-discounted) false-upgrade rate, coverage, risk
- [ ] Δfalse-upgrade at matched coverage

## Deviations & caveats
- **kimi temperature=1** (provider rejects temperature=0) — disclosed in the prereg.
- The 64-fact preliminary φ is **not** a stable estimate; the 393-fact corpus is the
  number the paper should cite.
- `results/*.json` is gitignored (reproducible); `corpus.json`, `stats.json`, and the
  `.py` files are committed.
