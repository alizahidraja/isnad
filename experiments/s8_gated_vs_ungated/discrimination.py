"""§8 chain discrimination — does the chain grade separate corrupted from clean claims?

The paper's core claim is that weaker chains carry more corrupted claims. The old
evidence was a stale single-seed result from a replaced corpus. This measures it
directly on the committed four-book corpus, offline and deterministic, over 10 seeds:

1. **Corruption rate by chain grade** — the direct test of the WHO/WHETHER claim.
2. **Quarantine precision/recall** — of the claims the decision matrix quarantines
   or rejects, how many are actually corrupted.
3. **Chain-only acceptance curve** — rank claims by chain grade alone, serve the top
   X%, and compare served-error to a random (uniform) baseline at matched coverage.

Run:  uv run python experiments/s8_gated_vs_ungated/discrimination.py
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from isnad.core.chain import Chain, ChainLinkSpec, grade_chain_from_registry
from isnad.core.decision import decide
from isnad.core.registry import Registry
from isnad.types import (
    Action,
    AdalahGrade,
    ChainGrade,
    ContentVerdict,
    DabtGrade,
    NarratorGrade,
    TransformType,
)

_EXP_DIR = Path(__file__).resolve().parent
_RESULTS = _EXP_DIR / "results"

_GRADE_ORDER = {
    ChainGrade.SAHIH: 0,
    ChainGrade.HASAN: 1,
    ChainGrade.DAIF: 2,
    ChainGrade.DAIF_JIDDAN: 3,
    ChainGrade.MAWDU: 4,
}
_QUARANTINE_ACTIONS = {Action.QUARANTINE, Action.REJECT_AND_QUARANTINE_NARRATOR}


def _rebuild_chain(claim: dict) -> Chain:
    specs = [
        ChainLinkSpec(
            narrator_id=link["narrator_id"],
            step=link.get("step", i),
            version=link.get("version", "unknown"),
            transform_type=TransformType(link.get("transform_type", "pass_through")),
            domain=link.get("domain", "general"),
        )
        for i, link in enumerate(claim.get("chain_json", []))
    ]
    return Chain(specs)


def _registry_from_snapshot(snap: dict) -> Registry:
    reg = Registry()
    for key, data in snap.items():
        nid, domain = key.split("/", 1)
        reg.register(
            nid,
            domain,
            grade=NarratorGrade(data["grade"]),
            adalah=AdalahGrade(data["adalah"]),
            dabt=DabtGrade(data["dabt"]),
        )
    return reg


def _content_verdicts(eval_claims: list[dict]) -> dict[str, ContentVerdict]:
    """Replicate run.py's TF-IDF semantic critic (dedup by normalized text)."""
    from isnad.critics.embedding import TFIDFIndex, _has_contradiction_signal

    norms = list({c.get("normalized", "") for c in eval_claims if c.get("normalized")})
    verdicts: dict[str, ContentVerdict] = {}
    if len(norms) < 2:
        return dict.fromkeys(norms, ContentVerdict.UNVERIFIABLE)

    idx = TFIDFIndex(norms)
    vecs = [idx.tfidf_vector(t) for t in norms]
    rng = random.Random(42)
    sample_size = min(500, len(norms) - 1)
    for i, norm in enumerate(norms):
        candidates = list(range(len(norms)))
        candidates.remove(i)
        rng.shuffle(candidates)
        sample = candidates[:sample_size]
        best_sim = 0.0
        best_idx = sample[0]
        for j in sample:
            sim = idx.cosine_similarity(vecs[i], vecs[j])
            if sim > best_sim:
                best_sim = sim
                best_idx = j
        if best_sim >= 0.75:
            if _has_contradiction_signal(norm, norms[best_idx]):
                verdicts[norm] = ContentVerdict.CONTRADICTION
            else:
                verdicts[norm] = ContentVerdict.CONSISTENT
        elif best_sim >= 0.50 and _has_contradiction_signal(norm, norms[best_idx]):
            verdicts[norm] = ContentVerdict.CONTRADICTION
        else:
            verdicts[norm] = ContentVerdict.UNVERIFIABLE
    return verdicts


