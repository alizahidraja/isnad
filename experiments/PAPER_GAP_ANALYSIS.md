## Paper Gap Analysis — What the Experiment Proves

### What the Paper Currently Has (§8)

The paper describes the corroboration (*mutābaʿāt*) mechanism conceptually:
independent chains reporting the same claim can upgrade trust via
information-theoretic error multiplication.  But §8 had no empirical
validation — the engine existed but had never fired on real data.

### What This Experiment Adds

| Claim | Evidence |
|---|---|
| Corroboration fires on real data | **603/603 (100%)** semantically-matched cross-source pairs |
| Independence detection works | 8/8 negative controls: madār (shared family), shared source, correlated chains all blocked |
| DAIF → HASAN upgrade is gated | Grade gate, count gate, cap — all verified |
| HASAN never reaches SAHIH | Cap tested with SAHIH-strength corroborators |
| Information-theoretic math calibrated | Effective weights range 1.5–10.5, scaled by chain quality |
| Cross-source semantic matching feasible | 662 pairs found (cosine ≥ 0.75) from 10,544 sentences |
| Reproducible | Single command: `python run.py` |

### What the Paper Still Doesn't Have (After This Experiment)

1. **Real LLM-generated claims:** All claims are extracted Wikipedia sentences.
   A production system would generate claims via LLMs — these claims may have
   different error characteristics (hallucinations, confabulations).

2. **Dynamic narrator grading:** Narrator grades are assigned statically.
   The jarḥ–taʿdīl loop (evidence → grade transition) is not exercised.
   The BayesianTransitionPolicy is tested in unit tests but not in the
   experiment.

3. **Full pipeline integration:** Chain grading → matn criticism →
   corroboration → decision matrix.  Only the corroboration step is tested.
   The decision matrix (4×2: chain_grade × content_verdict → action) is
   not exercised with real data.

4. **Cross-source data beyond Wikipedia:** Britannica requires JS rendering.
   Simple Wikipedia is genuinely independent but both are Wikimedia projects.
   ArXiv, textbooks (OpenStax), or news sources would add diversity.

5. **Statistical significance testing:** 603 pairs is solid but formal
   statistical tests (confidence intervals, effect sizes) would strengthen
   the paper.

6. **Failure mode analysis:** What happens when corroboration fires on
   a FALSE claim?  Both sources could be wrong in the same way (shared
   blind spot).  This is the madār problem at the content level.

7. **Human ground truth:** A sample of claims should be verified against
   authoritative references (textbooks, expert review) to confirm the
   claims are actually true — not just independently reported.

### What the Paper Could Have (Next Steps)

| Addition | Effort | Impact |
|---|---|---|
| Run with OpenStax physics corpus (already downloaded) | 1 day | Cross-source beyond Wikipedia |
| Test with real LLM-extracted claims (GPT-4, Claude) | 2 days | Production-relevant |
| Add formal statistical tests (CI, p-values) | 1 day | Academic rigor |
| Human validation of 100 claim pairs vs textbook ground truth | 2 days | Gold standard |
| Full pipeline: claims → grade → critic → corroborate → decide | 3 days | Complete system demo |
| Plot trust score distributions, grade transition Sankey diagrams | 1 day | Paper-quality visuals |
