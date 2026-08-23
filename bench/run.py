"""ISNAD-Bench: measure ISNAD's chain grading against classical ground truth.

Run:  uv run python -m bench.run [--db PATH] [--limit N | --sample N]

The primary question, stated once:

    When ISNAD is given the classical scholars' narrator grades, does its
    weakest-link rule reproduce the scholars' own chain verdicts?

The primary metric is Cohen's kappa (not accuracy — sahih dominates). A
collapsed 3-way (sahih / hasan / weak) is reported alongside the full 4-way,
because classical isnād verdicts are fundamentally three-tiered; ISNAD's fourth
grade (mawḍūʿ) is a *stricter* flag meaning "a rejected narrator is present",
which classical scholars usually express as "weak" (ḍaʿīf) or "very weak".
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from collections import Counter
from collections.abc import Iterator, Sequence

from bench.data import Node, RawChain, iter_chains
from bench.mapping import chain_grade_from_hukum, narrator_grade_from_rank
from bench.metrics import (
    cohens_kappa,
    confusion_matrix,
    linear_weighted_kappa,
    per_class_metrics,
)
from isnad.core.grading import grade_chain
from isnad.types import ChainGrade, NarratorGrade, TransformType

CLASSES = [g.value for g in (ChainGrade.SAHIH, ChainGrade.HASAN, ChainGrade.DAIF, ChainGrade.MAWDU)]

# Sentinel names (gap markers) → whether the gap is the grade-preserving taʿlīq
# form or a genuine break (irsāl / inqiṭāʿ).
_TALIQ = "موضع تعليق"

_GradeResult = tuple[list[NarratorGrade], bool, list[int], bool, bool]


def _load_sanad_ids(db_path: str) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT id FROM sanads")]
    finally:
        conn.close()


def _grade_one_chain(
    nodes: tuple[Node, ...], rank_map: dict[int, NarratorGrade] | None = None
) -> _GradeResult:
    """Map one chain's nodes to ISNAD grades (sentinels → is_complete)."""
    narrator_grades: list[NarratorGrade] = []
    rank_nos: list[int] = []
    has_gap = False
    has_taliq = False
    for node in nodes:
        mapped = narrator_grade_from_rank(node.rank_no, node.rank, node.name)
        if mapped.is_sentinel:
            has_gap = True
            if node.name == _TALIQ:
                has_taliq = True
            continue
        if rank_map is not None and node.rank_no in rank_map:
            grade = rank_map[node.rank_no]
        else:
            grade = mapped.narrator_grade
        narrator_grades.append(grade)
        if node.rank_no is not None:
            rank_nos.append(node.rank_no)
    return narrator_grades, not has_gap, rank_nos, has_taliq, has_gap


def _chain_grade_from_narrators(narrator_grades: list[NarratorGrade], is_complete: bool) -> str:
    transforms = [TransformType.PASS_THROUGH] * len(narrator_grades)
    return str(grade_chain(narrator_grades, transforms, is_complete).value)


def _bucket(
    true: str,
    pred: str,
    has_gap: bool,
    has_taliq: bool,
    rank_nos: list[int],
    hukum: str | None,
) -> str | None:
    """Label a disagreement with the principled explanation, or None."""
    if true == pred:
        return None
    hukum = hukum or ""
    # ISNAD's stricter mawḍūʿ flag vs classical "weak".
    if true == "daif" and pred == "mawdu":
        return "severity: classical ḍaʿīf vs ISNAD mawḍūʿ (rejected narrator)"
    if true == "mawdu" and pred == "daif":
        return "severity: classical mawḍūʿ vs ISNAD ḍaʿīf"
    # Continuity: ISNAD capped at ḍaʿīf because of a chain gap.
    if has_gap and pred == "daif":
        if has_taliq:
            return "continuity: taʿlīq gap (scholar still sound/good)"
        return "continuity: irsāl/inqiṭāʿ gap"
    if true == "daif" and pred in ("hasan", "sahih"):
        # Classical "weak alone, ḥasan with mutābaʿa (corroboration)" — ISNAD
        # grants ḥasan directly from ACCEPTABLE narrators (§4.2 divergence).
        if "توبع" in hukum:
            return "corroboration: weak-alone → ḥasan-with-mutābaʿa"
        if any(r in (7, 9) for r in rank_nos):
            return "leniency: majhūl → ḥasan ceiling"
        # A gap is asserted in the verdict text but no sentinel node exists in
        # the chain structure, so ISNAD cannot see it.
        if any(k in hukum for k in ("تعليق", "إرسال", "انقطاع")):
            return "gap-in-text-only: ḍaʿīf by irsāl/taʿlīq (no sentinel)"
        return "leniency: weak → sound/good (mapping)"
    if true in ("sahih", "hasan") and pred in ("hasan", "sahih"):
        return "grade: ṣaḥīḥ ↔ ḥasan boundary"
    return "other"


def _shuffled_rank_map(rng: random.Random) -> dict[int, NarratorGrade]:
    """A random permutation of the rank→grade assignment (negative control)."""
    grades = [narrator_grade_from_rank(rn).narrator_grade for rn in range(1, 13)]
    rng.shuffle(grades)
    return dict(zip(range(1, 13), grades, strict=True))


_PassResult = tuple[list[str], list[str], list[str | None], int, int]


