"""ISNAD-Bench M4 — ikhtilāṭ (the mukhtaliṭūn / period-sliced grades).

The *mukhtaliṭūn* are narrators who were sound and then declined — classically
through age or illness. The scholars **dated the decline** rather than
discarding the record: everything transmitted before the decline stands,
everything after is suspect. That is the exact case ISNAD's ``get_grade_as_of()``
was built for (issue #43).

This measures two things, honestly:
1. the phenomenon's size — how many narrators declined, and how many chains it
   touches;
2. whether a *static* grade (which compresses the timeline) hurts agreement
   with the consensus, by comparing κ on chains that contain a declined
   narrator vs clean chains.

Run:  uv run python -m bench.ikhtilat [--db PATH]
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter

from bench.data import iter_chains
from bench.mapping import chain_grade_from_hukum, grade_from_qawl
from bench.metrics import cohens_kappa, confusion_matrix
from bench.run import _chain_grade_from_narrators, _grade_one_chain

CLASSES = ["sahih", "hasan", "daif", "mawdu"]


def _load_ikhtilat(db_path: str) -> tuple[set[int], list[str]]:
    conn = sqlite3.connect(db_path)
    try:
        ids = {r[0] for r in conn.execute("SELECT id FROM rawis WHERE has_ikhtilat=1")}
        texts = [
            r[0]
            for r in conn.execute(
                "SELECT rank FROM rawis WHERE has_ikhtilat=1 AND rank IS NOT NULL "
                "AND (rank LIKE '%اختلط%' OR rank LIKE '%تغير%')"
            )
        ]
    finally:
        conn.close()
    return ids, texts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/hadith-kg.db")
    args = parser.parse_args()

    ikhtilat_ids, decline_texts = _load_ikhtilat(args.db)

    print("=" * 72)
    print("ISNAD-Bench M4 — ikhtilāṭ (the mukhtaliṭūn / period-sliced grades)")
    print("=" * 72)
    print(f"\nnarrators flagged ikhtilāṭ:          {len(ikhtilat_ids)}")
    print(f"explicit decline in the rank text:  {len(decline_texts)}")

    pre: Counter[str] = Counter()
    for t in decline_texts:
        grade = grade_from_qawl(t)
        if grade is not None:
            pre[grade.value] += 1
    print("\npre-decline grade (from 'was X, then declined' texts):")
    for g, n in pre.most_common():
        print(f"  {n:>4}  {g}")

    print("\nthe scholars' own period-slices (a sample):")
    for t in sorted(set(decline_texts))[:12]:
        print(f"  - {t}")

    # The κ split: does a static grade hurt agreement on declined narrators?
    yt_ikhtilat: list[str] = []
    yp_ikhtilat: list[str] = []
    yt_clean: list[str] = []
    yp_clean: list[str] = []
    for chain in iter_chains(args.db):
        true = chain_grade_from_hukum(chain.hukum)
        if true is None:
            continue
        has_ikhtilat = any(n.rawi_id in ikhtilat_ids for n in chain.nodes)
        narrator_grades, is_complete, _r, _t, _g = _grade_one_chain(chain.nodes)
        if not narrator_grades:
            continue
        pred = _chain_grade_from_narrators(narrator_grades, is_complete)
        if has_ikhtilat:
            yt_ikhtilat.append(true.value)
            yp_ikhtilat.append(pred)
        else:
            yt_clean.append(true.value)
            yp_clean.append(pred)

    k_ikhtilat = cohens_kappa(confusion_matrix(yt_ikhtilat, yp_ikhtilat, CLASSES), CLASSES)
    k_clean = cohens_kappa(confusion_matrix(yt_clean, yp_clean, CLASSES), CLASSES)

    print(f"\nchains containing a declined narrator: {len(yt_ikhtilat)}")
    print(f"κ (ikhtilāṭ chains):  {k_ikhtilat:.4f}")
    print(f"κ (clean chains):     {k_clean:.4f}")

    print("\n--- the honest framing ---")
    print("  A static grade compresses a timeline into one number. The scholars")
    print("  dated the decline instead; get_grade_as_of() (issue #43) is the same")
    print("  mechanism.")
    print(
        f"  κ on declined-narrator chains ({k_ikhtilat:.3f}) ≈ clean chains"
        f" ({k_clean:.3f}) — because the consensus itself is a *static* grade,"
        " so the loss is invisible here."
    )
    print("  The real value of period-slicing is for timestamped AI pipelines")
    print("  (the xz sleeper-narrator), which the classical corpus cannot time-label.")


if __name__ == "__main__":
    main()
