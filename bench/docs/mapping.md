# ISNAD-Bench — ground-truth mapping (preregistered)

> **Status:** DRAFT v1 — submitted for review. Not yet frozen.
> This document is the *scientific claim* that makes the benchmark number
> meaningful. It maps classical hadith narrator grading to ISNAD's ordinal
> grades. It is committed to git **before** any result is computed, and must
> not be edited after results exist — any change is a new version with a new
> number (see "Preregistration commitment" below).

---

## 1. Data provenance (verified, not assumed)

| Field | Value |
|---|---|
| Dataset | [`emadjumaah/hadith-kg`](https://huggingface.co/datasets/emadjumaah/hadith-kg) ("الجامع" knowledge graph) |
| Source repo | `github.com/qataruts/hadith` |
| License | CC-BY-4.0 (per dataset card) |
| File | `hadith-kg.db` (canonical relational KG) |
| Size | 1,634,877,440 bytes |
| SHA-256 | `d528084321e715006712e0e2461809a3afc9408065a1d1af90238c8b723815a6` |
| Rows | 715,790 hadiths · 577,024 sanads · 4.4M sanad_rawl links · 49,844 narrators · 127,863 criticism statements (1,015 critics) |

### Relevant schema (inspected live)

| Table | Key columns | Meaning |
|---|---|---|
| `rawis` | `rank`, `rank_no`, `has_ikhtilat`, `has_tadlis`, `is_bukhari`, `is_muslim` | one narrator, with a 12-tier reliability rank |
| `sanads` | `hukum`, `max_rank`, `length` | one chain; `hukum` = scholar's verdict; `max_rank` = weakest-link rank |
| `sanad_rawis` | `sanad_id`, `pos`, `rawi_id` | ordered narrator links of a chain |
| `hadiths` | `type`, `matn`, `group_id` | `type` = attribution type (مرفوع/موقوف/مقطوع/قدسي), **not** authenticity |
| `aqwal` / `alems` | `rawi_id`, `alem_id`, `qawl` | 127,863 criticism statements by 1,015 named critics |

`max_rank` was verified equal to `max(rank_no)` over the chain's links
(sampled 5/5). `hukum` is the scholar's free-text chain verdict.

> **Correction (found during implementation):** `max_rank` is *not* a clean
> weakest-link signal. The corpus encodes **chain discontinuities** as synthetic
> sentinel narrators — `موضع تعليق` (taʿlīq), `موضع إرسال` (irsāl),
> `موضع انقطاع` (inqiṭāʿ) — assigned `rank_no=12` with `rank=NULL`. They appear
> in 51,803 of 577,024 chains (~9%). These are the classical *ittiṣāl* gaps, and
> they map directly onto ISNAD's `is_complete=False`. The benchmark therefore
> (a) treats a sentinel node as a chain gap, and (b) computes the true
> weakest-link rank from **non-sentinel** narrators only.

---

## 2. The ground-truth ladder: Ibn Ḥajar's 12 tiers

The corpus encodes Ibn Ḥajar al-ʿAsqalānī's *Taqrīb al-Tahdhīb* ranking,
the standard modern reference for rijāl grading. `rank_no` is the ordinal
(1 = best, 12 = worst). Distribution over 49,844 narrators:

| rank_no | Arabic | Transliteration | Meaning | Count |
|---|---:|---|---|---:|
| 1 | صحابي | Ṣaḥābī | Companion of the Prophet | 2,315 |
| 2 | ثقة حافظ / ثقة ثبت | Thiqah ḥāfiẓ / thabt | Reliable, precise (top tier) | 994 |
| 3 | ثقة | Thiqah | Reliable | 6,173 |
| 4 | صدوق حسن الحديث | Ṣadūq ḥasan al-ḥadīth | Truthful, good hadith | 5,718 |
| 5 | صدوق يهم | Ṣadūq yahim | Truthful but errs | 301 |
| 6 | مقبول | Maqbūl | Acceptable (with corroboration) | 5,901 |
| 7 | مجهول الحال | Majhūl al-ḥāl | Unknown condition (mastūr) | 23,001 |
| 8 | ضعيف الحديث | Ḍaʿīf al-ḥadīth | Weak in hadith | 1,788 |
| 9 | مجهول | Majhūl | Unknown | 1,868 |
| 10 | متروك / منكر | Matrūk / munkar | Abandoned / rejected | 966 |
| 11 | متهم بالكذب / بالوضع | Muttaham bi-l-kadhib | Accused of lying / fabrication | 540 |
| 12 | كذاب / وضاع | Kadhdhāb / waḍḍāʿ | Liar / fabricator | 254 |

---

## 3. The mapping (preregistered)

### 3.1 Narrator grade: `rank_no` → ISNAD

| rank_no | NarratorGrade | AdalahGrade (integrity) | DabtGrade (precision) | Rationale |
|---|---:|---|---|---|
| 1–3 | RELIABLE | HIGH | HIGH | Ṣaḥābī / thiqah: both axes sound |
| 4 | ACCEPTABLE | ACCEPTABLE | ACCEPTABLE | Ṣadūq ḥasan: the canonical ḥasan narrator |
| 5 | ACCEPTABLE | ACCEPTABLE | LOW | Ṣadūq yahim: **integrity fine, precision weak** — the two-axis split is load-bearing |
| 6 | ACCEPTABLE | ACCEPTABLE | ACCEPTABLE | Maqbūl: accepted **only with corroboration** (see §4.1) |
| 7 | UNGRADED | UNASSESSED | UNASSESSED | Majhūl al-ḥāl: no evidence either way |
| 8 | WEAK | ACCEPTABLE | LOW | Ḍaʿīf al-ḥadīth: precision weakness (recoverable) |
| 9 | UNGRADED | UNASSESSED | UNASSESSED | Majhūl: unknown |
| 10 | REJECTED | SUSPECT | LOW | Matrūk/munkar: abandoned (mixed) |
| 11–12 | REJECTED | COMPROMISED | LOW | Muttaham/kadhdhāb/waḍḍāʿ: integrity strike — permanent |

**Integrity ladder check** (§ of ISNAD #30): rank 11–12 map to `COMPROMISED`
integrity, which ISNAD's grader makes *permanently* REJECTED. Rank 8 maps to
`WEAK` with *uncompromised* integrity — the precision-driven, recoverable
case (#40). This is the benchmark's direct test of the integrity/precision
split.

### 3.2 Chain verdict: `sanads.hukum` → ISNAD `ChainGrade`

`hukum` is free text; we classify on the leading phrase (preregistered):

| Leading phrase | ChainGrade |
|---|---|
| `إسناده متصل ، رجاله ثقات` (connected, thiqah) | SAHIH |
| `إسناد حسن` (ḥasan chain) | HASAN |
| `إسناد ضعيف` (weak chain) | DAIF |
| `إسناد شديد الضعف` / `فيه متهم بالوضع` / `متروك` (very weak / fabrication) | MAWDU |

### 3.3 Chain computation

Each `sanad` is a `PASS_THROUGH` chain (every narrator faithfully transmits).
A sentinel node (`موضع تعليق` / `موضع إرسال` / `موضع انقطاع`) makes the chain
`is_complete=False` (ISNAD caps it at DAIF) and is excluded from the narrator
list. Because the gap is read from the chain **structure** (`sanad_rawis`), not
from the `hukum` text, there is no circularity: `is_complete` is an independent
signal, and the `hukum` verdict is the ground-truth label. We run `grade_chain`
over the mapped `NarratorGrade` list; corroboration and transform refinement are
introduced as **ablation layers** (see §4), not baked into the primary number.

---

## 4. Known principled divergences (we surface these, not hide them)

These are places where ISNAD and classical grading can *legitimately* disagree.
The benchmark must report them separately, not bury them in a single accuracy
number.

1. **UNGRADED → ḍaʿīf (default) vs ḥasan (lenient opt-in).** Classical scholars
   treat a *majhūl* (unknown) narrator as making the chain weak. ISNAD now
   **defaults** to the same (ungraded caps at ḍaʿīf via `strict_unknown`'s
   successor, `lenient_unknown=False`). The earlier lenient stance — ungraded
   caps at ḥasan (never claim ṣaḥīḥ without evidence) — is opt-in via
   `lenient_unknown=True`. ISNAD-Bench measures the gap at 0.11 κ; the default
   is strict, matching the method ISNAD claims descent from.

2. **Maqbūl (rank 6/7) is corroboration-dependent.** Classical `مقبول` means
   "accepted only in mutābaʿāt/shawāhid" — ḥasan *with* an independent
   supporting chain, ḍaʿīf alone. The primary number (no corroboration) will
   therefore over-grade these; a second number *with* ISNAD's corroboration
   engine enabled should close the gap. This is the benchmark's direct test of
   the mutābaʿāt mechanism.

3. **Ittiṣāl (continuity).** Classical grading penalises `إرسال`/`تعليق`/`انقطاع`
   (breaks). ISNAD encodes this as `is_complete=False → DAIF`. The corpus marks
   these breaks as sentinel nodes, so `is_complete` is read from chain structure
   (independent of the verdict), and continuity disagreement is measured, not
   assumed away.

4. **The two-axis split at ranks 10–12** (matrūk = SUSPECT vs COMPROMISED) is a
   judgment call. Flagged for domain review; it does not affect the
   NarratorGrade→ChainGrade outcome (all REJECTED → MAWDU), only the
   integrity-ladder diagnostic.

---

## 5. Preregistration commitment

1. This document is committed to `feature/58-isnad-bench` **before** any
   agreement number is computed.
2. The primary metric is Cohen's κ (and the full confusion matrix + per-class
   precision/recall) — **not** raw accuracy (sahih dominates).
3. The mapping is **frozen** once the first number is computed. Any change
   produces a new `mapping` version and a new, separately-reported number.
4. Negative controls: (a) majority-class baseline (always-sahih), (b)
   shuffled-grade baseline — reported alongside the real number.
5. The **human ceiling** is reported alongside: inter-critic agreement over the
   same chains (from `aqwal`). ISNAD cannot be expected to exceed it.

---

*Author's note: this mapping is my best-effort reading of Ibn Ḥajar's Taqrīb
tiers. The repo has no external domain reviewer yet; the ranks 6–7 and 10–12
rows in §3.1 are the places most likely to need a scholar's correction.*
