# Content-madār calibration — committed results (#54)

**Eval set:** 28 pairs (8 shared-error token-bearing, 4 shared-error token-less, 8 independent-agreement, 4 near-miss boundary, 4 independent-different) + 2 N-way · `eval_set_sha256=a3f92f863fe442d9…`

| Layer | Recall | Recall (token-bearing) | Recall (token-less) | FP (agreement) | FP (near-miss) |
|---|---|---|---|---|---|
| `shares_error_with` (raw, **measured**) | 0.667 | 1.000 | **0.000** | **0.750** | **1.000** |
| `detect_content_madar` (gated, **oracle — structural**) | 0.667 | — (structural) | — (structural) | — (structural) | — (structural) |

## Reading the numbers

- **Recall is no longer saturated at 1.0.** The token-bearing shared errors (8) are caught with recall 1.000; the token-less shared errors (4) — the same mistake reworded with no shared salient token — are caught with recall **0.000**. That is the honest recall gap: the fingerprint is a *surface-token* detector and cannot see a reworded error. Overall recall is 0.667 = 8/12.
- **FP (agreement)** remains the headline hazard: the bare fingerprint fires on 6/8 genuine independent-agreement pairs (0.750) — correct facts sharing a salient token.
- **FP (near-miss)** is a *newly measured defect*, not fixed here: the bare fingerprint fires on 4/4 near-miss boundary pairs (1.000) — one correct and one wrong claim sharing a subject token but differing in value (1687 vs 1689). The entity-set-equality rule fires *before* the numbers are compared, so identically-phrased near-misses collide. This is disclosed, not fixed (fixing the detector is a separate change).
- **N-way (3+ chain):** True of the shared-error N-way case(s) fire and 1 negative control(s) correctly do not fire — API-coverage verification of `detect_content_madar`'s any-match semantics (oracle-fed, structural).

- The **gated row is structural, not an empirical FP rate** (oracle-fed verdicts), so its FP/recall columns are `— (structural)`. The real end-to-end FP is `fcr_base × fcr_corr × raw_fire_rate`, measured in `experiments/critic_eval`, not here.

## Honest limits

Small pilot set. Headline FP-on-agreement is 6/8 with a wide Wilson CI at this n; the token-less recall gap and the near-miss FP are the newly measured, honest findings. The gated row is structural. Nothing here fixes the detector — it measures it. `src/isnad/core/content_madar.py` is unchanged by this harness.
