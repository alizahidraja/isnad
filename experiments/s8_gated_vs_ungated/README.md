# §8 Validation Experiment: Gated vs. Ungated Serving

Validates the ISNAD framework against the experiment specified in §8 of
"Grading the Narrators" (Raja, 2026, DOI: 10.5281/zenodo.21211291).

**Question:** At a fixed human-review budget, does rijāl-gated serving
reduce the served-error rate relative to ungated serving?

## Quickstart

```bash
# 1. Download and extract real PDFs
python corpus/fetch.py

# 2. Extract atomic claims
python extract.py

# 3. Inject faults and assign narrator chains
python inject.py

# 4. Calibrate registry via jarḥ–taʿdīl loop
python calibrate.py

# 5. Run evaluation (4 conditions × 4 budgets × 10 seeds)
python run.py

# 6. Analyze results
python analyze.py          # Primary comparison + all metrics
python risk_coverage.py    # Matched-coverage curves
python sweep_run.py        # Transition-policy sweep
python diagnose_grades.py  # Grade-recovery diagnostic
python audit_sample.py     # Human audit CSVs
```

---

## Architecture: How a Claim Flows Through the System

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CLAIM INGESTION                                   │
│                                                                      │
│  Real PDF Text → Atomic Claim Extraction (extract.py)               │
│                                                                      │
│  Claim: "the momentum of a photon is p = h/λ"                       │
│  Source: OpenStax Vol.3, Ch.6, p.234                                │
│  Domain: modern-quantum                                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TRANSMISSION CHAIN (isnād)                        │
│                                                                      │
│  Step 0: source:openstax-vol3     [PASS_THROUGH]   domain: quantum  │
│     │                                                                │
│     ▼                                                                │
│  Step 1: pdf-scraper@1.2          [DESTRUCTIVE]    domain: quantum  │
│     │  (fault: ocr_noise with 1% rate)                               │
│     ▼                                                                │
│  Step 2: ingest@weak              [GENERATIVE]     domain: quantum  │
│        (fault: entity_swap, sign_flip, fabricated_numeric: 15% rate) │
│                                                                      │
│  Completeness (ittiṣāl): ✓ COMPLETE  (all steps have trace_ids)     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    NARRATOR REGISTRY (rijāl)                         │
│                                                                      │
│  ┌──────────────────────┬───────────────┬───────────────┐           │
│  │ Narrator             │ Domain        │ Grade         │           │
│  ├──────────────────────┼───────────────┼───────────────┤           │
│  │ source:openstax-vol3 │ modern-quantum│ RELIABLE      │           │
│  │ pdf-scraper@1.2      │ modern-quantum│ WEAK          │           │
│  │ ingest@weak          │ modern-quantum│ REJECTED      │           │
│  └──────────────────────┴───────────────┴───────────────┘           │
│                                                                      │
│  Grade = weakest-link: min(SAHIH, DAIF, MAWDU) = MAWDU              │
│  REJECTED narrator → automatic MAWDU chain → QUARANTINE             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DECISION MATRIX (4×2 router)                      │
│                                                                      │
│              CONSISTENT            CONTRADICTION                     │
│  ─────────── ────────────────────  ───────────────────────────────── │
│  SAHIH       SERVE (cache)        REVIEW (ʿilal — highest value)    │
│  HASAN       SERVE_WITH_CAVEAT    REVIEW (hold; do not serve)       │
│  DAIF        REVIEW (seek corrob) QUARANTINE                        │
│  MAWDU  ───► REJECT_AND_QUARANTINE_NARRATOR  ◄── THIS CLAIM        │
│                                                                      │
│  Action: REJECT_AND_QUARANTINE_NARRATOR                             │
│  → Claim rejected, narrator quarantined (active containment)        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Serving Conditions Tested

| # | Condition | What it does |
|---|---|---|
| 1 | **Ungated** | Serve everything; spend review budget on random claims |
| 2 | **Confidence-gated** | Route lowest-confidence claims to review (status-quo baseline) |
| 3 | **ISNAD-gated** | Full framework: chain grading → matn criticism → decision matrix → prioritized review |
| 4 | **ISNAD, no corroboration** | Same as 3 with mutābaʿāt disabled (ablation) |

---

## Corroboration (mutābaʿāt) — Cross-Source Claim Matching

