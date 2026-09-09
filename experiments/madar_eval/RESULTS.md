# Content-madār calibration — committed results (#54)

**Eval set:** 20 pairs (8 shared-error, 8 independent-agreement, 4 independent-different) · `eval_set_sha256=c2b9872ba7fa6b03…`

| Layer | Recall | Precision | F1 | FP rate (all neg.) | FP rate (agreement — danger) |
|---|---|---|---|---|---|
| `shares_error_with` (raw fingerprint, **measured**) | 1.000 | 0.571 | 0.727 | 0.500 | **0.750** |
| `detect_content_madar` (gated, **oracle — structural**) | 1.000 | — (structural) | — (structural) | — (structural) | — (structural) |

## Reading the numbers

- The **raw `shares_error_with` row is the measurement.** Its **FP rate
  (agreement)** is the headline: how often the bare fingerprint fires on two
  *independent, correct* witnesses of the same fact — i.e. how often it would
  discount the exact corroboration corroboration exists to reward. That is the
  fingerprint's *intrinsic* hazard, and it is why the fingerprint is never used
  bare — only behind the corpus gate.
- **Recall** — of the pairs that truly echo the same specific mistake, how many
  the fingerprint catches.
- The **gated row is structural, not an empirical FP rate.** `detect_content_madar`
  only fingerprints a claim already flagged CONTRADICTION; this harness feeds the
  verdict *from the ground-truth label*, so on every independent-agreement pair the
  gate short-circuits before the fingerprint runs and FP is 0 **by construction of
  that oracle** — not because the detector was validated. Break `shares_error_with`
  to fire on everything and this row still reads 0.
- The gate's *real* false-positive contribution in production is
  approximately `fcr_base × fcr_corr × raw_fire_rate` — `detect_content_madar`
  fires only when *both* the base AND the corroborating claim are (mis)flagged
  CONTRADICTION, so *two* independent false-contradiction draws must line up, times
  the ~0.75 chance the fingerprint then collides. Each `false_contradiction_rate`
  factor is measured in `experiments/critic_eval`, not here. This harness does not
  measure the end-to-end rate; it assumes a perfect critic (both factors = 0). The
  gated **recall** of 1.0 is oracle-inflated the same way the FP is — it reflects the
  fed labels, not measured detector recall. The honest claim is narrow: **the bare
  fingerprint is hazardous (measured), and gating on a prior CONTRADICTION verdict
  keeps it away from correct agreement (structural).**

## What this measures — and what it does not

This **measures the raw-fingerprint hazard** (its false-positive rate on independent
agreement) and **demonstrates the gate short-circuit** — it does not measure the
shipped (gated) detector's end-to-end false-positive rate as a single number (that
needs the two `false_contradiction_rate` factors above; see the follow-up issue). It
also says nothing about the *undetectable* half of content-level madār — two
independent sources repeating the same received error on a claim the corpus cannot
check. That case is undecidable by construction (there is no wrongness oracle to turn
*same content* into *same error*), and #54 discloses it as a permanent limit, not a
gap to close. See `src/isnad/core/content_madar.py`.

## Sample size

Small pilot set. The headline FP-on-agreement is **6/8 = 0.750** (Wilson 95% CI
≈ 0.41–0.93); raw recall is **8/8 = 1.000** (saturated). Treat these as a pilot
signal, not a tight estimate — the direction (the bare fingerprint is hazardous) is
robust; the exact rate is not pinned by 8 cases.

## Raw-fingerprint misfires (why the gate matters)

On the raw layer, 6 negative pair(s) fired — 6 on independent *agreement*. Each is a
correct, independent restatement that shares a salient token (a number, name,
or date). These are exactly the collisions the corpus gate is there to stop:
the fingerprint alone cannot tell *same correct fact* from *same mistake*.
