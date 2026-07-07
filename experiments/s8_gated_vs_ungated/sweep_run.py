"""Transition-policy sweep for the §8 experiment.

Sweeps downgrade thresholds ∈ {3, 6, 10, 15, 25} and measures:
- ISNAD-gated coverage at B=10%
- ISNAD-gated served-error rate
- Grade-recovery accuracy (how many narrators correctly graded)
- Review precision

Uses the ConfigurableTransitionPolicy through the framework's public API.
Does NOT edit framework code.

Output: results/sweep_results.json + results/sweep_curve.csv
"""

from __future__ import annotations

import json
import os
import random
import sys
from collections import defaultdict

_exp_dir = os.path.dirname(os.path.abspath(__file__))
if _exp_dir not in sys.path:
    sys.path.insert(0, _exp_dir)

from isnad.chain import Chain, ChainLinkSpec
from isnad.grading import grade_chain
from isnad.matn import DeterministicRuleCritic
from isnad.matrix import decide
from isnad.registry import Registry
from isnad.types import (
    Action,
    ContentVerdict,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    TransformType,
)
from sweep_policy import ConfigurableTransitionPolicy

# Designed fault rates for grade-recovery scoring
DESIGNED_RATES: dict[str, float] = {
    "pdf-scraper@1.2": 0.01,
    "pdf-scraper@0.9-legacy": 0.18,
    "ingest@good": 0.02,
    "ingest@weak": 0.15,
}


def calibrate_with_policy(
    cal_claims: list[dict],
    gt_lookup: dict[str, dict],
    domains: list[str],
    audit_budget: int,
    downgrade_threshold: int,
    seed: int,
) -> Registry:
    """Run calibration with a specific downgrade threshold."""
    rng = random.Random(seed)
    policy = ConfigurableTransitionPolicy(downgrade_threshold=downgrade_threshold)
    reg = Registry(transition_policy=policy)

    narrator_ids: set[str] = set()
    for c in cal_claims:
        for nid in [c.get("assigned_scraper", ""), c.get("assigned_ingest", "")]:
            if nid:
                narrator_ids.add(nid)

    for nid in narrator_ids:
        for domain in domains:
            reg.register(nid, domain)

    by_nd: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in cal_claims:
        for nid in [c.get("assigned_scraper", ""), c.get("assigned_ingest", "")]:
            if nid:
                by_nd[(nid, c.get("domain", "general"))].append(c)

    for (nid, domain), claims in by_nd.items():
        rng.shuffle(claims)
        audited = claims[:audit_budget]
        correct = 0
        for c in audited:
            gt = gt_lookup.get(c["claim_id"])
            if gt is None:
                continue
            if gt.get("corrupted", False):
                reg.record_evidence(nid, domain, EvidenceType.POST_HOC_AUDIT,
                                    EvidenceAction.JARH, "defective")
            else:
                correct += 1
                reg.record_evidence(nid, domain, EvidenceType.POST_HOC_AUDIT,
                                    EvidenceAction.TADIL, "correct")
        if correct >= max(1, len(audited)) * 0.7:
            for _ in range(2):
                reg.record_evidence(nid, domain, EvidenceType.CORROBORATION_OUTCOME,
                                    EvidenceAction.TADIL, "sustained")

    return reg


def evaluate_isnad_gated(
    eval_claims: list[dict],
    gt_lookup: dict[str, dict],
    reg: Registry,
    budget: float = 0.10,
) -> dict:
    """Run ISNAD-gated serving and return metrics."""
    n = len(eval_claims)
    review_budget = max(1, int(n * budget))
    critic = DeterministicRuleCritic()

    graded = []
    for c in eval_claims:
        chain = _rebuild_chain(c)
        grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
        xforms = [l.transform_type for l in chain.links]
        cg = grade_chain(grades, xforms, is_complete=c.get("chain_complete", True))
        action = decide(cg, ContentVerdict.UNVERIFIABLE)
        graded.append((c, cg.value, action))

    graded.sort(key=lambda x: _action_priority(x[2]))

    served = 0
    errors = 0
    reviewed = 0
    reviewed_defective = 0
    for claim, _, action in graded:
        gt = gt_lookup.get(claim["claim_id"], {})
        if action in (Action.REJECT_AND_QUARANTINE_NARRATOR, Action.QUARANTINE):
            continue
        if action == Action.REVIEW and reviewed < review_budget:
            reviewed += 1
            served += 1
            if gt.get("corrupted", False):
                reviewed_defective += 1
            continue
        if action in (Action.SERVE, Action.SERVE_WITH_CAVEAT):
            served += 1
            if gt.get("corrupted", False):
                errors += 1
            continue

    return {
        "coverage": served / max(1, n),
        "served_error_rate": errors / max(1, served),
        "reviewed": reviewed,
        "review_precision": reviewed_defective / max(1, reviewed),
        "errors_served": errors,
    }


