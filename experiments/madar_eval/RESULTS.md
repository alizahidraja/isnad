# Content-madār calibration — committed results (#54)

**Eval set:** 20 pairs (8 shared-error, 8 independent-agreement, 4 independent-different) · `eval_set_sha256=556e838958c25250…`

| Layer | Recall | Precision | F1 | FP rate (all neg.) | FP rate (agreement — danger) |
|---|---|---|---|---|---|
| `shares_error_with` (raw fingerprint, **measured**) | 1.000 | 0.571 | 0.727 | 0.500 | **0.750** |
| `detect_content_madar` (gated, **oracle — structural**) | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |

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
  `critic_false_contradiction_rate × raw_fire_rate` — the chance the critic wrongly
  calls an agreement a contradiction, times the ~0.75 chance the fingerprint then
  collides. The first factor is measured in `experiments/critic_eval`
  (`false_contradiction_rate`), not here. This harness does not measure it; it
  assumes a perfect critic. The honest claim is narrow: **the bare fingerprint is
  hazardous (measured), and gating on a prior CONTRADICTION verdict is what keeps
  it away from correct agreement (structural).**

## What this measures — and what it does not

This calibrates the **detectable** half of content-level madār: claims whose
wrongness the corpus can verify. It says nothing about the *undetectable* half —
two independent sources repeating the same received error on a claim the corpus
cannot check. That case is undecidable by construction (there is no wrongness
oracle to turn *same content* into *same error*), and #54 discloses it as a
permanent limit, not a gap to close. See `src/isnad/core/content_madar.py`.

## Raw-fingerprint misfires (why the gate matters)

On the raw layer, 6 negative pair(s) fired — 6 on independent *agreement*. Each is a
correct, independent restatement that shares a salient token (a number, name,
or date). These are exactly the collisions the corpus gate is there to stop:
the fingerprint alone cannot tell *same correct fact* from *same mistake*.
