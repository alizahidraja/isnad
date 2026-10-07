# §8 Validation Experiment — Final Honest Results

**Date:** 2026-07-07 (s8 experiment) | Updated 2026-08-26 (reproducibility + extraction fixes)
**Branch:** s8-scale (merged to main)
**Corpus (re-run 2026-10-02):** 4 books — OpenStax Vol 1–3 + Crowell — **17,021 claims**,
**11,918 eval claims/seed** × 10 seeds. This is the single corpus the Primary Result below
is computed on (v1's 22,307-span / 156,170-eval-claim figures are superseded).

> **Update (2026-07-09):** Corroboration is no longer untested.
> The semantic corroboration experiment (v2) validates `mutābaʿāt` on
> 603 semantically-matched cross-source claim pairs from dual Wikipedia
> corpora. See [`experiments/corroboration_v2/`](../corroboration_v2/README.md)
> for full results.  **The s8 serving-coverage experiment below is a separate,
> orthogonal test of the weakest-link quarantine + decision matrix.**

---

## Reproducibility update (2026-08-26, issues #92 + #94)

Two corrections to the original paper's §8:

1. **Extraction method (#94).** The corpus was described as "20,000 atomic
   claims extracted via deepseek-chat". In fact the extractor was a regex
   splitter that (a) rewrote every "X is Y" into "X equals Y" — garbling prose
   ("the glass is sitting" → "the glass equals sitting") and breaking formula
   matching against the content critic — and (b) passed multiple-choice answer
   prefixes, questions, and OCR fragments through as "claims". The extractor is
   now a **deterministic heuristic segmenter + filter** (`extract.py`) producing
   **sentence-level spans**, not LLM "atomic claims". This is the honest unit of
   analysis: the experiment validates the transmission-grading *mechanics*, not
   claim semantics.

2. **Transition policy (#92).** The §8.2 figures ("ingest@weak rejected in 49/50
   cells", "4,057 quarantined = 29%") were produced by the **pre-#9** threshold
   policy (the monotonic ratchet fixed in issue #9) and are not reproducible from
   the corrected code.

`calibrate.py` is pinned to the **post-#9** `ThresholdTransitionPolicy`, and the
registry snapshots are regenerated from the cleaned corpus. The honest, current
result (50 cells = 10 seeds × 5 domains):

| Narrator | Designed fault | Recovered grade (50 cells) |
|---|---|---|
| `source:*` (openstax + crowell) | 0% | RELIABLE 50/50 (seed, now honored — #90) |
| `pdf-scraper@1.2` | 1% | RELIABLE 50/50 (seed) |
| `ingest@good` | 2% | ACCEPTABLE 50/50 (seed) |
| `ingest@weak` | 15% | **WEAK 31/50, UNGRADED 9/50, ACCEPTABLE 7/50, REJECTED 3/50** |
| `pdf-scraper@0.9-legacy` | 18% | missed (0/50 — too rare to grade) |

With `ingest@weak` REJECTED in 3 of 50 cells, the quarantine count is
**3,588 of 119,180 eval claims (3.0%)**. The weakest-link quarantine *mechanism*
is unchanged and unit-tested.

Both corrections are tracked in the paper-v2 issue (#51).

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

## Primary Result (re-run 2026-10-02, B∈{2,5,10,20}%, 10 seeds, 11,918 eval claims/seed)

| Condition | Coverage | Served-error | Review precision |
|---|---|---|---|
| Ungated | 100% | 8.9% → 7.3% | ~9% (random) |
| Confidence-gated | 100% | 8.9% → 7.3% | ~8–9% |
| **ISNAD-gated** | **2–20% (review budget)** | **0.0%** | ~9% |
| ISNAD, no corroboration | 2–20% (review budget) | 0.0% | ~9% (identical) |

ISNAD's zero served-error is a **coverage artifact**: it quarantines ~3% (ingest@weak →
REJECT), holds ~80–97% for review (ḥasan × UNVERIFIABLE → REVIEW), and serves only the review
budget — so it serves essentially nothing as safe-to-serve, hence 0 errors. The review-precision
column does **not** show the chain cannot rank corruption: `run.py` assigns every REVIEW claim
priority 0, so the review queue never orders by chain grade, and corruption is injected
per-narrator (a WHO property by design). ISNAD's review precision (~9%) is statistically
indistinguishable from random (~9%) and from the corruption rate (~9.1%) — so this run does **not** test whether the chain ranks corruption (the review queue never orders by chain grade). That discrimination question is now measured separately in [`DISCRIMINATION.md`](DISCRIMINATION.md): **the chain grade does discriminate** — ḥasan 4.6% → ḍaʿīf 15.1% corruption, and chain-only serving halves served-error (4.2% vs 9.2% random at matched coverage). So the honest statement is not "the chain cannot rank corruption" but "the chain ranks WHO-driven corruption (per-narrator injection), and the flat-priority review harness simply does not exploit that ranking." Confidence-gating is no better than
random. Corroboration fires 0× (single-source corpus), so `isnad` == `isnad_no_corroboration`
exactly. See [`MATCHED_COVERAGE_FINDING.md`](MATCHED_COVERAGE_FINDING.md).

---

## What Gets Rejected — and Why

Rejections come from `ingest@weak` being REJECTED in the 3 of 50 cells where the
post-#9 policy drives it that far (3,588 claims, 3.0% of eval). The chain trace
when it fires:

```
Step 0: source:openstax           RELIABLE ✓     [→]
Step 1: pdf-scraper@1.2           RELIABLE ✓     [DESTRUCTIVE ▼]
Step 2: ingest@weak               REJECTED ✗✗    [GENERATIVE ▲]  ← BREAKS

Chain grade: DAIF_JIDDAN → QUARANTINE
```

> **Note:** the original "4,057 claims (29%)" figure required `ingest@weak` to
> be REJECTED in 49/50 cells, which was the pre-#9 ratchet — see the
> reproducibility update above.

Full chain trace: `results/rejected_claims_diagnostic.txt`

---

## Where Coverage Goes

> **Note:** the table below reports the *corrected* post-#9 numbers. The
> pre-#9 figures ("4,057 quarantined = 29%") are superseded — see the
> reproducibility update above.

| Fate | Count | % |
|---|---|---|
| Quarantined (DAIF_JIDDAN via ingest@weak, REJECTED in 3/50 cells) | 3,588 | 3.0% |
| Held for review, beyond budget | majority | ~80–97% (depends on B) |
| **Served (within review budget)** | **~2–20%** | **B** |

The large review-held share are HASAN and DAIF chains with UNVERIFIABLE content
verdicts. The framework requires human review (or a working content critic
that returns CONSISTENT) to serve them. With the deterministic stub critic on
real text, neither condition is met.

---

## Critic false-consistent measurement (#126, added 2026-08-27, corrected 2026-08-27)

To trust a content critic to unlock the coverage ceiling, its *dangerous* error —
a corrupted claim labelled CONSISTENT (which the matrix would SERVE) — must be
measured, not assumed. `critic_false_consistent.py` does this against the
injection manifest, splitting faults by the two-axis divide (#124):

| Fault class | n | LLM false-CONSISTENT | Meaning |
|---|---|---|---|
| **content** (meaning-changing) | 92 | **36 (39.1%)** | the critic's actual job |
| transmission (OCR char substitution) | 108 | 107 (99.1%) | same meaning — chain grader's job |
| mixed | 12 | 9 (75.0%) | — |

Per-fault-type (the honest detail):

| Fault | n | CONSISTENT | CONTRADICTION | UNVERIFIABLE |
|---|---|---|---|---|
| ocr_noise | 108 | 107 | 0 | 1 |
| **fabricated_numeric** | 79 | **33** | 32 | 14 |
| entity_swap | 10 | 1 | 7 | 2 |

**Honest reading:** on content corruption, the LLM critic (DeepSeek) fails to
catch **39%** (36/92) — and on fabricated numbers specifically it is roughly
50/50 (33 vs 32). The safety gate is **emphatically not cleared**: the critic
is not safe to unlock coverage, and §8.4's matched-coverage re-run stays open.
This is a citable negative result: even an LLM-tier critic does not reliably
detect meaning-changing corruption in this corpus.

**Correction note (important):** an earlier version of this measurement reported
15.4% by misclassifying `fabricated_numeric` as "transmission" noise. It is not —
"L3"→"L2.61" changes the claim. The corrected number is 39.1%.

Run: `python critic_false_consistent.py` (uses `best_available_critic()`;
`DEEPSEEK_API_KEY` set → LLM tier, `--offline` → TF-IDF).

---

## What Was Validated and What Wasn't

| Claim | Status | Evidence |
|---|---|---|
| Weakest link quarantines unreliable narrators | ✓ Yes | Chain grade discriminates: ḥasan 4.6% vs ḍaʿīf 15.1% corruption; 3,581 quarantined (14.7% precision) |
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
