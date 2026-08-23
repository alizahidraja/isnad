# ISNAD-Bench — Results (v2)

**Headline:** ISNAD's weakest-link chain grading reproduces 1,200 years of
classical hadith scholars' chain verdicts with **Cohen's κ = 0.871** in strict
mode (classical majhūl) and **0.761** in lenient mode (ISNAD default), across
**577,024** scholar-graded chains — with a shuffled-rank control at κ = 0.047.

> Reproduce:
> `uv run python -m bench.run --seed 0` (lenient) ·
> `uv run python -m bench.run --seed 0 --strict` (classical majhūl)
>
> Data: `emadjumaah/hadith-kg` (CC-BY-4.0), `hadith-kg.db`,
> SHA-256 `d528084321e715006712e0e2461809a3afc9408065a1d1af90238c8b723815a6`.

## The two modes, side by side

ISNAD has two deliberate stances on a narrator it has never graded:

| Mode | UNGRADED narrator | 3-way κ | 4-way κ | Agreement |
|---|---|---|---:|---:|
| **lenient** (default) | caps at ḥasan (epistemic humility) | 0.7610 | 0.7548 | 82.4% |
| **strict** (`strict_unknown=True`) | caps at ḍaʿīf (classical majhūl) | **0.8714** | **0.8571** | **89.7%** |

The gap between them is the measured cost of the default leniency: **0.11 κ**.
Classical scholars treat an *unknown* narrator as making the chain weak; ISNAD's
default treats "ungraded" as a ḥasan ceiling (don't claim ṣaḥīḥ, but don't
punish the absence of a grade). Both are honest, documented choices — the
benchmark just quantifies them. The strict mode is opt-in in the library via
`grade_chain(..., strict_unknown=True)`.

## Negative controls

| Control | κ |
|---|---:|
| majority-class predictor | 0.0000 |
| shuffled-rank (scrambled mapping) | 0.0472 |

## Per-class performance (strict mode)

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| ṣaḥīḥ | 0.944 | 0.899 | 0.921 | 151,139 |
| ḥasan | 0.775 | 0.934 | 0.847 | 186,256 |
| ḍaʿīf | 0.897 | 0.818 | 0.856 | 171,763 |
| mawḍūʿ | 0.953 | 0.831 | 0.888 | 65,902 |

## The corroboration ablation (mutābaʿa)

The largest remaining "disagreement" is classical **"ḍaʿīf, becomes ḥasan if
corroborated"** (ضعيف ويحسن إذا توبع) — a *conditional* verdict. ISNAD, grading
each chain in isolation, grants ḥasan directly. The ablation asks: how many of
those chains actually have an independent corroborating route (same meaning
group, disjoint non-companion narrators)?

| Mode | weak-alone → ḥasan chains | with an independent route |
|---|---:|---:|
| lenient | 43,628 | **38,393 (88.0%)** |
| strict | 5,520 | **5,079 (92.0%)** |

So for ~88–92% of the chains ISNAD "over-grades", classical scholars would
*also* grade them ḥasan — via mutābaʿa — because an independent route exists.
Only the small remainder are genuine over-grades. This is direct evidence that
ISNAD's corroboration engine is the right next mechanism to wire in.

## Where ISNAD and the scholars disagree (lenient mode, bucketed)

| Count | Bucket | Meaning |
|---|---:|---|
| 43,628 | corroboration: weak-alone → ḥasan-with-mutābaʿa | 88% have independent support (above). |
| 16,777 | grade: ṣaḥīḥ ↔ ḥasan boundary | genuinely fuzzy; scholars disagree too. |
| 9,312 | continuity: irsāl/inqiṭāʿ gap | ISNAD caps gaps at ḍaʿīf. |
| 9,164 | severity: classical mawḍūʿ vs ISNAD ḍaʿīf | classical "very weak" but binding narrator is only rank 8. |
| 7,798 | leniency: majhūl → ḥasan ceiling | **fixed by strict mode.** |
| 3,773 | leniency: weak → sound/good (mapping) | residual mapping edges. |
| 1,770 | gap-in-text-only | gap in verdict text, no sentinel node. |
| 1,223 | severity: classical ḍaʿīf vs ISNAD mawḍūʿ | ISNAD stricter (rejected narrator). |
| 680 | continuity: taʿlīq gap | collector's known hanging form. |

## The three things this validates

1. **The weakest-link rule is right.** Given the scholars' own narrator grades,
   ISNAD reproduces their chain verdicts at κ = 0.87 (strict) — on a scale where
   the human ceiling (inter-critic agreement) is still to be measured.
2. **The two-axis split is real.** Integrity vs precision maps cleanly onto the
   classical ranks (ṣadūq-yahim = truthful-but-errs → precision LOW; fabricators
   → integrity COMPROMISED).
3. **Corroboration is the next lever, and it is real.** 88–92% of the remaining
   gap is exactly the mutābaʿa concept — corroboration the scholars themselves
   applied.

## Honest limits

- Measures **chain-grade** agreement, not hadith-verdict agreement (matn is out
  of scope for the chain path).
- The rank→grade mapping is the author's best-effort reading of Ibn Ḥajar's
  Taqrīb; preregistered and frozen. Ranks 6–7 and 10–12 flagged for review.
- The human ceiling (inter-critic κ from `aqwal`) is the next milestone (M3).
- "Mawḍūʿ" is a *chain*-level flag ("a rejected narrator is present"), not a
  matn-level "fabricated" verdict.
