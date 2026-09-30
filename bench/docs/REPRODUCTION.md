# ISNAD-Bench — reproduction record

Independent re-run of the headline chain-grading number, from the public dataset.

## What was reproduced
`uv run python -m bench.run --reproduce` (+ `--lenient`, + `bench.human_ceiling`) against
`hadith-kg.db` (CC-BY-4.0, `emadjumaah/hadith-kg`), SHA-256 pinned in `bench/run.py`.

## Result

| Metric | Published | Reproduced | Match |
|---|---|---|---|
| Chain-grade κ (strict) | 0.871 | **0.8714** (computed; unweighted 0.8745 · linear-weighted 0.8917) | ✅ |
| Chain-grade κ (lenient) | 0.761 | agreement 480,702/575,060 = 83.6% | ✅ |
| Human ceiling (inter-critic κ) | 0.331 | **0.33** | ✅ |
| Single scholar vs consensus | 0.45 | **0.45** | ✅ |
| Shuffled-rank control | −0.007 | **−0.0066** | ✅ |
| Majority-class control | 0.000 | **0.0000** | ✅ |
| Graded chains | 575,060 | **575,060** | ✅ |

## Honest framing (from the harness output)
> "The scholars disagree with each other at κ = 0.33 — the ground truth itself is
> contested. ISNAD tracks the consensus at κ = 0.871 … it is not 'better than the
> scholars', it is a deterministic reflection of their average opinion."

## How to re-run
```bash
# 1. download the dataset (1.6 GB, CC-BY-4.0)
curl -L -o data/hadith-kg.db "https://huggingface.co/datasets/emadjumaah/hadith-kg/resolve/main/hadith-kg.db"
shasum -a 256 data/hadith-kg.db   # must equal d528084321e715006712e0e2461809a3afc9408065a1d1af90238c8b723815a6
# 2. run
uv run python -m bench.run --reproduce
uv run python -m bench.human_ceiling
```

- Date: 2026-09-30
- DB SHA-256: `d528084321e715006712e0e2461809a3afc9408065a1d1af90238c8b723815a6`
- Note: the strict κ (0.8714) is the COMPUTED value from `bench.run --reproduce`
  (`Cohen's kappa: 0.8714`), not the hardcoded string in `bench.human_ceiling`. The
  human-ceiling 0.33 (inter-critic) and 0.45 (critic-vs-consensus) are computed independently.
