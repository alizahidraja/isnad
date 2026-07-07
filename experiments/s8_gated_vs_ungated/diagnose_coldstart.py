"""Coverage-vs-calibration diagnostic for the §8 experiment.

Re-runs calibration at increasing audit budgets and measures resulting
ISNAD-gated coverage at B=10%. Hypothesis: coverage rises as calibration
data increases — the collapse is a cold-start artifact (paper §7).

Outputs: coldstart_curve.csv + coldstart_curve.txt readout
"""

from __future__ import annotations

import json
import os
import random
import sys

_exp_dir = os.path.dirname(os.path.abspath(__file__))
if _exp_dir not in sys.path:
    sys.path.insert(0, _exp_dir)

from isnad.chain import Chain, ChainLinkSpec
from isnad.grading import grade_chain
from isnad.matrix import decide
from isnad.registry import Registry
from isnad.types import (
    Action,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    TransformType,
)


def calibrate_at_budget(
    cal_claims: list[dict],
    gt_lookup: dict[str, dict],
    audit_budget: int,
    seed: int,
) -> Registry:
    """Run jarḥ–taʿdīl with given audit budget per (narrator, domain)."""
    rng = random.Random(seed)
    reg = Registry()

    # Register all narrators
    narrator_ids: set[str] = set()
    for c in cal_claims:
        for nid in [c.get("assigned_scraper", ""), c.get("assigned_ingest", "")]:
            if nid:
                narrator_ids.add(nid)

    domains = set(c.get("domain", "general") for c in cal_claims)
    for nid in narrator_ids:
        for domain in domains:
            reg.register(nid, domain)

    # Group claims by (narrator, domain)
    from collections import defaultdict
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


def measure_coverage(
    eval_claims: list[dict],
    gt_lookup: dict[str, dict],
    reg: Registry,
    budget: float = 0.10,
) -> float:
    """Measure ISNAD-gated coverage at given budget."""
    n = len(eval_claims)
    review_budget = max(1, int(n * budget))

    graded = []
    for c in eval_claims:
        chain = _rebuild_chain(c)
        grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
        xforms = [l.transform_type for l in chain.links]
        cg = grade_chain(grades, xforms, is_complete=c.get("chain_complete", True))
        action = decide(cg, __import__("isnad.types", fromlist=["ContentVerdict"]).ContentVerdict.UNVERIFIABLE)
        graded.append((c, action))

    graded.sort(key=lambda x: _action_priority(x[1]))
    served = 0
    for _, action in graded:
        if action in (Action.SERVE, Action.SERVE_WITH_CAVEAT):
            served += 1
        elif action == Action.REVIEW and served < review_budget:
            served += 1

    return served / max(1, n)


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
    seed_dir = os.path.join(results_dir, "seed_1", "calibration")

    cal_path = os.path.join(seed_dir, "cal_claims.json")
    eval_path = os.path.join(seed_dir, "eval_claims.json")
    gt_path = os.path.join(results_dir, "seed_1", "ground_truth.json")

    if not all(os.path.exists(p) for p in [cal_path, eval_path, gt_path]):
        print("Missing data. Run inject.py and calibrate.py first.")
        return

    with open(cal_path) as f:
        cal_claims = json.load(f)
    with open(eval_path) as f:
        eval_claims = json.load(f)
    with open(gt_path) as f:
        gt_lookup = {r["claim_id"]: r for r in json.load(f)}

    budgets = [10, 20, 40, 80, 160]
    lines = [
        "Coverage-vs-Calibration Curve",
        "==============================",
        "",
        f"Calibration claims: {len(cal_claims)}",
        f"Evaluation claims:  {len(eval_claims)}",
        f"Serving budget: B=10%",
        "",
        "Hypothesis: coverage rises as calibration data increases (cold-start artifact).",
        "",
        f"  {'Audits/narrator':<18s} {'Coverage':>8s}",
        f"  {'─'*18} {'─'*8}",
    ]
    csv_lines = ["audit_budget,coverage"]

    for budget in budgets:
        reg = calibrate_at_budget(cal_claims, gt_lookup, budget, seed=42)
        cov = measure_coverage(eval_claims, gt_lookup, reg)
        lines.append(f"  {budget:<18d} {cov:>8.3f}")
        csv_lines.append(f"{budget},{cov:.4f}")
        print(f"  budget={budget:>3d}  coverage={cov:.3f}")

    lines.append("")
    if any(float(l.split(",")[1]) for l in csv_lines[1:]):
        first = float(csv_lines[1].split(",")[1])
        last = float(csv_lines[-1].split(",")[1])
        if last > first * 1.5:
            lines.append("✓ Coverage increases with calibration data — consistent with cold-start hypothesis.")
        elif last > first * 1.1:
            lines.append("⚠ Modest coverage increase with calibration — partially consistent with cold-start.")
        else:
            lines.append("✗ Coverage does NOT increase with calibration data — cold-start hypothesis not supported.")
        lines.append(f"  Coverage at 10 audits: {first:.3f}")
        lines.append(f"  Coverage at 160 audits: {last:.3f}")
        lines.append(f"  Ratio: {last/first:.2f}x")

    out_path = os.path.join(results_dir, "coldstart_curve.txt")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    csv_path = os.path.join(results_dir, "coldstart_curve.csv")
    with open(csv_path, "w") as f:
        f.write("\n".join(csv_lines))
    print(f"\nSaved to {out_path} and {csv_path}")


if __name__ == "__main__":
    main()
