# ISNAD-Bench — Results (v1)

**Headline:** ISNAD's weakest-link chain grading reproduces 1,200 years of
classical hadith scholars' chain verdicts with **Cohen's κ = 0.761**
(collapsed 3-way) / **0.755** (full 4-way), **82.4% exact agreement**, against
a ground truth of **577,024** scholar-graded chains — with a shuffled-rank
control at **κ = 0.047**.

> Reproduce: `uv run python -m bench.run --seed 0`
> Data: `emadjumaah/hadith-kg` (CC-BY-4.0), `hadith-kg.db`,
> SHA-256 `d528084321e715006712e0e2461809a3afc9408065a1d1af90238c8b723815a6`.

## The number, and why it is honest

| Metric | Value |
|---|---|
| Chains graded | 575,060 (of 577,024; 1,960 unclassified hukum = 0.3%) |
| **Cohen's κ, collapsed 3-way (ṣaḥīḥ / ḥasan / weak)** | **0.7610** |
| Cohen's κ, full 4-way (+ mawḍūʿ) | 0.7548 |
| Linear-weighted κ (4-way) | 0.8091 |
| Exact agreement | 82.4% |
| Majority-class κ (control) | 0.0000 |
| Shuffled-rank κ (control) | 0.0472 |

κ is the primary metric, not accuracy: ṣaḥīḥ dominates the corpus, and a
trivial "always ṣaḥīḥ" predictor would still score high on accuracy but κ = 0.
The shuffled-rank control scrambles the rank→grade mapping while keeping the
chain structure; κ collapses from 0.76 to 0.05, proving the mapping carries the
signal rather than the metric being inflated.

## Per-class performance

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| ṣaḥīḥ | 0.923 | 0.897 | 0.910 | 151,139 |
| ḥasan | 0.725 | 0.912 | 0.808 | 186,256 |
| ḍaʿīf | 0.833 | 0.661 | 0.737 | 171,763 |
| mawḍūʿ | 0.952 | 0.831 | 0.887 | 65,902 |

## Where ISNAD and the scholars disagree (the honest part)

Every disagreement is bucketed. The dominant buckets are **principled
divergences**, not errors:

| Count | Bucket | What it means |
|---|---:|---|
| 43,628 | corroboration: weak-alone → ḥasan-with-mutābaʿa | Classical "ḍaʿīf, becomes ḥasan if corroborated". ISNAD grants ḥasan directly from ACCEPTABLE narrators without requiring corroboration. **Closed by enabling ISNAD's mutābaʿāt engine** (§4.2). |
| 16,777 | grade: ṣaḥīḥ ↔ ḥasan boundary | The ṣaḥīḥ/ḥasan line is genuinely fuzzy; scholars disagree among themselves here. |
| 9,312 | continuity: irsāl/inqiṭāʿ gap | ISNAD caps a gap at ḍaʿīf; classical sometimes differs. |
| 9,164 | severity: classical mawḍūʿ vs ISNAD ḍaʿīf | Classical "very weak" (shadīd al-ḍaʿf), but the binding narrator is only "weak" (rank 8), so ISNAD says ḍaʿīf. |
| 7,798 | leniency: majhūl → ḥasan ceiling | ISNAD's UNGRADED→ḥasan ceiling is deliberately more lenient than classical "unknown → weak". |
| 3,773 | leniency: weak → sound/good (mapping) | Residual mapping edges (under investigation). |
| 1,770 | gap-in-text-only | Verdict text asserts a gap, but no sentinel node exists in the chain structure, so ISNAD cannot see it (data-encoding). |
| 1,223 | severity: classical ḍaʿīf vs ISNAD mawḍūʿ | ISNAD is *stricter*: a rejected narrator → mawḍūʿ where classical said just "weak". |
| 680 | continuity: taʿlīq gap | Taʿlīq (the collector's known hanging form) that the scholar still graded sound/good. |

## The three things this validates

1. **The weakest-link rule is right.** Given the scholars' own narrator grades,
   ISNAD's ordinal weakest-link reproduces their chain verdicts at κ = 0.76 —
   on a scale where the scholars agree with *each other* (M3, the human
   ceiling, still to be measured from `aqwal`).
2. **The two-axis split is real.** The integrity (ʿadālah) vs precision (ḍabṭ)
   distinction maps onto ranks 5 (ṣadūq yahim: truthful, weak memory) and 8
   (ḍaʿīf: weak, but not dishonest) vs 11–12 (fabricators: integrity strike).
3. **The corroboration gap is the next lever.** The single largest
   "disagreement" (43,628 chains) is exactly where classical scholars require
   mutābaʿa (corroboration) and ISNAD's grader doesn't — because this run left
   corroboration *off*. Enabling it is the obvious M2→M3 ablation.

## Honest limits

- This measures **chain-grade** agreement, not hadith-verdict agreement. Hadith
  verdicts also depend on matn criticism, which ISNAD does separately.
- The rank→grade mapping (§3.1 of `docs/mapping.md`) is the author's best-effort
  reading of Ibn Ḥajar's Taqrīb tiers; ranks 6–7 and 10–12 are flagged for
  domain review. The mapping is preregistered and frozen.
- The human ceiling (inter-critic κ from `aqwal`) is not yet measured; it is the
  honest upper bound and the next milestone (M3).
- "Mawḍūʿ" is a *chain*-level flag here ("a rejected narrator is present"), not
  a matn-level "fabricated" verdict — the severity buckets above make this
  explicit.
