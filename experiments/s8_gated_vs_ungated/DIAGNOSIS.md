# DIAGNOSIS.md — Starting State Before Fixes

**Date:** 2026-07-06 | **Branch:** s8-scale

---

## Problem 1: Claims are synthetic/fabricated, not from real PDFs

10 randomly sampled claims:

| claim_id | source | text |
|---|---|---|
| b6f2f4d2d2dd | crowell | "The torque on a magnetic dipole in a magnetic field is τ = μB sin θ." |
| 229243778c97 | crowell | "The root-mean-square speed is v_rms = √(3k_B T/m)." |
| e8333f1aefba | crowell | "Wave speed depends on medium properties, not amplitude or frequency..." |
| f8bd7b651ed8 | openstax | "r and angular quantities for a point at d equals tance r from the axis:" ← GARBLED |
| 1470fcc60cbe | crowell | "For Pyrex glass α ≈ 3×10⁻⁶ K⁻¹ (thermal shock resistant)." |
| b96c602f4051 | crowell | "green), GaN (3.4 eV, UV/blue)." ← FRAGMENT |
| 8ddd8ed61e03 | crowell | "RF voltage accelerates at each gap crossing." |
| aeaa99d4a25b | crowell | "Torque equals the rotational analog of force" |
| 15975e3b5b54 | crowell | "Superposition of potentials:" ← INCOMPLETE SENTENCE |
| 8aed45ae1c96 | crowell | "This form equals more general because it handles variable-mass systems..." ← BROKEN ENGLISH |

**Verdict:** These are NOT from real PDF text. Multiple claims are garbled
sentence fragments from aggressive regex splitting. No verbatim textbook prose
with equation numbers, section references, or figure captions. Sources are
pre-generated text, not actual PDF extraction.

Source distribution: crowell 3168, openstax 623 — wildly imbalanced.

---

## Problem 2: Corroboration is not wired in the evaluation loop

`run.py` line 179: `corroboration_support=False  # per-claim, not cross-chain`

The `evaluate_corroboration()` function from `isnad.core.corroboration` is NEVER
called in the evaluation loop. Conditions 3 (ISNAD) and 4 (ISNAD no corrob.)
produce IDENTICAL results across all 10 seeds:

```
s1_isnad_b10                     error=0.0213  coverage=0.0708
s1_isnad_no_corroboration_b10    error=0.0213  coverage=0.0708  ← IDENTICAL
s2_isnad_b10                     error=0.0086  coverage=0.0873
s2_isnad_no_corroboration_b10    error=0.0086  coverage=0.0873  ← IDENTICAL
... (all 10 seeds identical)
```

**Verdict:** The 107 cross-source overlaps in the corpus are unused. The
corroboration ablation cannot test anything until `evaluate_corroboration()`
is called in run.py's ISNAD condition.

---

## Problem 3: Degenerate metric regime — error ≈ 0%, coverage < 10%

The near-zero error is an artifact of near-zero coverage. The system only
serves ~5-10% of claims (the ultra-safe ones), so error is trivially low.
This applies across ALL transition-policy thresholds.

```
Default policy at B=10%:
  ISNAD error: 0.0111  coverage: 0.079
  Confidence:  0.1460  coverage: 1.000
```

The experiment needs MATCHED-COVERAGE comparison — at equal coverage, does
ISNAD serve fewer errors? This requires sweeping the operating point to trace
served-error at 30%, 50%, 70%, 90% coverage for each condition.

**Verdict:** The current comparison is a degenerate tradeoff — error goes to
zero because coverage goes to zero. Standard selective-prediction evaluation
requires matched-coverage comparison.
