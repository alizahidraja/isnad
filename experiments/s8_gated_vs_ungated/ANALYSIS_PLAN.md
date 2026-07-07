# Analysis Plan — §8 Gated vs. Ungated Validation Experiment

**Preregistered:** 2026-07-06  
**Paper:** "Grading the Narrators" (Raja, 2026, DOI: 10.5281/zenodo.21211291)  
**Status:** Committed before any results exist.

---

## 1. Research question

At a fixed human-review budget, does rijāl-gated serving reduce the served-error rate relative to ungated serving?

Primary comparator: ISNAD-gated vs. confidence-gated (current-practice baseline using self-assessment scores).

## 2. Hypotheses

- **H₁ (primary):** ISNAD-gated serving yields a lower served-error rate than confidence-gated serving at B = 10% review budget.
- **H₂ (corroboration):** Disabling corroboration (mutābaʿāt) reduces coverage without improving error rate, demonstrating that the corroboration rule recovers trustable claims that would otherwise require human review.
- **H₃ (risk–coverage):** ISNAD-gated serving achieves a better risk–coverage trade-off (lower AURC) than confidence-gated serving.

## 3. Experimental design

### 3.1 Corpus & claims
- Sources: OpenStax University Physics Vols. 1–3 (CC BY 4.0) + Crowell *Light and Matter* (CC BY-SA).
- Atomic claim extraction via LLM (deepseek-chat), ≥ 3,000 claims after dedup.
- Claims normalized; duplicates across sources linked as corroborating chains.

### 3.2 Narrator pipeline
- Each claim assigned one scraper variant (`pdf-scraper@1.2` or `pdf-scraper@0.9-legacy`) and one ingest variant (`ingest@good` or `ingest@weak`) uniformly at random.
- Faults: rule-based, deterministic per seed, per the rates in config.yaml.
- ~5% chains marked incomplete (missing trace link).
- Ground truth (which claims were corrupted) recorded in `ground_truth.py` — NEVER imported by grading/gating code.

### 3.3 Calibration (30% split)
- jarḥ–taʿdīl loop via the isnad package's real TransitionPolicy.
- 40 audited claims per (narrator, domain) from calibration split.
- Registry grades earned from evidence; NOT assigned from injection manifest.
- Domain tags: mechanics, electromagnetism, optics-waves, modern-quantum.
- Registry snapshot committed.

### 3.4 Evaluation (70% split)
Four serving conditions, all at the SAME budgets B ∈ {2%, 5%, 10%, 20%}:
1. **Ungated + random review:** Serve all claims; spend budget on uniform-random claims.
2. **Confidence-gated:** Route B lowest self-confidence claims to review; serve rest.
3. **ISNAD-gated:** Full framework: chain grading → matn criticism → decision matrix → prioritized review queue consumption (ʿilal first, then ḥasan×contradiction, etc.). Claims beyond budget not served.
4. **ISNAD-gated, no corroboration:** Same as 3 with mutābaʿāt disabled (ablation).

5 random seeds for narrator assignment + injection. Matn criticism: deterministic critic.

### 3.5 Reviewer simulation
Simulated perfect reviewer: reviewed claims get correct verdict from ground truth. Defective → blocked/corrected (counted as not-served-error). Clean → served. Review-queue precision is therefore the realistic-cost metric.

## 4. Metrics

### Primary metric
- **Served-error rate** at B = 10%: ISNAD-gated vs. confidence-gated.

### Secondary metrics
- Served-error rate for all conditions at all B.
- **Review-queue precision:** fraction of reviewed items actually defective.
- **Coverage:** fraction of eval claims served.
- **Risk–coverage curves:** AURC per condition.
- **Corroboration effect:** coverage delta between conditions 3 and 4 at fixed error rate.
- **Completeness-path behavior:** fraction of incomplete-chain claims correctly routed.

## 5. Statistical procedure

- All numbers: mean ± 95% CI over 5 seeds.
- Primary comparison: paired bootstrap CI on the difference (ISNAD − confidence) at B=10%.
- Also report McNemar's test on paired binary outcomes (served-error yes/no per claim).
- CI overlap check on served-error bars.

## 6. Decision rule

ISNAD is **validated on this corpus** if:
- ISNAD-gated served-error rate < confidence-gated at B=10%, AND
- 95% bootstrap CI on the difference does not include zero.

A null result (no significant difference) or negative result (ISNAD worse) is reported with equal prominence.

## 7. Interpretive constraints

- The reviewer is simulated-perfect → review-queue precision is the realistic metric; lower-than-1.0 precision erodes real-world benefit.
- Faults are synthetic rule-based corruptions → real fault distributions may differ.
- Single corpus domain (undergraduate physics) limits external validity.
- Single extraction model (deepseek-chat) — different extractors may produce different claim distributions.

## 8. Deviations

*None yet — this plan is preregistered before any results exist.*
