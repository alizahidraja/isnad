"""ISNAD-Bench: measure ISNAD's chain grading against classical ground truth.

Run:  uv run python -m bench.run [--db PATH] [--limit N | --sample N]
      uv run python -m bench.run --lenient        # ungraded → ḥasan (opt-in)

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
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence

from bench._grade import (
    bucket as _bucket,
)
from bench._grade import (
    chain_grade_from_narrators as _chain_grade_from_narrators,
)
from bench._grade import (
    grade_one_chain as _grade_one_chain,
)
from bench._grade import (
    independence_set as _independence_set,
)
from bench.data import RawChain, iter_chains
from bench.mapping import chain_grade_from_hukum, narrator_grade_from_rank
from bench.metrics import (
    cohens_kappa,
    confusion_matrix,
    linear_weighted_kappa,
    per_class_metrics,
)
from isnad.types import ChainGrade, NarratorGrade

CLASSES = [g.value for g in (ChainGrade.SAHIH, ChainGrade.HASAN, ChainGrade.DAIF, ChainGrade.MAWDU)]

# Sentinel names (gap markers) → whether the gap is the grade-preserving taʿlīq
# form or a genuine break (irsāl / inqiṭāʿ).
_TALIQ = "موضع تعليق"

# The corroboration bucket label (must match _bucket exactly).
_CORROBORATION_BUCKET = "corroboration: weak-alone → ḥasan-with-mutābaʿa"

_GradeResult = tuple[list[NarratorGrade], bool, list[int], bool, bool]


def _load_sanad_ids(db_path: str) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT id FROM sanads")]
    finally:
        conn.close()


def _shuffled_rank_map(rng: random.Random) -> dict[int, NarratorGrade]:
    """A random permutation of the rank→grade assignment (negative control)."""
    grades = [narrator_grade_from_rank(rn).narrator_grade for rn in range(1, 13)]
    rng.shuffle(grades)
    return dict(zip(range(1, 13), grades, strict=True))


_PassResult = tuple[list[str], list[str], list[str | None], int, int]


def _run_pass(
    chains: Iterator[RawChain],
    rank_map: dict[int, NarratorGrade] | None = None,
    lenient_unknown: bool = False,
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
        pred = _chain_grade_from_narrators(narrator_grades, is_complete, lenient_unknown)
        y_true.append(true.value)
        y_pred.append(pred)
        buckets.append(_bucket(true.value, pred, has_gap, has_taliq, rank_nos, chain.hukum))
    return y_true, y_pred, buckets, n_unclassified, n_skipped_empty


def _corroboration_analysis(
    db_path: str, id_set: set[int], lenient_unknown: bool
) -> tuple[int, int]:
    """For each "weak-alone → ḥasan" chain, does an independent route exist?

    Classical "ḍaʿīf, becomes ḥasan if corroborated" is a *conditional* verdict.
    This answers: how many of the chains ISNAD over-grades actually have an
    independent corroborating route (same meaning group, disjoint non-companion
    narrators) — i.e. how many would classical scholars *also* grade ḥasan, via
    mutābaʿa, if corroboration were taken into account.
    """
    routes: dict[int | None, list[frozenset[int]]] = defaultdict(list)
    weak_alone: list[tuple[int | None, frozenset[int]]] = []
    for chain in iter_chains(db_path, id_set):
        true = chain_grade_from_hukum(chain.hukum)
        if true is None:
            continue
        indep = _independence_set(chain.nodes)
        routes[chain.group_id].append(indep)
        narrator_grades, is_complete, _rank_nos, _taliq, _gap = _grade_one_chain(chain.nodes)
        if not narrator_grades:
            continue
        pred = _chain_grade_from_narrators(narrator_grades, is_complete, lenient_unknown)
        if true.value == "daif" and pred in ("hasan", "sahih") and "توبع" in (chain.hukum or ""):
            weak_alone.append((chain.group_id, indep))

    independent = 0
    for gid, indep in weak_alone:
        for other in routes.get(gid, []):
            if other != indep and other.isdisjoint(indep):
                independent += 1
                break
    return len(weak_alone), independent


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
    parser.add_argument("--lenient", action="store_true", help="UNGRADED → ḥasan (opt-in)")
    parser.add_argument("--no-controls", action="store_true", help="skip negative controls")
    parser.add_argument("--no-corroboration", action="store_true", help="skip mutābaʿa ablation")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    if not args.json:
        print("=" * 72)
        print("ISNAD-Bench: chain-grade agreement vs classical ground truth")
        if args.lenient:
            print("mode: lenient (ungraded narrator → ḥasan ceiling, opt-in)")
        else:
            print("mode: STRICT (ungraded narrator → ḍaʿīf, classical majhūl — default)")
        print("=" * 72)

    all_ids = _load_sanad_ids(args.db)
    if args.sample is not None:
        ids = rng.sample(all_ids, args.sample)
    elif args.limit is not None:
        ids = all_ids[: args.limit]
    else:
        ids = all_ids
    id_set = set(ids)

    y_true, y_pred, buckets, n_unclassified, n_skipped = _run_pass(
        iter_chains(args.db, id_set), lenient_unknown=args.lenient
    )

    n = len(y_true)
    if not args.json:
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
    pc = per_class_metrics(y_true, y_pred, CLASSES)

    # Collapsed 3-way: classical isnād verdicts are three-tiered.
    collapse = {"sahih": "sahih", "hasan": "hasan", "daif": "weak", "mawdu": "weak"}
    yt3 = [collapse[t] for t in y_true]
    yp3 = [collapse[p] for p in y_pred]
    cm3 = confusion_matrix(yt3, yp3, ["sahih", "hasan", "weak"])
    kappa3 = cohens_kappa(cm3, ["sahih", "hasan", "weak"])

    majority_kappa: float | None = None
    shuffled_kappa: float | None = None
    mode: str | None = None
    if not args.no_controls:
        mode = Counter(y_true).most_common(1)[0][0]
        cm_maj = confusion_matrix(y_true, [mode] * n, CLASSES)
        majority_kappa = cohens_kappa(cm_maj, CLASSES)
        shuffled_map = _shuffled_rank_map(rng)
        yt_s, yp_s, _, _, _ = _run_pass(
            iter_chains(args.db, id_set), rank_map=shuffled_map, lenient_unknown=args.lenient
        )
        cm_shuf = confusion_matrix(yt_s, yp_s, CLASSES)
        shuffled_kappa = cohens_kappa(cm_shuf, CLASSES)

    n_wa: int | None = None
    n_ind: int | None = None
    if not args.no_corroboration:
        n_wa, n_ind = _corroboration_analysis(args.db, id_set, args.lenient)

    counts = Counter(b for b in buckets if b is not None)
    agree = sum(1 for b in buckets if b is None)

    if args.json:
        import json

        summary = {
            "mode": "lenient" if args.lenient else "strict",
            "chains_selected": len(ids),
            "chains_graded": n,
            "unclassified_hukum": n_unclassified,
            "empty_skipped": n_skipped,
            "kappa_4way": kappa,
            "kappa_linear_weighted": wkappa,
            "kappa_3way": kappa3,
            "agreement": agree / n,
            "per_class": pc,
            "controls": {"majority_kappa": majority_kappa, "shuffled_kappa": shuffled_kappa},
            "corroboration": {"weak_alone": n_wa, "independent_route": n_ind},
            "disagreement_buckets": dict(counts),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    print("\n--- Full 4-way (sahih / hasan / daif / mawdu) ---")
    print(f"  Cohen's kappa (unweighted):   {kappa:.4f}")
    print(f"  linear-weighted kappa:        {wkappa:.4f}")
    _report_matrix(cm, CLASSES)
    print("  per-class:")
    for c in CLASSES:
        m = pc[c]
        print(
            f"    {c:>7}  P={m['precision']:.3f}  R={m['recall']:.3f}  "
            f"F1={m['f1']:.3f}  (n={m['support']})"
        )

    print("\n--- Collapsed 3-way (sahih / hasan / weak) — apples-to-apples ---")
    print(f"  Cohen's kappa:                {kappa3:.4f}")
    _report_matrix(cm3, ["sahih", "hasan", "weak"])

    if not args.no_controls:
        print("\n--- Negative controls (reported beside the real number) ---")
        print(f"  majority-class kappa:  {majority_kappa:.4f}  (predict '{mode}')")
        print(f"  shuffled-rank kappa:   {shuffled_kappa:.4f}  (rank→grade scrambled)")

    if not args.no_corroboration:
        print("\n--- Corroboration ablation (mutābaʿa) ---")
        if n_wa and n_ind is not None:
            print(f"  weak-alone → ḥasan chains:            {n_wa}")
            print(f"  with an independent corroborating route: {n_ind} ({n_ind / n_wa:.1%})")
            print("  → classical scholars would grade those ḥasan via mutābaʿa; the")
            print("    remainder are chains ISNAD over-grades without corroboration.")

    print("\n--- Disagreement analysis (the honest part) ---")
    if counts:
        for label, cnt in counts.most_common():
            print(f"  {cnt:>7}  {label}")
    else:
        print("  (no disagreements)")
    print(f"\n  agreement: {agree}/{n} ({agree / n:.1%})")


if __name__ == "__main__":
    main()
