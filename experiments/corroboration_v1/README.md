# Corroboration Experiment v1 — Exact String Matching

**Status:** Superseded by v2 (semantic matching).  Kept for historical
comparison.  v1 proved the mechanism works; v2 proves it works on
semantically-matched real data.

## Key Results (Historical)

| Metric | Value |
|---|---|
| Total claims | 136 |
| Corroboration fired | 68/136 (50%) |
| Phase A (synthetic) | 59/59 DAIF→HASAN |
| Phase B (cross-topic) | 9/18 DAIF→HASAN |
| Data | 12 Wikipedia intros, ~215 sentences |

## Differences from v2

| | v1 | v2 |
|---|---|---|
| Matching | Exact string | Cosine similarity ≥ 0.75 |
| Sources | Wikipedia + synthetic "Britannica" chain | Wikipedia + Simple Wikipedia |
| Claims | 136 | 603 |
| Source URLs | No | Yes (100%) |
| Negative controls | No | Yes (8/8) |

## Why v1 Matters

v1 discovered the critical design requirements:
- Chains must use **completely disjoint narrator IDs** for independence
- Model families must differ (shared family → madār penalty)
- `min_independent_chains=1` for 2-source experiments

These findings drove the source code fixes on main.

---

## Run

```bash
cd experiments/corroboration_v1
python run.py       # Fetch Wikipedia intros + run
python analyze.py   # Analyze
```
