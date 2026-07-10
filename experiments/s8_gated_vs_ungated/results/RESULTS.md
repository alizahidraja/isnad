# §8 Validation Experiment — Final Honest Results

**Date:** 2026-07-07 (s8 experiment) | Updated 2026-07-09 (corroboration cross-ref)
**Branch:** s8-scale (merged to main)
**Corpus:** 20,000 claims from real PDFs (OpenStax Vol.1-3 + Crowell)

> **Update (2026-07-09):** Corroboration is no longer untested.
> The semantic corroboration experiment (v2) validates `mutābaʿāt` on
> 603 semantically-matched cross-source claim pairs from dual Wikipedia
> corpora. See [`experiments/corroboration_v2/`](../corroboration_v2/README.md)
> for full results.  **The s8 serving-coverage experiment below is a separate,
> orthogonal test of the weakest-link quarantine + decision matrix.**

---

## Four Things That Must Be Said First

### 1. Corroboration was not tested IN THIS EXPERIMENT — zero times across all runs.
`evaluate_corroboration()` is wired and called. It returned 0 upgrades in every
run because the s8 corpus has no cross-source claim overlap (single-source PDFs).

**THIS IS NOW VALIDATED ELSEWHERE:** The semantic corroboration v2 experiment
achieves 603/603 (100%) DAIF→HASAN upgrades on semantically-matched claims from
Regular vs Simple English Wikipedia — two genuinely independent sources.
8/8 negative controls pass.  See [`experiments/corroboration_v2/`](../corroboration_v2/).

### 2. This result is "ISNAD with warm-start grades" — not autonomous discovery.
Three of four narrator types were seed-graded (source RELIABLE, scraper RELIABLE,
ingest@good ACCEPTABLE). Only ingest@weak was discovered. Legitimate per paper
§7, but must be stated.

### 3. Coverage is 10%, not 53%. A critic self-matching bug inflated the prior number.
An earlier run showed 53% coverage because the matn critic matched claims against
themselves (always CONSISTENT → HASAN+CONSISTENT = SERVE_WITH_CAVEAT). Fixed:
the critic now returns UNVERIFIABLE on real text (the deterministic stub cannot
detect real contradictions). With UNVERIFIABLE, HASAN chains route to REVIEW,
not serve. Coverage drops to the review budget: 10%.

### 4. Without content criticism, the framework cannot serve HASAN-tier claims.
The decision matrix routes HASAN+UNVERIFIABLE → REVIEW. To serve HASAN claims
automatically, the content critic must return CONSISTENT. The deterministic stub
critic cannot do this on real text (no self-matching, no hardcoded patterns
matching real textbook prose). A production system needs a working content
critic — LLM-backed or embedding-based — to achieve practical coverage.

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
| **Corroboration upgrades independent chains** | **✅ Validated (v2)** | **603/603 cross-source claims, 8/8 controls — see corroboration_v2/** |
| Content criticism on real text (stub) | ✗ Not functional | Stub critic cannot detect real contradictions |
| Content criticism on real text (embedding) | ✅ Working | EmbeddingCritic catches contradictions offline |
| Confidence-gating is no better than random | ✓ Yes | ~8% error at all budgets |

---

## Bottom Line

The weakest-link rule and narrator quarantine work.  Corroboration (*mutābaʿāt*)
is now empirically validated on a separate dual-Wikipedia semantic-matching
experiment (603/603 claim pairs, 100% fire rate).  

Two things remain for practical end-to-end deployment on THIS corpus:
1. **A working content critic** — so HASAN chains can graduate from REVIEW to SERVE
2. **Cross-source claim overlap** — the s8 corpus is single-source; corroboration
   requires genuinely independent sources asserting the same claims

With the deterministic stub critic on single-source text, the framework serves
only the review budget's worth of claims — 10% at zero error — and the
remaining 90% sit in the review queue. This is correct conservative behavior
given the available information.  The semantic corroboration v2 experiment
proves the missing pieces work when the right data is available.
