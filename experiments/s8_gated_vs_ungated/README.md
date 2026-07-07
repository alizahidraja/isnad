# §8 Validation Experiment: Gated vs. Ungated Serving

Validates the ISNAD framework against the experiment specified in §8 of
"Grading the Narrators" (Raja, 2026, DOI: 10.5281/zenodo.21211291).

**Question:** At a fixed human-review budget, does rijāl-gated serving
reduce the served-error rate relative to ungated serving?

## Quickstart

```bash
cd experiments/s8_gated_vs_ungated
make s8-all          # Full pipeline (extract → inject → calibrate → run → analyze)
make s8-extract      # Just claim extraction
make s8-calibrate    # Just calibration (Phase 1)
make s8-run          # Just evaluation (Phase 2)
make s8-analyze      # Just analysis
```

## Pipeline Overview

```
corpus/chunks/ → extract.py → claims.json
                              ↓
                         inject.py → enriched_claims + ground_truth (per seed)
                              ↓
                         calibrate.py → registry snapshot + eval split (Phase 1)
                              ↓
                         run.py → verdicts per condition × budget × seed (Phase 2)
                              ↓
                         analyze.py → RESULTS.md + metrics
```

## Scientific Integrity

- **Leakage firewall:** `ground_truth.py` is NEVER imported by grading/gating code.
  Verified by `tests/test_firewall.py`.
- **Preregistration:** `ANALYSIS_PLAN.md` was committed before any results.
- **Honest reporting:** `results/RESULTS.md` reports whatever the numbers are.
- **Determinism:** All randomness seeded; LLM calls cached.

## Cost Estimate

- Extraction: ~3,000 claims ÷ ~10 claims/call × $0.0005/call ≈ $0.15
- Matn criticism (LLM): ~2,100 eval claims × $0.0005 ≈ $1.05 (per seed, if enabled)
- Default uses deterministic matn critic → $0 for matn.
- Total estimated: < $2 for full run with deterministic critic.

## Key Files

| File | Purpose |
|---|---|
| `ANALYSIS_PLAN.md` | Preregistered hypotheses, metrics, decision rule |
| `config.yaml` | All parameters (models, rates, budgets, seeds) |
| `corpus/` | Source texts, attribution, chunks |
| `extract.py` | Claim extraction from corpus |
| `narrators.py` | Narrator definitions and fault classes |
| `inject.py` | Fault injection and chain assignment |
| `ground_truth.py` | **FIREWALL** — Injection manifest |
| `calibrate.py` | Phase 1: jarḥ–taʿdīl calibration |
| `run.py` | Phase 2: gated vs. ungated evaluation |
| `analyze.py` | Metrics and RESULTS.md generation |
| `audit_sample.py` | Human audit CSV export |
| `results/RESULTS.md` | Final report |
