# ISNAD Benchmark

The reproducible numbers behind ISNAD — and how to run them on **your own system**.

## The two benchmarks

| Benchmark | What it measures | Honest headline | Run |
|---|---|---|---|
| **ISNAD-Bench** | weakest-link grading vs 577,024 chains (575,060 graded) | **κ = 0.871** (human ceiling κ = 0.331) | `uv run python -m bench.run` |
| **Adversarial** | corruption detection on a synthetic corpus | **narrator grading 100%**, content criticism 15% | `uv run python experiments/adversarial_benchmark/run.py` |

The headline numbers lead with the *split*, not a conflated average — the
narrator-grading layer and the content critic are at different maturity, and
the benchmark says so.

## Baselines (reported beside every number)

| Baseline | Result |
|---|---|
| no-gating (serve everything) | 0% recall, 0% FPR |
| confidence-gating | ≈ random — self-reported confidence is noise (§8) |
| shuffled-grade (scrambled mapping) | κ = −0.007 |
| majority-class | κ = 0.000 |

## Run it on *your* data

The adoption path: grade your own corpus + narrator set, no dataset required.

```bash
pip install isnad
isnad bench --config mine.json
```

`mine.json`:

```json
{
  "domain": "physics",
  "narrators": {
    "source:openstax": "reliable",
    "model:gpt-4o": "acceptable",
    "model:gpt-4o-mini": "weak"
  },
  "claims": [
    {"text": "force equals mass times acceleration",
     "chain": ["source:openstax", "model:gpt-4o"]}
  ]
}
```

Output is a JSON scorecard: per-claim chain grade + the grade distribution.
Grades are **operator-assigned** — you bring the narrator grades; ISNAD applies
the weakest-link rule and reports what it would do.

## Submission

The benchmark is a *yardstick*, not a self-assessment. If you run it on your
system, report:

- the config (corpus + narrator grades) you used,
- the resulting grade distribution,
- any disagreements you think are ISNAD mis-grading (with the specific claim).

Open an issue with that. The honest number is the point; an inflated one is a
bug.

## Method & limits

- **ISNAD-Bench** is preregistered (`bench/docs/mapping.md`) — the Arabic-grade
  → ISNAD mapping was committed before any number was computed.
- The corpus is gitignored and pinned by SHA-256; `bench/README.md` documents
  the audit discipline.
- The human ceiling (scholars-vs-scholars κ = 0.331) is reported beside ISNAD —
  it is the honest upper bound, not a thing to exceed.
