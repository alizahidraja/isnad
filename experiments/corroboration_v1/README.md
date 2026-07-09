# Corroboration Experiment v1

## Research Question
Does independent corroboration (*mutābaʿāt*) meaningfully upgrade trust in the Isnād–Rijāl framework?

## Hypothesis
Claims supported by two independent transmission chains (different source narrators)
receive higher chain grades than those supported by a single chain.

## Experiment Design

### Phase A: Synthetic Matching
- Same exact claim text from two different "sources" (Wikipedia vs Britannica)
- Chains: `source:wikipedia → ingest:direct → model:gpt4` vs `source:britannica → ingest:direct → model:gpt4`
- Narrator sets are fully disjoint → independence guaranteed
- **Purpose**: Validate that the CorroborationEngine fires when all preconditions are met

### Phase B: Cross-Topic Matching
- Real near-duplicate claims found across Wikipedia topic boundaries
- e.g., "Quantum mechanics" and "Wave-particle duality" share factual overlap
- Uses TF-IDF Jaccard similarity to find candidate pairs
- **Purpose**: Test on real, non-synthetic overlaps

### Narrator Grades
| Narrator | Grade |
|---|---|
| `source:wikipedia` | ACCEPTABLE |
| `source:britannica` | ACCEPTABLE |
| `ingest:direct` | RELIABLE |
| `ingest:ocr` | WEAK |
| `model:gpt4` | RELIABLE |

### CorroborationEngine Configuration
- `min_independent_chains`: 2
- `corroboration_cap`: HASAN (cannot reach SAHIH via corroboration alone)
- `min_gate_grade`: HASAN (at least one corroborating chain must be HASAN+)

## Running

```bash
# From repo root
python experiments/corroboration_v1/run.py   # Run the experiment
python experiments/corroboration_v1/analyze.py  # Analyze results
```

## Success Criteria

| Metric | Target |
|---|---|
| Corroboration fired rate (Phase A) | >80% |
| Corroboration fired rate (Phase B) | >20% |
| Grade upgrade rate | >30% |
| Claims processed | >50 |

## Files

- `data_loader.py` — Wikipedia API client, sentence extraction, near-duplicate detection
- `run.py` — Main experiment: chain building, grading, corroboration, reporting
- `analyze.py` — Result analysis and diagnosis
- `results/` — Output directory (results.json, report.txt)
