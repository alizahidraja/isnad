# §8 Validation Experiment: Gated vs. Ungated Serving

Validates the ISNAD framework against the experiment specified in §8 of
"Grading the Narrators" (Raja, 2026, DOI: 10.5281/zenodo.21211290).

**Question:** At a fixed human-review budget, does rijāl-gated serving
reduce the served-error rate relative to ungated serving?

## Quickstart

### Full Pipeline (downloads 500MB PDFs)

```bash
python corpus/fetch.py          # 1. Download real PDFs
python extract.py               # 2. Extract atomic claims
python inject.py                # 3. Inject faults + assign chains
python calibrate.py             # 4. Phase 1: jarḥ–taʿdīl calibration
python run.py                   # 5. Phase 2: evaluate 4 conditions
python analyze.py               # 6. Metrics + RESULTS.md
```

### Self-Contained Runner (no PDFs, no downloads)

Runs the full ISNAD pipeline on pre-extracted claims (Bayesian grading +
EmbeddingCritic content criticism + corroboration). The 17,021-claim four-book corpus
(`results/claims.json`) is **not committed** — generate it with the full
pipeline above, or fetch it from Zenodo 10.5281/zenodo.21216873. Falls back
to TF-IDF critic when no LLM API key is set.

```bash
python run_experiment.py                     # EmbeddingCritic (TF-IDF) fallback
DEEPSEEK_API_KEY=sk-... python run_experiment.py  # DeepSeek LLM critic
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
│  BayesianTransitionPolicy: Beta-distribution per narrator×domain    │
│  Prior: Beta(1,1) → UNGRADED. Evidence updates posterior.           │
│  Grade = posterior mean mapped to ordinal tier.                      │
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
│                    DECISION MATRIX (5×3 router)                      │
│                                                                      │
│              CONSISTENT            CONTRADICTION                     │
│  ─────────── ────────────────────  ───────────────────────────────── │
│  SAHIH       SERVE (cache)        REVIEW (contradiction (taʿāruḍ) — highest value)    │
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
| 1 | **Ungated** | Serve everything; random review |
| 2 | **Confidence-gated** | Route lowest-confidence claims to review |
| 3 | **ISNAD-gated** | Full framework: chain grading → content criticism → decision matrix |
| 4 | **ISNAD, no corroboration** | Ablation: mutābaʿāt disabled |

---

## Superseded v1 self-contained runner + headline numbers

These numbers predate the 2026-10-02 four-book re-run and the mapping-v2 grade split.
They used the old corpus and the conflated rejected-narrator->mawdu label (MAWDU 67% is the
pre-v2 conflation; under mapping v2 that tier is now daif-jiddan). See
[results/RESULTS.md](results/RESULTS.md) for the current 4-book, 5-grade numbers
(ungated 8.9%->7.3%, confidence 8.9%->7.3%, ISNAD-gated 0.0% served-error as a coverage artifact).
Confidence-gating is no better than random. The weakest-link quarantine
mechanism is what does the work; the binding constraint is the content critic
(see RESULTS.md §3–§4 for the honest negative: with a deterministic critic,
coverage is capped at the review budget).

---

## Key Findings

1. **Bayesian policy works:** Continuous Beta posterior replaces hardcoded thresholds. Narrator grades progress UNGRADED→WEAK→ACCEPTABLE→RELIABLE with sustained evidence, fall back with adverse evidence.

2. **Content criticism works offline:** EmbeddingCritic (TF-IDF) catches negation, opposite words, and numeric divergence without any API key or model download. 4.2% contradiction detection rate on corrupted claims.

3. **Corroboration engine is wired:** Two independent chains for the same claim correctly trigger upgrade (DAIF→HASAN). Madār detection catches correlated chains (same model family → blocked).

4. **Cold-start ceiling:** Coverage is capped at <10%. The jarḥ–taʿdīl loop cannot distinguish reliable from unreliable narrators without enough audited claims.

5. **Confidence-gating is useless:** Self-confidence scores have near-zero correlation with claim defects.

## File Map

| File | Purpose |
|---|---|
| `run_experiment.py` | **Self-contained runner** — Bayesian + EmbeddingCritic + Corroboration |
| `corpus/fetch.py` | Download real PDFs, extract text, chunk |
| `extract.py` | Atomic claim extraction from chunks |
| `narrators.py` | Narrator definitions and fault classes |
| `inject.py` | Fault injection and chain assignment |
| `ground_truth.py` | **FIREWALL** — Injection manifest |
| `calibrate.py` | Phase 1: jarḥ–taʿdīl calibration |
| `run.py` | Phase 2: gated vs. ungated evaluation |
| `analyze.py` | Metrics and RESULTS.md generation |
| `risk_coverage.py` | Risk–coverage curves |
| `sweep_policy.py` | Configurable TransitionPolicy |
| `sweep_run.py` | Transition-policy sweep |
| `audit_sample.py` | Human audit CSV export |
| `archive/` | Diagnostic scripts (pre-restructure debugging) |
| `results/RESULTS.md` | Complete honest report |
| `results/claims.json` | 17,021 pre-extracted claims |
| `results/s8_bayesian_corroboration.json` | Self-contained runner output |