def _analyze() -> dict:
    grade_corruption: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    quarantine = [0, 0]  # [corrupted_quarantined, quarantined]
    reject = [0, 0]  # [corrupted_rejected, rejected]
    # chain-only acceptance curve: per X%, (served, errors) chain-only and random
    curves: dict[str, dict[str, list[int]]] = {"chain_only": {}, "random": {}}
    per_seed: list[dict] = []

    for seed in range(1, 11):
        seed_dir = _RESULTS / f"seed_{seed}"
        gt = {r["claim_id"]: r for r in json.loads((seed_dir / "ground_truth.json").read_text())}
        eval_claims = json.loads((seed_dir / "calibration" / "eval_claims.json").read_text())
        snap = json.loads((seed_dir / "calibration" / "registry_snapshot.json").read_text())
        reg = _registry_from_snapshot(snap)
        verdicts = _content_verdicts(eval_claims)

        rows = []  # (grade_rank, corrupted, action_is_quarantine)
        for claim in eval_claims:
            cid = claim["claim_id"]
            corrupted = bool(gt.get(cid, {}).get("corrupted", False))
            chain = _rebuild_chain(claim)
            cg = grade_chain_from_registry(reg, chain)
            cv = verdicts.get(claim.get("normalized", ""), ContentVerdict.UNVERIFIABLE)
            action = decide(cg, cv)
            grade_corruption[cg.value][1] += 1
            grade_corruption[cg.value][0] += int(corrupted)
            if action in _QUARANTINE_ACTIONS:
                if action == Action.REJECT_AND_QUARANTINE_NARRATOR:
                    reject[1] += 1
                    reject[0] += int(corrupted)
                else:
                    quarantine[1] += 1
                    quarantine[0] += int(corrupted)
            rows.append((_GRADE_ORDER[cg], corrupted))

        # chain-only acceptance curve: serve top X% by grade rank (weakest last)
        rows_sorted = sorted(rows, key=lambda r: r[0])
        rng = random.Random(seed)
        for x in (10, 20, 30, 40, 50):
            k = max(1, int(len(rows) * x / 100))
            served_chain = rows_sorted[:k]
            err_chain = sum(c for _, c in served_chain)
            curves["chain_only"].setdefault(str(x), [0, 0])
            curves["chain_only"][str(x)][0] += len(served_chain)
            curves["chain_only"][str(x)][1] += err_chain
            idx = list(range(len(rows)))
            rng.shuffle(idx)
            served_rand = [rows[i] for i in idx[:k]]
            err_rand = sum(c for _, c in served_rand)
            curves["random"].setdefault(str(x), [0, 0])
            curves["random"][str(x)][0] += len(served_rand)
            curves["random"][str(x)][1] += err_rand

        seed_dist = {g: grade_corruption[g][1] for g in list(grade_corruption)}
        per_seed.append({"seed": seed, "n_eval": len(eval_claims)})

    return {
        "scope": "four-book corpus, 10 seeds, 11,918 eval claims/seed, offline + deterministic",
        "corruption_by_grade": {
            g: {"n": n, "corrupted": c, "rate": round(c / n, 4) if n else None}
            for g, (c, n) in sorted(
                grade_corruption.items(), key=lambda kv: _GRADE_ORDER.get(ChainGrade(kv[0]), 99)
            )
        },
        "quarantine": {
            "quarantined": quarantine[1],
            "quarantined_corrupted": quarantine[0],
            "precision": round(quarantine[0] / quarantine[1], 4) if quarantine[1] else None,
            "rejected": reject[1],
            "rejected_corrupted": reject[0],
        },
        "chain_only_vs_random": {
            x: {
                "chain_only_served_error_rate": round(
                    curves["chain_only"][x][1] / curves["chain_only"][x][0], 4
                ),
                "random_served_error_rate": round(
                    curves["random"][x][1] / curves["random"][x][0], 4
                ),
            }
            for x in ("10", "20", "30", "40", "50")
        },
        "per_seed": per_seed,
    }


def main() -> None:
    report = _analyze()
    out_json = _RESULTS / "discrimination.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"scope: {report['scope']}")
    print("\n--- corruption rate by chain grade (weaker → higher rate = discrimination) ---")
    for g, d in report["corruption_by_grade"].items():
        rate = f"{d['rate']:.3%}" if d["rate"] is not None else "n/a"
        print(f"  {g:12s} n={d['n']:>6,}  corrupted={d['corrupted']:>5,}  rate={rate}")
    q = report["quarantine"]
    print(f"\n--- quarantine ---")
    print(
        f"  quarantined={q['quarantined']:,} corrupted={q['quarantined_corrupted']:,} precision={q['precision']}"
    )
    print(f"  rejected={q['rejected']:,} corrupted={q['rejected_corrupted']:,}")
    print("\n--- chain-only vs random served-error at matched coverage ---")
    for x, d in report["chain_only_vs_random"].items():
        print(
            f"  X={x:>3}%  chain_only={d['chain_only_served_error_rate']:.3%}  random={d['random_served_error_rate']:.3%}"
        )
    print(f"\nwrote {out_json}")


if __name__ == "__main__":
    main()