def _run_pass(
    chains: Iterator[RawChain], rank_map: dict[int, NarratorGrade] | None = None
) -> _PassResult:
    """Grade every chain; return (y_true, y_pred, buckets, unclassified, skipped)."""
    y_true: list[str] = []
    y_pred: list[str] = []
    buckets: list[str | None] = []
    n_unclassified = 0
    n_skipped_empty = 0
    for chain in chains:
        true = chain_grade_from_hukum(chain.hukum)
        if true is None:
            n_unclassified += 1
            continue
        narrator_grades, is_complete, rank_nos, has_taliq, has_gap = _grade_one_chain(
            chain.nodes, rank_map
        )
        if not narrator_grades:
            n_skipped_empty += 1
            continue
        pred = _chain_grade_from_narrators(narrator_grades, is_complete)
        y_true.append(true.value)
        y_pred.append(pred)
        buckets.append(_bucket(true.value, pred, has_gap, has_taliq, rank_nos, chain.hukum))
    return y_true, y_pred, buckets, n_unclassified, n_skipped_empty


def _report_matrix(cm: dict[str, dict[str, int]], classes: Sequence[str]) -> None:
    print("  confusion matrix (rows=true, cols=pred):")
    print("    " + "".join(f"{c[:6]:>9}" for c in classes))
    for c in classes:
        row = "".join(f"{cm[c][d]:>9}" for d in classes)
        print(f"    {c:>6}{row}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/hadith-kg.db", help="path to hadith-kg.db")
    parser.add_argument("--limit", type=int, default=None, help="process first N sanads")
    parser.add_argument("--sample", type=int, default=None, help="random sample of N sanads")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed for sampling/controls")
    parser.add_argument("--no-controls", action="store_true", help="skip negative controls")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    print("=" * 72)
    print("ISNAD-Bench: chain-grade agreement vs classical ground truth")
    print("=" * 72)

    all_ids = _load_sanad_ids(args.db)
    if args.sample is not None:
        ids = rng.sample(all_ids, args.sample)
    elif args.limit is not None:
        ids = all_ids[: args.limit]
    else:
        ids = all_ids
    id_set = set(ids)

    y_true, y_pred, buckets, n_unclassified, n_skipped = _run_pass(iter_chains(args.db, id_set))

    n = len(y_true)
    print(
        f"\ncorpus: {len(ids)} chains selected · {n} graded · "
        f"{n_unclassified} unclassified hukum · {n_skipped} empty skipped"
    )
    if n == 0:
        print("no gradable chains — aborting")
        return

    cm = confusion_matrix(y_true, y_pred, CLASSES)
    kappa = cohens_kappa(cm, CLASSES)
    wkappa = linear_weighted_kappa(cm, CLASSES)

    print("\n--- Full 4-way (sahih / hasan / daif / mawdu) ---")
    print(f"  Cohen's kappa (unweighted):   {kappa:.4f}")
    print(f"  linear-weighted kappa:        {wkappa:.4f}")
    _report_matrix(cm, CLASSES)
    print("  per-class:")
    pc = per_class_metrics(y_true, y_pred, CLASSES)
    for c in CLASSES:
        m = pc[c]
        print(
            f"    {c:>7}  P={m['precision']:.3f}  R={m['recall']:.3f}  "
            f"F1={m['f1']:.3f}  (n={m['support']})"
        )

    # Collapsed 3-way: classical isnād verdicts are three-tiered.
    collapse = {"sahih": "sahih", "hasan": "hasan", "daif": "weak", "mawdu": "weak"}
    yt3 = [collapse[t] for t in y_true]
    yp3 = [collapse[p] for p in y_pred]
    cm3 = confusion_matrix(yt3, yp3, ["sahih", "hasan", "weak"])
    kappa3 = cohens_kappa(cm3, ["sahih", "hasan", "weak"])
    print("\n--- Collapsed 3-way (sahih / hasan / weak) — apples-to-apples ---")
    print(f"  Cohen's kappa:                {kappa3:.4f}")
    _report_matrix(cm3, ["sahih", "hasan", "weak"])

    # Negative controls
    if not args.no_controls:
        print("\n--- Negative controls (reported beside the real number) ---")
        mode = Counter(y_true).most_common(1)[0][0]
        y_majority = [mode] * n
        cm_maj = confusion_matrix(y_true, y_majority, CLASSES)
        print(f"  majority-class kappa:  {cohens_kappa(cm_maj, CLASSES):.4f}  (predict '{mode}')")

        shuffled_map = _shuffled_rank_map(rng)
        yt_s, yp_s, _, _, _ = _run_pass(iter_chains(args.db, id_set), rank_map=shuffled_map)
        cm_shuf = confusion_matrix(yt_s, yp_s, CLASSES)
        print(
            f"  shuffled-rank kappa:   {cohens_kappa(cm_shuf, CLASSES):.4f}  (rank→grade scrambled)"
        )

    # Error analysis
    print("\n--- Disagreement analysis (the honest part) ---")
    counts = Counter(b for b in buckets if b is not None)
    if counts:
        for label, cnt in counts.most_common():
            print(f"  {cnt:>7}  {label}")
    else:
        print("  (no disagreements)")
    agree = sum(1 for b in buckets if b is None)
    print(f"\n  agreement: {agree}/{n} ({agree / n:.1%})")


if __name__ == "__main__":
    main()
