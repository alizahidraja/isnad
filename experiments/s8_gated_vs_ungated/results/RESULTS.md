# §8 Validation Experiment — Results

**Date:** 2026-07-06
**Analysis Plan:** ANALYSIS_PLAN.md (preregistered before results)

## Primary Result: ISNAD-gated vs. Confidence-gated at B=10%

| Condition | Served-Error Rate (mean ± 95% CI) |
|---|---|
| ISNAD-gated | 0.1078 |
| Confidence-gated | 0.1493 |
| Difference (ISNAD − confidence) | -0.0415 ± 0.0566 |
| Significant? | ✗ Not significant |

**Conclusion:** The difference was not statistically significant. The §8 hypothesis is **inconclusive** on this corpus — a larger corpus or more seeds may be needed.

## All Conditions — Served-Error Rate vs. Budget

| Condition | B=2% | B=5% | B=10% | B=20% |
|---|---|---|---|---|
| ungated | 0.1622 | 0.1577 | 0.1482 | 0.1353 |
| confidence | 0.1619 | 0.1566 | 0.1493 | 0.1327 |
| isnad | 0.1597 | 0.1210 | 0.1078 | 0.1048 |
| isnad_no_corroboration | 0.1597 | 0.1210 | 0.1078 | 0.1048 |

## Review-Queue Precision

| Condition | B=10% Precision |
|---|---|
| ungated | 0.166 |
| confidence | 0.155 |
| isnad | 0.149 |

## Coverage (Fraction of Claims Served)

| Condition | B=10% Coverage |
|---|---|
| ungated | 1.000 |
| confidence | 1.000 |
| isnad | 0.133 |
| isnad_no_corroboration | 0.133 |

## Corroboration Effect (Ablation)

Coverage difference between ISNAD-gated with and without corroboration at B=10% isolates the mutābaʿāt rule's effect on trust recovery.

## Limitations

- Simulated-perfect human reviewer → review-precision is realistic-cost metric.
- Synthetic rule-based faults → real fault distributions may differ.
- Single corpus domain (undergraduate physics) → limited external validity.
- Single extraction model → different extractors may shift claim distributions.
- Pre-generated corpus chunks (not live PDF extraction) for reproducibility.
- Corpus size was below the ≥3000 claim target (see extract output).