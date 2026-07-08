"""Risk–coverage analysis for §8 experiment.

Sweeps operating points to trace served-error vs. coverage for each condition,
enabling matched-coverage comparison — the standard selective-prediction
evaluation that neutralizes the "ISNAD just serves less" critique.

Produces:
- results/risk_coverage.csv — per-condition (coverage, error) pairs
- Matched-coverage comparison table at coverage ∈ {0.20, 0.30, 0.50, 0.70, 0.90}
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

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.grading import grade_chain
from isnad.core.decision import decide
from isnad.core.registry import Registry
from isnad.types import (
    Action,
    ChainGrade,
    ContentVerdict,
    NarratorGrade,
    TransformType,
)

from sweep_policy import ConfigurableTransitionPolicy


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


def compute_risk_coverage_curve(
    eval_claims: list[dict],
    gt_lookup: dict[str, dict],
    reg: Registry,
    domains: list[str],
    cal_claims: list[dict],
    seed: int,
    n_points: int = 50,
    downgrade_threshold: int = 3,
) -> list[dict]:
    """Sweep the serving operating point for ISNAD-gated condition.

    For each operating point (review budget B from 0 to 0.50), compute
    coverage and served-error rate. Returns list of (coverage, error) dicts.
    """
    # Grade all claims first
    graded = []
    for c in eval_claims:
        chain = _rebuild_chain(c)
        grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
        xforms = [l.transform_type for l in chain.links]
        cg = grade_chain(grades, xforms, is_complete=c.get("chain_complete", True))
        action = decide(cg, ContentVerdict.UNVERIFIABLE)
        graded.append((c, action))

    graded.sort(key=lambda x: _action_priority(x[1]))

    points = []
    n = len(eval_claims)
    served_set: set[int] = set()
    errors_in_served = 0

    for i, (claim, action) in enumerate(graded):
        gt = gt_lookup.get(claim["claim_id"], {})
        is_defective = gt.get("corrupted", False)

        if action == Action.REJECT_AND_QUARANTINE_NARRATOR:
            continue
        if action == Action.QUARANTINE:
            continue

        # Serve this claim (either via review budget or direct serve)
        served_set.add(i)
        if is_defective:
            errors_in_served += 1

    # Now sweep: at each operating point (coverage level), what's the error?
    # We sweep by ordering claims by priority and serving top-K
    sorted_claims = sorted(
        [(i, action) for i, (_, action) in enumerate(graded)],
        key=lambda x: _action_priority(x[1]),
    )
    n_servable = sum(
        1 for _, action in sorted_claims
        if action not in (Action.REJECT_AND_QUARANTINE_NARRATOR, Action.QUARANTINE)
    )

    # For sweeping the operating point, we vary budget B
    budgets = [i / n_points for i in range(1, n_points + 1)]
    budgets = [b * 0.50 for b in budgets]  # B from 0.01 to 0.50

    for b in budgets:
        reviewed_count = 0
        served = 0
        errors = 0

        for claim, action in graded:
            gt = gt_lookup.get(claim["claim_id"], {})
            is_defective = gt.get("corrupted", False)

            if action in (Action.REJECT_AND_QUARANTINE_NARRATOR, Action.QUARANTINE):
                continue

            if action == Action.REVIEW and reviewed_count < int(n * b):
                reviewed_count += 1
                served += 1
                continue

            if action in (Action.SERVE, Action.SERVE_WITH_CAVEAT):
                served += 1
                if is_defective:
                    errors += 1
                continue

        if served > 0:
            points.append({
                "budget": b,
                "coverage": served / n,
                "served_error_rate": errors / served,
            })

    return points


def compute_confidence_risk_coverage(
    eval_claims: list[dict],
    gt_lookup: dict[str, dict],
    n_points: int = 50,
) -> list[dict]:
    """Risk-coverage curve for confidence-gated condition."""
    sorted_claims = sorted(
        enumerate(eval_claims),
        key=lambda x: x[1].get("model_confidence", 0.5),
    )
    n = len(eval_claims)
    points = []

    for i in range(1, n_points + 1):
        k = int(n * i / n_points)
        served_indices = set(j for j, _ in sorted_claims[k:])
        # Plus reviewed claims (lowest confidence get reviewed, not served-as-error)
        reviewed_indices = set(j for j, _ in sorted_claims[:k])

        served = 0
        errors = 0
        for j, claim in enumerate(eval_claims):
            gt = gt_lookup.get(claim["claim_id"], {})
            if j in served_indices:
                served += 1
                if gt.get("corrupted", False):
                    errors += 1
            # Reviewed claims are served clean

        if served > 0:
            points.append({
                "coverage": served / n,
                "served_error_rate": errors / served,
            })

    return points


def matched_coverage_comparison(
    isnad_curve: list[dict],
    conf_curve: list[dict],
    target_coverages: list[float],
) -> list[dict]:
    """At each target coverage, find nearest points and compare error rates."""
    results = []
    for tc in target_coverages:
        # Find nearest ISNAD point
        isnad_pt = min(isnad_curve, key=lambda p: abs(p["coverage"] - tc))
        conf_pt = min(conf_curve, key=lambda p: abs(p["coverage"] - tc))

        results.append({
            "target_coverage": tc,
            "isnad_actual_coverage": isnad_pt["coverage"],
            "isnad_error": isnad_pt["served_error_rate"],
            "confidence_actual_coverage": conf_pt["coverage"],
            "confidence_error": conf_pt["served_error_rate"],
            "isnad_advantage": conf_pt["served_error_rate"] - isnad_pt["served_error_rate"],
        })
    return results


def _action_priority(action: Action) -> int:
    p = {Action.REVIEW: 0, Action.SERVE_WITH_CAVEAT: 1, Action.SERVE: 99}
    return p.get(action, 50)


def main() -> None:
    exp_dir = _exp_dir
    results_dir = os.path.join(exp_dir, "results")
    seed_dir = os.path.join(results_dir, "seed_1")
    cal_dir = os.path.join(seed_dir, "calibration")

    with open(os.path.join(cal_dir, "eval_claims.json")) as f:
        eval_claims = json.load(f)
    with open(os.path.join(seed_dir, "ground_truth.json")) as f:
        gt_lookup = {r["claim_id"]: r for r in json.load(f)}
    with open(os.path.join(cal_dir, "registry_snapshot.json")) as f:
        snap = json.load(f)

    domains = ["mechanics", "electromagnetism", "optics-waves", "modern-quantum", "general"]
    reg = Registry()
    for key, data in snap.items():
        nid, domain = key.split("/", 1)
        reg.register(nid, domain, grade=NarratorGrade(data["grade"]))

    # ISNAD risk-coverage curve (default policy)
    isnad_curve = compute_risk_coverage_curve(
        eval_claims, gt_lookup, reg, domains,
        cal_claims=json.load(open(os.path.join(cal_dir, "cal_claims.json"))),
        seed=42,
    )

    # Confidence risk-coverage curve
    conf_curve = compute_confidence_risk_coverage(eval_claims, gt_lookup)

    # Save curves
    with open(os.path.join(results_dir, "risk_coverage_isnad.csv"), "w") as f:
        f.write("budget,coverage,served_error_rate\n")
        for p in isnad_curve:
            f.write(f"{p['budget']:.4f},{p['coverage']:.4f},{p['served_error_rate']:.4f}\n")

    with open(os.path.join(results_dir, "risk_coverage_confidence.csv"), "w") as f:
        f.write("coverage,served_error_rate\n")
        for p in conf_curve:
            f.write(f"{p['coverage']:.4f},{p['served_error_rate']:.4f}\n")

    # Matched-coverage comparison
    targets = [0.20, 0.30, 0.50, 0.70, 0.90]
    matched = matched_coverage_comparison(isnad_curve, conf_curve, targets)

    print("\n=== MATCHED-COVERAGE COMPARISON ===")
    print(f"  {'Target Cov':>10s}  {'ISNAD Cov':>10s}  {'ISNAD Err':>10s}  {'Conf Cov':>10s}  {'Conf Err':>10s}  {'Advantage':>10s}")
    print(f"  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*10}")
    for m in matched:
        print(f"  {m['target_coverage']:>10.0%}  {m['isnad_actual_coverage']:>10.3f}  "
              f"{m['isnad_error']:>10.4f}  {m['confidence_actual_coverage']:>10.3f}  "
              f"{m['confidence_error']:>10.4f}  {m['isnad_advantage']:>+10.4f}")

    with open(os.path.join(results_dir, "matched_coverage.json"), "w") as f:
        json.dump(matched, f, indent=2)

    print(f"\nSaved to results/risk_coverage_*.csv and results/matched_coverage.json")


if __name__ == "__main__":
    main()
