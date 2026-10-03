"""ISNAD-Bench: held-out + full-corpus lookup oracle (de-circularizes Blocker 1).

``bench/tier_residual.py`` showed ISNAD's strict kappa equals an *in-sample*
tier->modal lookup oracle on gap-free chains (``max_rank < 12``). Two questions
the review panel flagged remain open; this script answers them:

1. **Held-out.** Is the tier->modal map stable out of sample? Fit the map on a
   train split (even ``sanad_id``) and score ISNAD and the held-out oracle on the
   disjoint test split (odd ``sanad_id``). If the held-out oracle still matches
   ISNAD, the equality is not an overfit artifact of fitting on the same chains.
2. **Full corpus.** What is the lookup ceiling over ALL chains (including gapped,
   ``max_rank >= 12`` -> daif, the continuity cap), next to ISNAD's headline
   kappa = 0.871? tier_residual only compared on the gap-free subset.

Run:  uv run python -m bench.tier_oracle --out bench/docs/tier_oracle.json

Note: the per-tier purity range 0.88-0.97 quoted in the paper EXCLUDES tier 1,
whose modal is estimated from only n=3 chains (purity 0.6667) — too small to
treat as a stable tier->verdict map.
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
from collections.abc import Sequence
from typing import cast

from bench._grade import chain_grade_from_narrators, grade_one_chain
from bench.data import iter_chains
from bench.mapping import chain_grade_from_hukum
from bench.metrics import cohens_kappa, confusion_matrix
from bench.run import CLASSES, PINNED_DB_SHA256, verify_db_hash

THREE_WAY = {"sahih": "sahih", "hasan": "hasan", "daif": "weak", "mawdu": "weak"}


def _kappas(y_true: Sequence[str], y_pred: Sequence[str]) -> dict[str, float]:
    k4 = cohens_kappa(confusion_matrix(y_true, y_pred, CLASSES), CLASSES)
    t3 = [THREE_WAY[y] for y in y_true]
    p3 = [THREE_WAY[y] for y in y_pred]
    classes3 = ["sahih", "hasan", "weak"]
    k3 = cohens_kappa(confusion_matrix(t3, p3, classes3), classes3)
    return {"kappa_4way": round(k4, 4), "kappa_3way": round(k3, 4)}


def _modal(tiers: dict[int, collections.Counter[str]]) -> dict[int, str]:
    return {t: c.most_common(1)[0][0] for t, c in tiers.items()}


def analyse(db_path: str) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT id, max_rank, hukum, matn_no FROM sanads").fetchall()
    finally:
        conn.close()

    sanads: dict[int, tuple[int, str | None, int | None]] = {
        sid: (max_rank, hukum, matn_no) for sid, max_rank, hukum, matn_no in rows
    }
    verdict: dict[int, str] = {}
    for sid, (_rank, hukum, _code) in sanads.items():
        g = chain_grade_from_hukum(hukum)
        if g is not None:
            verdict[sid] = g.value

    # tier -> modal verdict, fit on gap-free chains only (max_rank < 12).
    by_tier: dict[int, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    gap_free = [s for s in verdict if sanads[s][0] < 12]
    gapped = [s for s in verdict if sanads[s][0] >= 12]
    for s in gap_free:
        by_tier[sanads[s][0]][verdict[s]] += 1
    modal = _modal(by_tier)

    # ---- held-out: fit modal on even ids, score on odd ids ----
    train = [s for s in gap_free if s % 2 == 0]
    test = [s for s in gap_free if s % 2 == 1]
    by_tier_train: dict[int, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    for s in train:
        by_tier_train[sanads[s][0]][verdict[s]] += 1
    modal_train = _modal(by_tier_train)

    # ---- ISNAD grades over all classified chains ----
    preds: dict[int, str] = {}
    for chain in iter_chains(db_path, set(verdict)):
        grades, is_complete, _r, _t, _g, adalah = grade_one_chain(chain.nodes)
        if grades:
            preds[chain.sanad_id] = chain_grade_from_narrators(
                grades, is_complete, adalah_grades=adalah
            )

    def _score(ids: Sequence[int], oracle_from: dict[int, str]) -> dict[str, object]:
        ids = [s for s in ids if s in preds]
        true = [verdict[s] for s in ids]
        isnad_pred = [preds[s] for s in ids]
        oracle_pred = [
            "daif" if sanads[s][0] >= 12 else oracle_from.get(sanads[s][0], "daif") for s in ids
        ]
        agree = sum(1 for a, b in zip(isnad_pred, oracle_pred, strict=True) if a == b)
        tier_marginal = dict(collections.Counter(sanads[s][0] for s in ids))
        verdict_marginal = dict(collections.Counter(verdict[s] for s in ids))
        return {
            "n": len(ids),
            "lookup_oracle": _kappas(true, oracle_pred),
            "isnad_strict": _kappas(true, isnad_pred),
            "isnad_vs_oracle_agreement": round(agree / len(ids), 4) if ids else None,
            "isnad_vs_oracle_confusion": confusion_matrix(oracle_pred, isnad_pred, CLASSES),
            "tier_marginal": tier_marginal,
            "verdict_marginal": verdict_marginal,
        }

    return {
        "scope": "all chains with a readable free-text hukum, max_rank sentinel >= 12 -> daif",
        "n_chains": len(sanads),
        "n_classified": len(verdict),
        "n_gap_free": len(gap_free),
        "n_gapped": len(gapped),
        "heldout_train_even_ids": _score(train, modal_train),
        "heldout_test_odd_ids": _score(test, modal_train),
        "full_corpus_in_sample_modal": _score(list(verdict), modal),
    }


def _print(report: dict[str, object]) -> None:
    print(f"scope: {report['scope']}")
    print(
        f"chains {report['n_chains']:,} · classified {report['n_classified']:,} "
        f"(gap-free {report['n_gap_free']:,}, gapped {report['n_gapped']:,})"
    )
    for label in ("heldout_train_even_ids", "heldout_test_odd_ids", "full_corpus_in_sample_modal"):
        r = cast(dict[str, object], report[label])
        print(f"\n{label}: n={r['n']:,}")
        print(f"  lookup oracle  {r['lookup_oracle']}")
        print(f"  ISNAD strict   {r['isnad_strict']}")
        print(f"  ISNAD==oracle agreement  {r['isnad_vs_oracle_agreement']}")
        print(f"  tier marginal  {r['tier_marginal']}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default="data/hadith-kg.db")
    ap.add_argument("--out", help="write the report as JSON (commit it as the artifact)")
    ap.add_argument("--skip-hash", action="store_true", help="tests only: skip the DB pin")
    args = ap.parse_args(argv)

    db_hash = "skipped" if args.skip_hash else verify_db_hash(args.db)
    report = analyse(args.db)
    report["db_sha256"] = db_hash
    report["pinned_sha256"] = PINNED_DB_SHA256
    _print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