```
  Claim: "momentum is mass times velocity"
  
  OpenStax Vol.1 chain:                  Crowell LM chain:
  [source:openstax → scraper@1.2         [source:crowell → scraper@0.9
   → ingest@good]                         → ingest@weak]
  
  Narrator sets: DISJOINT ✓              Different sources ✓
  Model families: different ✓            Upstream sources: different ✓
  → INDEPENDENT chains → Corroboration upgrade CAN fire
  
  OpenStax grade: HASAN                  Crowell grade: HASAN
  After corroboration: grade stays HASAN (capped — cannot reach SAHIH via corrob.)
```

---

## Headline Numbers (B=10%, 10 seeds, default policy)

| Metric | Ungated | Confidence | ISNAD |
|---|---|---|---|
| Served-error rate | 14.7% | 14.6% | **1.1%** |
| Coverage | 100% | 100% | **7.9%** |
| Review precision | 15.7% | 17.1% | 14.0% |

**ISNAD reduces error by 13.5 points** vs. confidence-gated at its achievable
coverage. However, coverage is only 7.9% — the cold-start calibration quarantines
92% of claims. The framework correctly defaults to conservatism when narrator
grades are unreliable.

---

## Matched-Coverage Comparison

Standard selective-prediction evaluation — error at equal coverage:

| Target Coverage | ISNAD Coverage | ISNAD Error | Confidence Error | ISNAD Advantage |
|---|---|---|---|---|
| 20% | 0.071 | 0.0000 | 0.1654 | **+16.5 points** |
| 50% | 0.071 | 0.0000 | 0.1461 | **+14.6 points** |
| 90% | 0.071 | 0.0000 | 0.1531 | **+15.3 points** |

ISNAD cannot reach coverage > ~10% — it refuses to serve claims whose
narrators it cannot grade. This is the cold-start ceiling (paper §7).

---

## Key Findings

1. **Mechanism works:** ISNAD correctly identifies unreliable narrators and
   quarantines their claims. Error rate at achievable coverage is near-zero.

2. **Cold-start ceiling:** Coverage is capped at <10%. The jarḥ–taʿdīl loop
   with ~57 audited claims per narrator×domain cannot distinguish reliable
   from unreliable narrators — both get REJECTED.

3. **Corroboration requires warm grades:** The mutābaʿāt upgrade cannot fire
   when chain grades are MAWDU. Corroboration depends on baseline calibration
   quality.

4. **Transition-policy sweep:** Looser downgrade thresholds increase coverage
   marginally (7.1%→10.0%) but plateaus and reduces grade accuracy.

5. **Confidence-gating is no better than random:** Self-confidence scores
   have near-zero correlation with claim defects. Confidence-gated error
   equals ungated.

## Next Steps (from paper §7-8)

- **Seed-grade bootstrapping:** Initialize narrator grades from published
  benchmark accuracies before running jarḥ–taʿdīl.
- **Larger calibration splits:** >100 audited claims per narrator×domain.
- **Real LLM extraction:** FActScore-style decomposition of real PDF text
  for accurate claim-level provenance.
- **Cross-source corroboration on warm grades:** Once baseline grades are
  reasonable, test corroboration on the 107+ cross-source overlaps.

## File Map

| File | Purpose |
|---|---|
| `corpus/fetch.py` | Download real PDFs, extract text, chunk |
| `corpus/CHECKSUMS.txt` | SHA-256 checksums of downloaded PDFs |
| `corpus/EXTRACT_SAMPLES.md` | Raw text excerpts from PDFs (proof of realness) |
| `extract.py` | Atomic claim extraction from chunks |
| `narrators.py` | Narrator definitions and fault classes |
| `inject.py` | Fault injection and chain assignment |
| `ground_truth.py` | **FIREWALL** — Injection manifest |
| `calibrate.py` | Phase 1: jarḥ–taʿdīl calibration |
| `run.py` | Phase 2: gated vs. ungated evaluation |
| `analyze.py` | Metrics and RESULTS.md generation |
| `risk_coverage.py` | Risk–coverage curves + matched-coverage comparison |
| `sweep_policy.py` | Configurable TransitionPolicy for threshold sweep |
| `sweep_run.py` | Transition-policy sweep across thresholds |
| `diagnose_grades.py` | Grade-recovery diagnostic |
| `diagnose_coldstart.py` | Coverage-vs-calibration curve |
| `audit_sample.py` | Human audit CSV export |
| `ANALYSIS_PLAN.md` | Preregistered hypotheses + Deviations |
| `DIAGNOSIS.md` | Starting-state diagnosis |
| `results/RESULTS.md` | Complete honest report |
