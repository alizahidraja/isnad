# ISNAD-Bench

**One reproducible agreement number between ISNAD's weakest-link chain grading
and a rule-based grading convention derived from Ibn Hajar's 12 narrator tiers.**

This directory is deliberately separate from `src/isnad/` — it imports the
library but touches nothing in it. The 1.6 GB dataset lives in `data/`
(gitignored) and is never committed.

## What it measures

ISNAD grades *chains* (isnād), not hadith. The dataset (emadjumaah/hadith-kg) provides
~577,000 graded chains — a rule-based convention derived from Ibn Hajar's 12 narrator
tiers — with named narrators and named critics. This
benchmark asks a single, falsifiable question:

> When ISNAD is given the classical scholars' narrator grades, does its
> weakest-link rule reproduce the dataset's rule-based chain-verdict convention?

The answer is reported as **Cohen's κ** plus a full confusion matrix — never
raw accuracy (ḥasan is the plurality at 32.4%, so accuracy would flatter a
majority-class predictor), and never a single number without its
disagreement analysis.

## Ground truth

- **Dataset:** [`emadjumaah/hadith-kg`](https://huggingface.co/datasets/emadjumaah/hadith-kg) (CC-BY-4.0), 715,790 hadiths, 577,024 chains, 49,844 narrators, 127,863 criticism statements by 945 critics.
- **Narrator ranks:** Ibn Ḥajar's *Taqrīb al-Tahdhīb* 12 tiers (`rawis.rank_no`).
- **Chain verdicts:** the dataset's chain-verdict field (`sanads.hukum`, a templated convention string).
- **Weakest link:** `sanads.max_rank` (verified = max narrator rank in the chain).

## The mapping (the scientific claim)

The classical 12-tier → ISNAD grade mapping is the whole game — it is
**pre-committed** in [`docs/mapping.md`](docs/mapping.md) and frozen before any
number is computed. Read that first; it is the benchmark's credibility.

## Milestones

| # | Milestone | Number |
|---|---|---|
| M1 | Chain-grade agreement on Sahih Muslim only (all-ṣaḥīḥ) | false-demotion rate (lower-bound honesty) |
| M2 | Full-corpus discrimination (ṣaḥīḥ/ḥasan/ḍaʿīf/mawḍūʿ) | Cohen's κ + confusion matrix + error analysis |
| M3 | Narrator-grade agreement via per-critic agreement (`aqwal`) | critic-vs-critic κ (context, not a ceiling) |
| M4 | Ikhtilāṭ → period-sliced grades (`get_grade_as_of`) | validates the flagship #43 feature |

## Run

```bash
uv run python -m bench.run            # strict (default), full corpus
uv run python -m bench.run --lenient  # ungraded → ḥasan
uv run python -m bench.run --sample 2000  # quick smoke test
uv run python -m bench.human_ceiling  # M3: inter-critic agreement
```

## Honesty rules (non-negotiable)

- The primary number is **κ**, not accuracy.
- Every disagreement is bucketed: mapping ambiguity / missing grade / weakest-link-vs-nuance / continuity / genuine bug.
- Negative controls (majority-class, shuffled-grade) are reported beside the real number.
- The narrator-grade agreement is reported beside ISNAD as context — it is not a ceiling.

## Audit & review discipline

Every change to this benchmark — and every number it produces — passes through
a standing **multi-persona audit** before it is trusted:

- **Honesty/Auditor** — is the claim scoped? is a limit hidden or stated?
- **Measurement scientist** — is the metric right for the class imbalance? is
  the mapping pre-committed and un-tuned?
- **Security/Threat** — data provenance, no keys, supply-chain integrity.
- **DevEx/Adopter** — is the one-command story intact?
- **Maintainer** — tests, lint, mypy, docs stay green.

These are not optional; a number without this audit is not shipped.
