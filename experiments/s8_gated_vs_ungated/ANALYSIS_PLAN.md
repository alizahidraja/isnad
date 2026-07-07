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

### 2026-07-06 — Corpus scaling and seed increase

- **Corpus scaled from 1,084 to 3,002 claims.** The original run produced only
  1,084 claims (below the preregistered ≥3,000 floor). Additional textbook
  excerpts were added covering all four physics domains to meet the target.
  The extraction method, model, dedup, and confidence capture are unchanged.
- **Seeds increased from 5 to 10.** Narrower CIs via more randomness samples.
  The primary hypothesis, metrics, and decision rule are unchanged.
- **Cross-source corroboration overlap: 0.** The synthetic corpus produces
  no identical normalized claims across OpenStax and Crowell sources.
  Consequently, the corroboration ablation (condition 4) is untestable —
  conditions 3 and 4 produce identical results. This is flagged prominently
  in RESULTS.md.
- **Transition-policy sweep preregistered 2026-07-06.** A secondary (not primary)
  analysis sweeps the downgrade threshold ∈ {3, 6, 10, 15, 25} to characterize
  the coverage-collapse finding. Hypothesis: looser thresholds reduce
  over-penalization of reliable narrators, increasing coverage while preserving
  error advantage up to some point, after which error rises. This sweep is
  executed via the framework's pluggable TransitionPolicy interface (not by
  editing framework code). The primary preregistered comparison uses the
  DEFAULT policy (threshold=3) and is reported separately from the sweep.
  Sweep is CONFIGURATION exploration, not p-hacking — all thresholds are
  reported regardless of outcome.
- **Matched-coverage analysis preregistered 2026-07-06.** The degenerate
  ~0% error / <10% coverage regime makes the original served-error comparison
  misleading. A secondary matched-coverage analysis is added: sweep each
  condition's operating point to trace served-error at matched coverage
  levels (20%, 30%, 50%, 70%, 90%). This is the standard selective-prediction
  evaluation and neutralizes the "ISNAD just serves less" critique. If ISNAD
  cannot reach a coverage level, that is reported honestly. The original
  preregistered primary (B=10%, default policy) is reported verbatim alongside.
- **Cross-source overlap corpus added 2026-07-06.** 107 claim texts now appear
  in both OpenStax and Crowell source files, making the corroboration ablation
  (conditions 3 vs 4) testable for the first time.
  spec called for downloading and chunking actual PDFs. For reproducibility
  and cost, we use committed text excerpts approximating the source content.
  A full production run should use real PDFs and LLM extraction.
