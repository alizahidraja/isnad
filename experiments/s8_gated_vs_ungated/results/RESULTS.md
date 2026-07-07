# §8 Validation Experiment — Final Honest Results

**Date:** 2026-07-07 | **Branch:** s8-scale
**Corpus:** 20,000 claims from real PDFs (OpenStax Vol.1-3 + Crowell)

---

## Four Things That Must Be Said First

### 1. Corroboration was never tested — zero times across all runs.
`evaluate_corroboration()` is wired and called. It returned 0 upgrades in every run. Gated on baseline chain grades above DAIF, which the cold-start never produces. **Status: EMPIRICALLY UNTESTED.**

### 2. This result is "ISNAD with warm-start grades" — not autonomous discovery.
Three of four narrator types were seed-graded (source RELIABLE, scraper RELIABLE, ingest@good ACCEPTABLE). Only ingest@weak was discovered. Legitimate per paper §7, but must be stated.

### 3. Coverage is 10%, not 53%. A critic self-matching bug inflated the prior number.
An earlier run showed 53% coverage because the matn critic matched claims against themselves (always CONSISTENT → HASAN+CONSISTENT = SERVE_WITH_CAVEAT). Fixed: the critic now returns UNVERIFIABLE on real text (the deterministic stub cannot detect real contradictions). With UNVERIFIABLE, HASAN chains route to REVIEW, not serve. Coverage drops to the review budget: 10%.

### 4. Without content criticism, the framework cannot serve HASAN-tier claims.
The decision matrix routes HASAN+UNVERIFIABLE → REVIEW. To serve HASAN claims automatically, the content critic must return CONSISTENT. The deterministic stub critic cannot do this on real text (no self-matching, no hardcoded patterns matching real textbook prose). A production system needs a working content critic — LLM-backed or embedding-based — to achieve practical coverage.

---

## Primary Result (preregistered, B=10%, 10 seeds, critic=UNVERIFIABLE)

| Condition | Error Rate | Coverage |
|---|---|---|
| Ungated | 8.2% | 100% |
| Confidence-gated | 8.1% | 100% |
| **ISNAD-gated** | **~0%** | **10.0%** |

ISNAD achieves near-zero error at the review-budget coverage ceiling (10%).
Confidence-gating is no better than random.

---

## What Gets Rejected — and Why

100% of rejections (4,057 claims, 29%) come from `ingest@weak` being REJECTED:

```
Step 0: source:openstax           RELIABLE ✓     [→]
Step 1: pdf-scraper@1.2           RELIABLE ✓     [DESTRUCTIVE ▼]
Step 2: ingest@weak               REJECTED ✗✗    [GENERATIVE ▲]  ← BREAKS

Chain grade: MAWDU → REJECT_AND_QUARANTINE_NARRATOR
```

Full chain trace: `results/rejected_claims_diagnostic.txt`

---

## Where Coverage Goes

| Fate | Count | % |
|---|---|---|
| Quarantined (MAWDU via ingest@weak) | 4,057 | 29% |
| Held for review, beyond budget | ~8,544 | 61% |
| **Served (within review budget)** | **~1,400** | **10%** |

The 61% held for review are HASAN and DAIF chains with UNVERIFIABLE content
verdicts. The framework requires human review (or a working content critic
that returns CONSISTENT) to serve them. With the deterministic stub critic on
real text, neither condition is met.

---

## What Was Validated and What Wasn't

| Claim | Status | Evidence |
|---|---|---|
| Weakest link quarantines unreliable narrators | ✓ Yes | 100% of ingest@weak claims rejected |
| jarḥ–taʿdīl discovers bad narrators | ✓ Partial | Found ingest@weak (15%); good narrators were seed-graded |
| Seed-grading enables practical grades | ✓ Yes | But coverage still limited by critic |
| Corroboration upgrades independent chains | ✗ Untested | Never fired |
| Content criticism on real text | ✗ Not functional | Stub critic cannot detect real contradictions |
| Confidence-gating is no better than random | ✓ Yes | ~8% error at all budgets |

---

## Bottom Line

The weakest-link rule and narrator quarantine work. But two critical pieces are
missing for practical deployment: a working content critic (so HASAN chains can
graduate from REVIEW to SERVE), and warm-enough baseline grades for corroboration
to activate. With the deterministic stub critic, the framework serves only the
review budget's worth of claims — 10% at zero error — and the remaining 90% sit
in the review queue. This is correct conservative behavior given the available
information, but it means the full ISNAD pipeline (chain grading + content
criticism + corroboration → practical coverage) has not been demonstrated
end-to-end on this corpus.
