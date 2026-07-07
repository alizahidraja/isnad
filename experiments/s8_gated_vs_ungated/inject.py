"""Fault injection and chain assignment for the §8 experiment.

Assigns each claim a scraper variant and ingest variant (uniform random,
seeded), applies faults per narrator rates, marks ~5% chains incomplete,
and records ground truth.

Uses the real isnad package's Chain and ChainLinkSpec types to build
transmission chains.
"""

from __future__ import annotations

import json
import os
import random
import sys

from isnad.chain import Chain, ChainLinkSpec
from isnad.types import TransformType

# Add experiment dir to path for local imports
_exp_dir = os.path.dirname(os.path.abspath(__file__))
if _exp_dir not in sys.path:
    sys.path.insert(0, _exp_dir)

from ground_truth import GroundTruth, InjectionRecord
from narrators import (
    INGEST_VARIANTS,
    NARRATOR_VARIANTS,
    SCRAPER_VARIANTS,
)


def assign_narrators(
    claims: list[dict],
    rng: random.Random,
    incomplete_rate: float = 0.05,
) -> tuple[list[dict], GroundTruth]:
    """Assign narrator variants to each claim and inject faults.

    Returns (enriched_claims, ground_truth).
    enriched_claims have added fields: scraper, ingest, corrupted_text,
    chain_complete, chain_json.

    WARNING: ground_truth is the FIREWALL module — never passed to grading code.
    """
    gt = GroundTruth()
    enriched: list[dict] = []

    for claim in claims:
        c = dict(claim)  # copy

        # Assign narrator variants uniformly at random
        scraper_id = rng.choice(SCRAPER_VARIANTS)
        ingest_id = rng.choice(INGEST_VARIANTS)
        scraper = NARRATOR_VARIANTS[scraper_id]
        ingest = NARRATOR_VARIANTS[ingest_id]

        c["assigned_scraper"] = scraper_id
        c["assigned_ingest"] = ingest_id
        c["domain"] = claim.get("domain", "general")

        # Apply faults
        original_text = claim["text"]
        corrupted_text = original_text
        fault_type = "none"
        responsible = "none"

        # Scraper fault (destructive)
        corrupted_text, scraper_fault = scraper.apply_faults(corrupted_text, rng)
        if scraper_fault != "none":
            fault_type = f"scraper:{scraper_fault}"
            responsible = scraper_id

        # Ingest fault (generative)
        corrupted_text, ingest_fault = ingest.apply_faults(corrupted_text, rng)
        if ingest_fault != "none":
            if fault_type != "none":
                fault_type += f"+ingest:{ingest_fault}"
            else:
                fault_type = f"ingest:{ingest_fault}"
            if responsible == "none":
                responsible = ingest_id

        c["corrupted_text"] = corrupted_text
        c["is_corrupted"] = fault_type != "none"

        # Mark ~5% chains incomplete
        chain_complete = rng.random() >= incomplete_rate
        c["chain_complete"] = chain_complete

        # Build the real isnad Chain
        chain = Chain([
            ChainLinkSpec(
                f"source:{claim.get('source', 'unknown')}",
                step=0,
                domain=c["domain"],
                transform_type=TransformType.PASS_THROUGH,
            ),
            ChainLinkSpec(
                scraper_id,
                step=1,
                version=scraper_id.split("@")[1] if "@" in scraper_id else "unknown",
                domain=c["domain"],
                transform_type=TransformType.DESTRUCTIVE,
            ),
            ChainLinkSpec(
                ingest_id,
                step=2,
                version=ingest_id.split("@")[1] if "@" in ingest_id else "unknown",
                domain=c["domain"],
                transform_type=TransformType.GENERATIVE,
            ),
        ])
        c["chain_json"] = chain.to_jsonb()

        # Record ground truth
        gt.add(InjectionRecord(
            claim_id=claim["claim_id"],
            corrupted=fault_type != "none",
            fault_type=fault_type,
            responsible_narrator=responsible,
            original_text=original_text,
            corrupted_text=corrupted_text,
            domain=c["domain"],
            chain_complete=chain_complete,
            assigned_scraper=scraper_id,
            assigned_ingest=ingest_id,
            model_confidence=claim.get("model_confidence", 0.0),
        ))

        enriched.append(c)

    return enriched, gt


def main() -> None:
    exp_dir = os.path.dirname(os.path.abspath(__file__))
    claims_path = os.path.join(exp_dir, "results", "claims.json")

    if not os.path.exists(claims_path):
        print("Run extract.py first to generate claims.json")
        sys.exit(1)

    claims = load_claims(claims_path)
    print(f"Loaded {len(claims)} claims")

    # Seed from config (hardcoded for now; in production, read config.yaml)
    for seed in [1, 2, 3, 4, 5]:
        rng = random.Random(seed * 12345)
        enriched, gt = assign_narrators(claims, rng)

        # Save per seed
        seed_dir = os.path.join(exp_dir, "results", f"seed_{seed}")
        os.makedirs(seed_dir, exist_ok=True)

        with open(os.path.join(seed_dir, "enriched_claims.json"), "w") as f:
            json.dump(enriched, f, indent=2)

        with open(os.path.join(seed_dir, "ground_truth.json"), "w") as f:
            json.dump([
                {
                    "claim_id": r.claim_id,
                    "corrupted": r.corrupted,
                    "fault_type": r.fault_type,
                    "responsible_narrator": r.responsible_narrator,
                    "original_text": r.original_text,
                    "corrupted_text": r.corrupted_text,
                    "domain": r.domain,
                    "chain_complete": r.chain_complete,
                    "assigned_scraper": r.assigned_scraper,
                    "assigned_ingest": r.assigned_ingest,
                    "model_confidence": r.model_confidence,
                }
                for r in gt.records
            ], f, indent=2)

        print(f"  seed={seed}: {gt.summary()}")

    print("Injection complete. Ground truth per seed saved.")


if __name__ == "__main__":
    # Import here to avoid circular
    from extract import load_claims
    main()
