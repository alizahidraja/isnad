# ISNAD-Bench — derived graded output

**One reproducible agreement number between ISNAD's weakest-link chain grading
and 1,200 years of labelled hadith ground truth.**

## What this is (and is not)

This is **derived output**, not a re-host of the source data. The underlying
dataset is [`emadjumaah/hadith-kg`](https://huggingface.co/datasets/emadjumaah/hadith-kg)
(CC-BY-4.0). This dataset contains, per chain, the scholar's verdict, ISNAD's
predicted chain grade, and the principled disagreement bucket — computed by the
exact functions that produce the benchmark's κ.

## The headline number — and how to read it

ISNAD's weakest-link chain grading reproduces 1,200 years of classical hadith
scholars' chain verdicts at **Cohen's κ = 0.871** (strict default), across
**577,024** scholar-graded chains, with a shuffled-rank control at κ = 0.047.

**ISNAD faithfully implements the scholars' consensus; it is not "better than
the scholars".** The human ceiling — how well the scholars agree with *each
other* — is κ = 0.331 (critic-vs-critic). ISNAD's 0.871 means it is a
deterministic reflection of the scholars' *average opinion*, on a scale where
they disagree with each other at 0.331. The consensus it tracks is the honest
upper bound, not a thing to exceed.

## Scope limit (read before citing)

This measures **chain-grade (isnād) agreement only** — not matn (content)
verdicts, and not hadith authenticity. "Mawḍūʿ" here is a chain-level flag
("a rejected narrator is present"), not a matn-level "fabricated" verdict.

## Provenance & reproducibility

| Field | Value |
|---|---|
| Derived from | `emadjumaah/hadith-kg` (CC-BY-4.0) |
| Source SHA-256 | `d528084321e715006712e0e2461809a3afc9408065a1d1af90238c8b723815a6` |
| Mapping | `bench/docs/mapping.md` (preregistered, frozen) |
| Reproduction | `uv run python -m bench.run --seed 0` |
| Software | `pip install isnad` (Apache-2.0) |
| Paper | arXiv:2607.24117 · DOI 10.48550/arXiv.2607.24117 |

## The mapping caveat (honest, not hidden)

The 12-tier → ISNAD grade mapping is the **author's best-effort reading of Ibn
Ḥajar's *Taqrīb al-Tahdhīb* tiers**. The project has **no external domain
reviewer yet**; ranks 6–7 and 10–12 are the rows most likely to need a scholar's
correction. Any correction is a new mapping version with a new, separately
reported number — never a silent edit.

## File format

One JSON object per line, prefixed by a `# ` JSON header carrying the source
SHA-256, the mapping SHA-256, and the exact invocation. Schema:

`sanad_id, hukum, true_grade, predicted_grade, disagreement_bucket, is_complete,
has_gap, has_taliq, narrator_rank_nos, mode`
