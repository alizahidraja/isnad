# ISNAD-Bench

**One reproducible agreement number between ISNAD's weakest-link chain grading
and 1,200 years of labelled hadith ground truth.**

This directory is deliberately separate from `src/isnad/` — it imports the
library but touches nothing in it. The 1.6 GB dataset lives in `data/`
(gitignored) and is never committed.

## What it measures

ISNAD grades *chains* (isnād), not hadith. Classical hadith scholarship already
graded ~577,000 chains by hand, with named narrators and named critics. This
benchmark asks a single, falsifiable question:

> When ISNAD is given the classical scholars' narrator grades, does its
> weakest-link rule reproduce the scholars' own chain verdicts?

The answer is reported as **Cohen's κ** plus a full confusion matrix — never
raw accuracy (ṣaḥīḥ dominates), and never a single number without its
disagreement analysis.

## Ground truth

- **Dataset:** [`emadjumaah/hadith-kg`](https://huggingface.co/datasets/emadjumaah/hadith-kg) (CC-BY-4.0), 715,790 hadiths, 577,024 chains, 49,844 narrators, 127,863 criticism statements by 1,015 critics.
- **Narrator ranks:** Ibn Ḥajar's *Taqrīb al-Tahdhīb* 12 tiers (`rawis.rank_no`).
- **Chain verdicts:** the scholar's own verdict text (`sanads.hukum`).
- **Weakest link:** `sanads.max_rank` (verified = max narrator rank in the chain).

## The mapping (the scientific claim)

The classical 12-tier → ISNAD grade mapping is the whole game — it is
**preregistered** in [`docs/mapping.md`](docs/mapping.md) and frozen before any
number is computed. Read that first; it is the benchmark's credibility.

## Milestones

| # | Milestone | Number |
|---|---|---|
| M1 | Chain-grade agreement on Sahih Muslim only (all-ṣaḥīḥ) | false-demotion rate (lower-bound honesty) |
| M2 | Full-corpus discrimination (ṣaḥīḥ/ḥasan/ḍaʿīf/mawḍūʿ) | Cohen's κ + confusion matrix + error analysis |
| M3 | Human ceiling via per-critic agreement (`aqwal`) | inter-critic κ vs ISNAD-vs-consensus κ |
| M4 | Ikhtilāṭ → period-sliced grades (`get_grade_as_of`) | validates the flagship #43 feature |

## Run (when implemented)

```bash
uv run python bench/run.py            # full corpus
uv run python bench/run.py --sample   # CI smoke test on a committed fixture
```

## Honesty rules (non-negotiable)

- The primary number is **κ**, not accuracy.
- Every disagreement is bucketed: mapping ambiguity / missing grade / weakest-link-vs-nuance / continuity / genuine bug.
- Negative controls (majority-class, shuffled-grade) are reported beside the real number.
- The human ceiling is reported beside ISNAD — it is the honest upper bound.
