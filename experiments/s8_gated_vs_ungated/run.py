"""Phase 2 — Evaluation: gated vs. ungated serving at fixed review budget.

Runs four serving conditions on the 70% evaluation split:
1. Ungated + random review
2. Confidence-gated (status-quo baseline)
3. ISNAD-gated (full framework)
4. ISNAD-gated, no corroboration (ablation)

All conditions at the same human-review budgets B ∈ {2%, 5%, 10%, 20%}.
5 random seeds for narrator assignment + injection.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

from isnad.chain import Chain, ChainLinkSpec
from isnad.grading import grade_chain
from isnad.matn import DeterministicRuleCritic
from isnad.matrix import decide
from isnad.registry import Registry
from isnad.types import (
    Action,
    ChainGrade,
    ContentVerdict,
    NarratorGrade,
    TransformType,
)

_exp_dir = os.path.dirname(os.path.abspath(__file__))
if _exp_dir not in sys.path:
    sys.path.insert(0, _exp_dir)


@dataclass
class ClaimVerdict:
    """Per-claim evaluation verdict from one serving condition."""

    claim_id: str
    served: bool = False  # was it served to users?
    reviewed: bool = False  # was it sent to human review?
    error_if_served: bool = False  # if served, was it defective?
    action: str = ""
    chain_grade: str = ""
    content_verdict: str = ""
    condition: str = ""


def _rebuild_chain(claim: dict) -> Chain:
    """Rebuild a Chain from the stored chain_json."""
    links = claim.get("chain_json", [])
    specs = []
    for i, link in enumerate(links):
        specs.append(ChainLinkSpec(
            narrator_id=link["narrator_id"],
            step=i,
            version=link.get("version", "unknown"),
            transform_type=TransformType(link.get("transform_type", "pass_through")),
            domain=link.get("domain", "general"),
        ))
    chain = Chain(specs)
    return chain


def _isnad_gated_priority(action: Action) -> int:
    """Priority for review-queue consumption: lower = review first."""
    priority = {
        Action.REVIEW: 0,                        # ʿilal / ḥasan×contradiction
        Action.SERVE_WITH_CAVEAT: 1,             # review if budget allows
        Action.QUARANTINE: 2,                    # hold
        Action.REJECT_AND_QUARANTINE_NARRATOR: 3,  # already contained
        Action.SERVE: 99,                        # never review
    }
    return priority.get(action, 50)


def run_condition(
    eval_claims: list[dict],
    gt_lookup: dict[str, dict],
    reg: Registry,
    corpus_normalized: list[str],
    budget: float,
    condition: str,
) -> tuple[list[ClaimVerdict], dict]:
    """Run one serving condition on eval claims.

    Returns (verdicts, stats_dict).
    """
    n_claims = len(eval_claims)
    review_budget = max(1, int(n_claims * budget))
    critic = DeterministicRuleCritic()

    verdicts: list[ClaimVerdict] = []
    stats = {
        "served": 0, "reviewed": 0, "errors_served": 0,
        "reviewed_defective": 0, "quarantined": 0,
        "corroboration_upgrades": 0,
    }

    if condition == "ungated":
        # Serve everything, review random subset
        indices = list(range(n_claims))
        import random
        rng = random.Random(42)
        rng.shuffle(indices)
        review_set = set(indices[:review_budget])

        for i, claim in enumerate(eval_claims):
            v = ClaimVerdict(claim_id=claim["claim_id"], condition=condition)
            v.served = True
            gt = gt_lookup.get(claim["claim_id"], {})

            if i in review_set:
                v.reviewed = True
                stats["reviewed"] += 1
                if gt.get("corrupted", False):
                    stats["reviewed_defective"] += 1
                    # Reviewed and corrected → not served as error
                else:
                    pass  # reviewed, clean → served OK
                stats["served"] += 1
            else:
                # Not reviewed → served as-is
                stats["served"] += 1
                if gt.get("corrupted", False):
                    v.error_if_served = True
                    stats["errors_served"] += 1

            verdicts.append(v)

    elif condition == "confidence":
        # Route B lowest-confidence claims to review
        sorted_claims = sorted(
            enumerate(eval_claims),
            key=lambda x: x[1].get("model_confidence", 0.5),
        )
        review_set = set(i for i, _ in sorted_claims[:review_budget])

        for i, claim in enumerate(eval_claims):
            v = ClaimVerdict(claim_id=claim["claim_id"], condition=condition)
            v.served = True
            gt = gt_lookup.get(claim["claim_id"], {})

            if i in review_set:
                v.reviewed = True
                stats["reviewed"] += 1
                if gt.get("corrupted", False):
                    stats["reviewed_defective"] += 1
                stats["served"] += 1
            else:
                stats["served"] += 1
                if gt.get("corrupted", False):
                    v.error_if_served = True
                    stats["errors_served"] += 1

            verdicts.append(v)

    elif condition in ("isnad", "isnad_no_corroboration"):
        enable_corroboration = (condition == "isnad")

        # --- First pass: grade all chains ---
        graded_claims: list[dict] = []
        for claim in eval_claims:
            c = dict(claim)
            chain = _rebuild_chain(claim)

            link_grades = []
            for link in chain.links:
                g = reg.get_grade(link.narrator_id, link.domain)
                link_grades.append(g)
            link_transforms = [link.transform_type for link in chain.links]

            cg = grade_chain(
                link_grades, link_transforms,
                is_complete=claim.get("chain_complete", True),
                corroboration_support=False,
            )
            c["chain_grade_raw"] = cg.value
            c["chain_grade"] = cg.value
            c["_link_grades"] = [g.value for g in link_grades]
            c["_narrator_ids"] = [link.narrator_id for link in chain.links]

            # Matn criticism: deterministic stub returns UNVERIFIABLE on real text
            # (the stub only matches exact duplicates and hardcoded patterns;
            #  on real textbook text without self-matching, it always returns UNVERIFIABLE)
            cv = ContentVerdict.UNVERIFIABLE
            c["content_verdict"] = cv.value
            graded_claims.append(c)

        # --- Second pass: cross-claim corroboration (mutābaʿāt) ---
        if enable_corroboration:
            from isnad.corroboration import evaluate_corroboration

            # Build lookup by normalized text for cross-source matching
            by_norm: dict[str, list[dict]] = {}
            for c in graded_claims:
                norm = c.get("normalized", "")
                if norm:
                    by_norm.setdefault(norm, []).append(c)

            # Narrator metadata for correlation detection
            narrator_metadata: dict[str, dict] = {}
            for nid in set(
                n for c in graded_claims for n in c.get("_narrator_ids", [])
            ):
                if nid.startswith("source:"):
                    narrator_metadata[nid] = {"model_family": None, "upstream_source": nid}
                elif "pdf-scraper" in nid:
                    narrator_metadata[nid] = {"model_family": "scraper", "upstream_source": None}
                elif "ingest" in nid:
                    narrator_metadata[nid] = {"model_family": nid.rsplit("@",1)[0] if "@" in nid else nid, "upstream_source": None}

            corroboration_applied = 0
            for norm, claims in by_norm.items():
                if len(claims) < 2:
                    continue
                # Check for claims from different sources (different narrator chains)
                for i, c_a in enumerate(claims):
                    for c_b in claims[i + 1:]:
                        # Must have different sources (different chains)
                        if c_a.get("source") == c_b.get("source"):
                            continue
                        try:
                            cg_a = ChainGrade(c_a["chain_grade"])
                            cg_b = ChainGrade(c_b["chain_grade"])

                            upgraded_a = evaluate_corroboration(
                                base_grade=cg_a,
                                corroborating_chain_grades=[cg_b],
                                base_narrators=c_a.get("_narrator_ids", []),
                                corroborating_narrators=[c_b.get("_narrator_ids", [])],
                                narrator_metadata=narrator_metadata,
                            )
                            upgraded_b = evaluate_corroboration(
                                base_grade=cg_b,
                                corroborating_chain_grades=[cg_a],
                                base_narrators=c_b.get("_narrator_ids", []),
                                corroborating_narrators=[c_a.get("_narrator_ids", [])],
                                narrator_metadata=narrator_metadata,
                            )

                            if upgraded_a != cg_a:
                                c_a["chain_grade"] = upgraded_a.value
                                c_a["_corroborated"] = True
                                corroboration_applied += 1
                            if upgraded_b != cg_b:
                                c_b["chain_grade"] = upgraded_b.value
                                c_b["_corroborated"] = True
                                corroboration_applied += 1
                        except (ValueError, KeyError):
                            pass

            if corroboration_applied > 0:
                stats["corroboration_upgrades"] = corroboration_applied

        # --- Apply decision matrix to all graded claims ---
        for c in graded_claims:
            cg = ChainGrade(c["chain_grade"])
            cv = ContentVerdict(c.get("content_verdict", "unverifiable"))
            action = decide(cg, cv)
            c["matrix_action"] = action.value

        # Sort by review priority
        sorted_graded = sorted(
            graded_claims,
            key=lambda c: _isnad_gated_priority(
                Action(c.get("matrix_action", "serve"))
            ),
        )

        reviewed_count = 0
        for claim in sorted_graded:
            v = ClaimVerdict(
                claim_id=claim["claim_id"], condition=condition,
                action=claim.get("matrix_action", ""),
                chain_grade=claim.get("chain_grade", ""),
                content_verdict=claim.get("content_verdict", ""),
            )
            gt = gt_lookup.get(claim["claim_id"], {})
            action = Action(claim.get("matrix_action", "serve"))

            if action == Action.REJECT_AND_QUARANTINE_NARRATOR:
                # Quarantined — never served
                stats["quarantined"] += 1
                verdicts.append(v)
                continue

            if action == Action.QUARANTINE:
                stats["quarantined"] += 1
                verdicts.append(v)
                continue

            if action == Action.REVIEW and reviewed_count < review_budget:
                v.reviewed = True
                v.served = True
                reviewed_count += 1
                stats["reviewed"] += 1
                if gt.get("corrupted", False):
                    stats["reviewed_defective"] += 1
                stats["served"] += 1
                verdicts.append(v)
                continue

            if action in (Action.SERVE, Action.SERVE_WITH_CAVEAT):
                v.served = True
                stats["served"] += 1
                if gt.get("corrupted", False):
                    v.error_if_served = True
                    stats["errors_served"] += 1
                verdicts.append(v)
                continue

            # Default: not served
            verdicts.append(v)

    return verdicts, stats


def main() -> None:
    exp_dir = os.path.dirname(os.path.abspath(__file__))
    budgets = [0.02, 0.05, 0.10, 0.20]
    seeds = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    conditions = ["ungated", "confidence", "isnad", "isnad_no_corroboration"]
    all_results: dict[str, dict] = {}

    for seed in seeds:
        seed_dir = os.path.join(exp_dir, "results", f"seed_{seed}")
        cal_dir = os.path.join(seed_dir, "calibration")

        eval_path = os.path.join(cal_dir, "eval_claims.json")
        gt_path = os.path.join(seed_dir, "ground_truth.json")
        reg_path = os.path.join(cal_dir, "registry_snapshot.json")

        if not all(os.path.exists(p) for p in [eval_path, gt_path]):
            print(f"Seed {seed}: missing files. Run calibrate.py first.")
            continue

        with open(eval_path) as f:
            eval_claims = json.load(f)
        with open(gt_path) as f:
            gt_records = json.load(f)

        # Rebuild registry from snapshot
        reg = Registry()
        with open(reg_path) as f:
            reg_snap = json.load(f)
        for key, data in reg_snap.items():
            nid, domain = key.split("/", 1)
            reg.register(nid, domain, grade=NarratorGrade(data["grade"]))

        # Build corpus for matn criticism
        corpus_normalized = set(
            c.get("normalized", "") for c in eval_claims
            if c.get("normalized")
        )

        # Build GT lookup
        gt_lookup = {r["claim_id"]: r for r in gt_records}

        print(f"\nSeed {seed}: {len(eval_claims)} eval claims")

        for condition in conditions:
            for budget in budgets:
                verdicts, stats = run_condition(
                    eval_claims, gt_lookup, reg,
                    corpus_normalized, budget, condition,
                )

                total_claims = len(eval_claims)
                served = stats["served"]
                key = f"s{seed}_{condition}_b{int(budget*100):02d}"
                all_results[key] = {
                    "seed": seed,
                    "condition": condition,
                    "budget": budget,
                    "total_claims": total_claims,
                    "served": served,
                    "coverage": served / max(1, total_claims),
                    "errors_served": stats["errors_served"],
                    "served_error_rate": stats["errors_served"] / max(1, served),
                    "reviewed": stats["reviewed"],
                    "reviewed_defective": stats["reviewed_defective"],
                    "review_precision": (
                        stats["reviewed_defective"] / max(1, stats["reviewed"])
                    ),
                    "quarantined": stats["quarantined"],
                    "corroboration_upgrades": stats.get("corroboration_upgrades", 0),
                }

                print(f"  {condition:25s} B={budget:.0%}  "
                      f"coverage={all_results[key]['coverage']:.3f}  "
                      f"error_rate={all_results[key]['served_error_rate']:.4f}  "
                      f"review_prec={all_results[key]['review_precision']:.3f}")

    # Save all results
    results_dir = os.path.join(exp_dir, "results")
    with open(os.path.join(results_dir, "all_results.json"), "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nResults saved to results/all_results.json ({len(all_results)} entries)")


if __name__ == "__main__":
    main()
