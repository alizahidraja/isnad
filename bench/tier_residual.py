"""ISNAD-Bench: what explains the verdicts the weakest tier does not predict?

Paper v2, Blocker 1, step 2. ``tier_check.py`` found per-tier purity of
0.876-0.968 on no-gap-no-rank-12 chains (``max_rank < 12``): the weakest narrator's tier
predicts the chain verdict for most chains, but not all. This script measures,
on the same chains, where the residual comes from instead of assuming it:

1. **Classifier noise.** Agreement between ``chain_grade_from_hukum`` (keywords
   over the free-text ``hukum``) and the source's own structured per-chain code
   ``sanads.matn_no`` (0 sahih, 1 hasan, 2 daif, 3-5 very weak / fabricated).
2. **Purity against ``matn_no``** per tier, with no keyword classifier involved.
3. **Flag enrichment.** Among chains whose verdict differs from their tier's
   modal verdict, the share with a tadlis or ikhtilat narrator, or whose verdict
   text names a defect (tadlis, ikhtilat, irsal, inqita, i'dal, mutaba'a), next
   to the same share among all other chains. A flag is *enriched for* the residual
   if it is much more common there than in the rest — but it still only covers a
   minority of the residual; most residual chains are unexplained by these flags.
4. **Two kappas on the same chains.** A lookup oracle (tier -> modal verdict,
   fit in-sample: the ceiling for any rule that sees only the weakest tier) and
   ISNAD's strict weakest-link grading, each 5-way and 3-way.

Run:  uv run python -m bench.tier_residual --out bench/docs/tier_residual.json
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
from collections.abc import Sequence

from bench._grade import chain_grade_from_narrators, grade_one_chain
from bench.data import iter_chains
from bench.mapping import chain_grade_from_hukum
from bench.metrics import cohens_kappa, confusion_matrix
from bench.run import CLASSES, PINNED_DB_SHA256, verify_db_hash

# sanads.matn_no -> ISNAD class (build_hkg.py: 0 sahih, 1 hasan, 2 daif,
# 3 very weak, 4 accused of fabrication, 5 fabricated).
MATN_NO = {0: "sahih", 1: "hasan", 2: "daif", 3: "mawdu", 4: "mawdu", 5: "mawdu"}

# Defects named in the verdict text, matched after _norm (no diacritics, one alef).
TEXT_MARKERS = {
    "text_tadlis": re.compile("دلس"),
    "text_ikhtilat": re.compile("اختلط|اختلاط"),
    "text_irsal": re.compile("ارسال|مرسل|ارسل"),
    "text_inqita": re.compile("انقطاع|منقطع|لم يسمع|لم يدرك|لم يلق"),
    "text_idal": re.compile("معضل"),
    "text_mutabaa": re.compile("توبع"),
}
FEATURES = ["narrator_tadlis", "narrator_ikhtilat", *TEXT_MARKERS, "any"]
THREE_WAY = {
    "sahih": "sahih",
    "hasan": "hasan",
    "daif": "weak",
    "daif_jiddan": "weak",
    "mawdu": "weak",
}


def _norm(text: str | None) -> str:
    text = re.sub("[ً-ْٰـ]", "", text or "")
    return re.sub("[إأآ]", "ا", text)


def _kappas(y_true: Sequence[str], y_pred: Sequence[str]) -> dict[str, float]:
    k4 = cohens_kappa(confusion_matrix(y_true, y_pred, CLASSES), CLASSES)
    t3 = [THREE_WAY[y] for y in y_true]
    p3 = [THREE_WAY[y] for y in y_pred]
    classes3 = ["sahih", "hasan", "weak"]
    k3 = cohens_kappa(confusion_matrix(t3, p3, classes3), classes3)
    return {"kappa_5way": round(k4, 4), "kappa_3way": round(k3, 4)}


def _load(db_path: str) -> tuple[dict[int, tuple[int, str, int]], dict[int, list[bool]]]:
    conn = sqlite3.connect(db_path)
    try:
        rawi_flags = {
            rid: (bool(t), bool(i))
            for rid, t, i in conn.execute("SELECT id, has_tadlis, has_ikhtilat FROM rawis")
        }
        sanads = {
            sid: (rank, hukum, matn_no)
            for sid, rank, hukum, matn_no in conn.execute(
                "SELECT id, max_rank, hukum, matn_no FROM sanads WHERE max_rank < 12"
            )
        }
        chain_flags: dict[int, list[bool]] = {}
        for sid, rid in conn.execute("SELECT sanad_id, rawi_id FROM sanad_rawis"):
            if sid not in sanads:
                continue
            t, i = rawi_flags.get(rid, (False, False))
            cf = chain_flags.setdefault(sid, [False, False])
            cf[0] = cf[0] or t
            cf[1] = cf[1] or i
    finally:
        conn.close()
    return sanads, chain_flags


def analyse(db_path: str) -> dict[str, object]:
    sanads, chain_flags = _load(db_path)

    verdict: dict[int, str] = {}
    for sid, (_rank, hukum, _code) in sanads.items():
        g = chain_grade_from_hukum(hukum)
        if g is not None:
            verdict[sid] = g.value
    order = sorted(verdict)

    # 1. keyword classifier vs the source's structured code
    coded = [s for s in order if sanads[s][2] in MATN_NO]
    agree = sum(verdict[s] == MATN_NO[sanads[s][2]] for s in coded)
    disagreement: collections.Counter[tuple[str, str]] = collections.Counter()
    for s in coded:
        expected = MATN_NO[sanads[s][2]]
        if verdict[s] != expected:
            disagreement[(expected, verdict[s])] += 1

    # 2. purity per tier, by classifier and by structured code
    by_cls: dict[int, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    by_code: dict[int, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for s in order:
        by_cls[sanads[s][0]][verdict[s]] += 1
    for _s, (rank, _hukum, code) in sanads.items():
        by_code[rank][MATN_NO.get(code, "other")] += 1
    modal = {t: c.most_common(1)[0][0] for t, c in by_cls.items()}
    tiers = []
    for t in sorted(by_cls):
        n_cls = sum(by_cls[t].values())
        n_code = sum(by_code[t].values())
        tiers.append({
            "tier": t,
            "n": n_cls,
            "modal": modal[t],
            "purity_classifier": round(by_cls[t][modal[t]] / n_cls, 4),
            "purity_matn_no": round(by_code[t].most_common(1)[0][1] / n_code, 4),
            "modal_matn_no": by_code[t].most_common(1)[0][0],
        })

    # 3. flag enrichment: residual (verdict != tier's modal) vs the rest
    n_group: collections.Counter[str] = collections.Counter()
    hits: dict[str, collections.Counter[str]] = {
        "residual": collections.Counter(),
        "rest": collections.Counter(),
    }
    for s in order:
        group = "residual" if verdict[s] != modal[sanads[s][0]] else "rest"
        n_group[group] += 1
        tadlis, ikhtilat = chain_flags.get(s, [False, False])
        hit = {"narrator_tadlis": tadlis, "narrator_ikhtilat": ikhtilat}
        text = _norm(sanads[s][1])
        for name, rx in TEXT_MARKERS.items():
            hit[name] = bool(rx.search(text))
        hit["any"] = any(hit.values())
        for name, value in hit.items():
            hits[group][name] += int(value)
    enrichment = {}
    for name in FEATURES:
        share_res = hits["residual"][name] / n_group["residual"] if n_group["residual"] else 0.0
        share_rest = hits["rest"][name] / n_group["rest"] if n_group["rest"] else 0.0
        enrichment[name] = {
            "share_residual": round(share_res, 4),
            "share_rest": round(share_rest, 4),
            "ratio": round(share_res / share_rest, 2) if share_rest else None,
        }

    # 4. lookup-oracle ceiling vs ISNAD strict, on the same chains
    oracle = _kappas([verdict[s] for s in order], [modal[sanads[s][0]] for s in order])
    preds: dict[int, str] = {}
    for chain in iter_chains(db_path, set(order)):
        grades, is_complete, _r, _t, _g, adalah = grade_one_chain(chain.nodes)
        if grades:
            preds[chain.sanad_id] = chain_grade_from_narrators(
                grades, is_complete, adalah_grades=adalah
            )
    common = [s for s in order if s in preds]
    isnad = _kappas([verdict[s] for s in common], [preds[s] for s in common])

    return {
        "scope": "no-gap, no-rank-12 chains (max_rank < 12), keyword-readable verdicts",
        "n_chains": len(sanads),
        "n_classified": len(order),
        "classifier_vs_matn_no": {
            "n": len(coded),
            "agreement": round(agree / len(coded), 4) if coded else None,
            "disagreement_buckets": [
                {"matn_no": a, "classifier": b, "n": n}
                for (a, b), n in sorted(disagreement.items(), key=lambda kv: -kv[1])
            ],
        },
        "tiers": tiers,
        "residual": {"n_residual": n_group["residual"], "n_rest": n_group["rest"]},
        "enrichment": enrichment,
        "lookup_oracle": oracle,
        "isnad_strict": {**isnad, "n": len(common)},
    }


def _print(report: dict[str, object]) -> None:
    print(f"scope: {report['scope']}")
    print(f"chains {report['n_chains']:,} · classified {report['n_classified']:,}")
    cvm = report["classifier_vs_matn_no"]
    print(f"keyword classifier vs matn_no: {cvm['agreement']} agreement on {cvm['n']:,}")  # type: ignore[index]
    print("\ntier      n  modal  purity(classifier)  purity(matn_no)")
    for t in report["tiers"]:  # type: ignore[attr-defined]
        print(
            f"{t['tier']:>4} {t['n']:>8,}  {t['modal']:<6} {t['purity_classifier']:>10}"
            f"  {t['purity_matn_no']:>16} ({t['modal_matn_no']})"
        )
    res = report["residual"]
    print(f"\nresidual {res['n_residual']:,} vs rest {res['n_rest']:,}")  # type: ignore[index]
    print("feature               residual   rest    ratio")
    for name, e in report["enrichment"].items():  # type: ignore[attr-defined]
        print(f"{name:<20} {e['share_residual']:>8} {e['share_rest']:>7} {e['ratio']!s:>7}")
    print(f"\nlookup oracle (in-sample ceiling): {report['lookup_oracle']}")
    print(f"ISNAD strict, same chains:         {report['isnad_strict']}")


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
