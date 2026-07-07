"""Human audit hook — export sampled claims for independent verification.

Exports two CSVs:
1. 100 randomly sampled served claims with system verdict per condition
2. 100 review-queue items

Columns: claim_text, original_source_excerpt, condition, system_verdict,
         blank human_verdict column.
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys

_exp_dir = os.path.dirname(os.path.abspath(__file__))


def export_audit_samples(results_dir: str, seed: int = 999) -> None:
    """Export audit CSVs for human verification."""
    rng = random.Random(seed)

    # Try to load enriched claims from seed 1
    claims_path = os.path.join(results_dir, "seed_1", "enriched_claims.json")
    gt_path = os.path.join(results_dir, "seed_1", "ground_truth.json")

    if not os.path.exists(claims_path):
        print("No claim data found. Run inject.py first.")
        return

    with open(claims_path) as f:
        claims = json.load(f)

    gt_lookup = {}
    if os.path.exists(gt_path):
        with open(gt_path) as f:
            gt_lookup = {r["claim_id"]: r for r in json.load(f)}

    # Sample 100 served claims
    rng.shuffle(claims)
    served_sample = claims[:100]

    served_path = os.path.join(results_dir, "audit_served_sample.csv")
    with open(served_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "claim_id", "claim_text", "original_text", "domain",
            "model_confidence", "condition", "system_verdict",
            "human_verdict",
        ])
        for c in served_sample:
            gt = gt_lookup.get(c["claim_id"], {})
            writer.writerow([
                c["claim_id"][:16],
                c.get("corrupted_text", c.get("text", "")),
                gt.get("original_text", c.get("text", "")),
                c.get("domain", ""),
                c.get("model_confidence", ""),
                "isnad-gated",
                "served",
                "",  # blank for human
            ])

    # Sample 100 review-queue items (claims with corrupted text)
    corrupted = [c for c in claims if c.get("is_corrupted", False)]
    rng.shuffle(corrupted)
    review_sample = corrupted[:100]

    review_path = os.path.join(results_dir, "audit_review_sample.csv")
    with open(review_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "claim_id", "claim_text", "original_text", "fault_type",
            "domain", "condition", "system_verdict",
            "human_verdict",
        ])
        for c in review_sample:
            gt = gt_lookup.get(c["claim_id"], {})
            writer.writerow([
                c["claim_id"][:16],
                c.get("corrupted_text", c.get("text", "")),
                gt.get("original_text", c.get("text", "")),
                gt.get("fault_type", "none"),
                c.get("domain", ""),
                "review-queue",
                "pending_review",
                "",
            ])

    print(f"Audit samples exported:")
    print(f"  Served:  {served_path}  ({len(served_sample)} claims)")
    print(f"  Review:  {review_path}  ({len(review_sample)} claims)")
    print(f"\nFill in the blank 'human_verdict' column and compare with system verdicts.")


def main() -> None:
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    export_audit_samples(results_dir)


if __name__ == "__main__":
    main()
