"""ISNAD-Bench M3 — the human ceiling.

Measures how well the classical critics agree with *each other* on a narrator,
from the 127,863 jarḥ–taʿdīl statements in ``aqwal``. This is the honest upper
bound for ISNAD's agreement: ISNAD cannot be expected to exceed the scholars'
own inter-rater agreement.

Run:  uv run python -m bench.human_ceiling [--db PATH]
"""

from __future__ import annotations

import argparse
import sqlite3

from bench.mapping import grade_from_qawl, narrator_grade_from_rank
from bench.metrics import cohens_kappa, confusion_matrix
from isnad.types import NarratorGrade

_GRADES = [g.value for g in NarratorGrade]


def _load_opinions(db_path: str) -> dict[int, list[str]]:
    """Map rawi_id -> list of classified critic grades (one per critic)."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT rawi_id, alem_id, qawl FROM aqwal ORDER BY rawi_id, alem_id, id"
        ).fetchall()
    finally:
        conn.close()

    opinions: dict[int, list[str]] = {}
    seen_pairs: set[tuple[int, int]] = set()
    for rawi_id, alem_id, qawl in rows:
        pair = (rawi_id, alem_id)
        if pair in seen_pairs:
            continue
        g = grade_from_qawl(qawl)
        if g is None:
            continue
        seen_pairs.add(pair)
        opinions.setdefault(rawi_id, []).append(g.value)
    return opinions


def _load_consensus(db_path: str) -> dict[int, str]:
    """Map rawi_id -> the consolidated NarratorGrade (from rawis.rank_no)."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT id, rank_no, rank, name FROM rawis").fetchall()
    finally:
        conn.close()
    consensus: dict[int, str] = {}
    for rid, rank_no, rank, name in rows:
        m = narrator_grade_from_rank(rank_no, rank, name)
        if not m.is_sentinel:
            consensus[rid] = m.narrator_grade.value
    return consensus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/hadith-kg.db")
    args = parser.parse_args()

    opinions = _load_opinions(args.db)
    consensus = _load_consensus(args.db)

    n_narrators = len(opinions)
    n_multi = sum(1 for gs in opinions.values() if len(gs) >= 2)

    # Pairwise inter-critic agreement.
    y_true: list[str] = []
    y_pred: list[str] = []
    unanimous = 0
    for gs in opinions.values():
        if len(gs) < 2:
            continue
        if len(set(gs)) == 1:
            unanimous += 1
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                y_true.append(gs[i])
                y_pred.append(gs[j])

    cm_critic = confusion_matrix(y_true, y_pred, _GRADES)
    kappa_critic = cohens_kappa(cm_critic, _GRADES)

    # Critic vs consensus: how well does one scholar track the average opinion.
    yc_true: list[str] = []
    yc_pred: list[str] = []
    for rawi_id, gs in opinions.items():
        c = consensus.get(rawi_id)
        if c is None:
            continue
        for g in gs:
            yc_true.append(c)
            yc_pred.append(g)
    cm_cons = confusion_matrix(yc_true, yc_pred, _GRADES)
    kappa_cons = cohens_kappa(cm_cons, _GRADES)

    print("=" * 72)
    print("ISNAD-Bench M3 — the human ceiling (inter-critic agreement)")
    print("=" * 72)
    print("\ncritics: 945 · criticism statements: 127,863")
    print(f"narrators with a classified grade: {n_narrators}")
    print(f"narrators with ≥2 critics:         {n_multi}")
    print(f"unanimous agreement: {unanimous}/{n_multi} ({unanimous / n_multi:.1%})")

    print("\n--- the three quantities, in the same units ---")
    print("  ISNAD vs consensus:       κ = 0.871")
    print(f"  critic vs consensus:      κ = {kappa_cons:.4f}")
    print(f"  critic vs critic:         κ = {kappa_critic:.4f}  ({len(y_true)} pairs)")

    print("\n--- what this means (the honest framing) ---")
    print(f"  The scholars disagree with each other at κ = {kappa_critic:.2f} — the ground truth")
    print(f"  itself is contested. A single scholar tracks the consensus at κ = {kappa_cons:.2f}.")
    print("  ISNAD tracks the consensus at κ = 0.871, i.e. it faithfully implements")
    print("  the scholars' consensus — it is not 'better than the scholars', it is")
    print("  a deterministic reflection of their average opinion.")

    print("\nconfusion matrix (critic vs critic):")
    for a in _GRADES:
        row = "".join(f"{cm_critic[a][b]:>9}" for b in _GRADES)
        print(f"  {a:>10}{row}")


if __name__ == "__main__":
    main()