def grade_recovery_score(reg: Registry, domains: list[str]) -> dict:
    """Compute grade-recovery accuracy."""
    narrator_ids = ["pdf-scraper@1.2", "pdf-scraper@0.9-legacy",
                    "ingest@good", "ingest@weak"]
    results = {}
    correct = 0
    for nid in narrator_ids:
        grades = []
        for domain in domains:
            grades.append(reg.get_grade(nid, domain))
        # For good narrators (rate <= 2%): should be RELIABLE or ACCEPTABLE
        # For bad narrators (rate >= 15%): should be WEAK or REJECTED
        rate = DESIGNED_RATES.get(nid, 0.5)
        good_grade_count = sum(1 for g in grades
                               if g in (NarratorGrade.RELIABLE, NarratorGrade.ACCEPTABLE))
        bad_grade_count = sum(1 for g in grades
                              if g in (NarratorGrade.REJECTED, NarratorGrade.WEAK))
        total = len(grades)

        if rate <= 0.05:
            ok = good_grade_count >= total * 0.3
        else:
            ok = bad_grade_count >= total * 0.3

        if ok:
            correct += 1
        results[nid] = {
            "designed_rate": rate,
            "good_grades": good_grade_count,
            "bad_grades": bad_grade_count,
            "total": total,
            "approximately_correct": ok,
        }

    results["recovery_score"] = f"{correct}/{len(narrator_ids)}"
    return results


def _rebuild_chain(claim: dict) -> Chain:
    links = claim.get("chain_json", [])
    specs = []
    for i, link in enumerate(links):
        specs.append(ChainLinkSpec(
            narrator_id=link["narrator_id"], step=i,
            transform_type=TransformType(link.get("transform_type", "pass_through")),
            domain=link.get("domain", "general"),
        ))
    return Chain(specs)


def _action_priority(action: Action) -> int:
    p = {Action.REVIEW: 0, Action.SERVE_WITH_CAVEAT: 1, Action.SERVE: 99}
    return p.get(action, 50)


def main() -> None:
    results_dir = os.path.join(_exp_dir, "results")
    domains = ["mechanics", "electromagnetism", "optics-waves", "modern-quantum", "general"]
    thresholds = [3, 6, 10, 15, 25]

    # Use seed 1 data for the sweep
    seed_dir = os.path.join(results_dir, "seed_1")
    cal_path = os.path.join(seed_dir, "calibration", "cal_claims.json")
    eval_path = os.path.join(seed_dir, "calibration", "eval_claims.json")
    gt_path = os.path.join(seed_dir, "ground_truth.json")

    if not all(os.path.exists(p) for p in [cal_path, eval_path, gt_path]):
        print("Missing data. Run inject.py and calibrate.py first.")
        return

    with open(cal_path) as f:
        cal_claims = json.load(f)
    with open(eval_path) as f:
        eval_claims = json.load(f)
    with open(gt_path) as f:
        gt_lookup = {r["claim_id"]: r for r in json.load(f)}

    print(f"Calibration claims: {len(cal_claims)}")
    print(f"Evaluation claims:  {len(eval_claims)}")
    print(f"Domains: {domains}")
    print()

    all_sweep: list[dict] = []

    for thresh in thresholds:
        reg = calibrate_with_policy(cal_claims, gt_lookup, domains, 40, thresh, seed=42)
        metrics = evaluate_isnad_gated(eval_claims, gt_lookup, reg)
        recovery = grade_recovery_score(reg, domains)

        entry = {
            "downgrade_threshold": thresh,
            "coverage": metrics["coverage"],
            "served_error_rate": metrics["served_error_rate"],
            "review_precision": metrics["review_precision"],
            "recovery_score": recovery["recovery_score"],
        }
        all_sweep.append(entry)

        print(f"threshold={thresh:>2d}  "
              f"coverage={metrics['coverage']:.3f}  "
              f"error={metrics['served_error_rate']:.4f}  "
              f"recovery={recovery['recovery_score']}  "
              f"prec={metrics['review_precision']:.3f}")

    # Save
    sweep_path = os.path.join(results_dir, "sweep_results.json")
    with open(sweep_path, "w") as f:
        json.dump(all_sweep, f, indent=2)

    csv_path = os.path.join(results_dir, "sweep_curve.csv")
    with open(csv_path, "w") as f:
        f.write("threshold,coverage,served_error_rate,review_precision,recovery_score\n")
        for e in all_sweep:
            f.write(f"{e['downgrade_threshold']},{e['coverage']:.4f},"
                    f"{e['served_error_rate']:.4f},{e['review_precision']:.3f},"
                    f"{e['recovery_score']}\n")

    print(f"\nSaved to {sweep_path} and {csv_path}")

    # Summary
    best_cov = max(all_sweep, key=lambda x: x["coverage"])
    print(f"\nBest coverage: {best_cov['coverage']:.3f} at threshold={best_cov['downgrade_threshold']} "
          f"(error={best_cov['served_error_rate']:.4f})")


if __name__ == "__main__":
    main()
