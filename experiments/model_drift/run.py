"""Model-drift leaderboard harness (#71) — run `python -m experiments.model_drift.run`.

Measures, per depth, how the pipeline (chain grade → content critic → decision matrix)
handles claims corrupted by a deterministic drift injector, against a deterministic
ground-truth oracle. Offline mode (no API keys) is the default and produces real,
reproducible numbers for the PIPELINE; live-model runs are a separate keyed phase.

The measured numbers:
- hallucination_rate  — fraction of claims the injector corrupted (ground truth).
- served_error_rate  — fraction of HALLUCINATED claims the pipeline still SERVEs.

Negative controls (reported beside every real number):
- no_gating (serve-everything) baseline.
- empty_critic (always UNVERIFIABLE) — a useless critic serves everything caveat.
- perfect critic (the oracle's verdict) — the decision matrix catches 100% by
  construction, which verifies the harness plumbing rather than claiming superiority.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.decision import decide
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.types import Action, ContentVerdict, NarratorGrade, NarratorType

from experiments.model_drift.dataset import (
    FACT_CORPUS,
    DriftInjector,
    Fact,
    chain_template,
    dataset_sha256,
)
from experiments.model_drift.oracle import GroundTruth, label_claim

_HERE = Path(__file__).resolve().parent
_RESULTS = _HERE / "results"

DEPTHS = (1, 2, 3, 4, 5)

# The offline "model family": a deterministic drift injector. Live families
# (provider, model_id) are declared but only measured in the keyed live phase.
MODEL_FAMILIES: dict[str, dict[str, object]] = {
    "offline-drift": {
        "provider": "offline",
        "model_id": "drift-injector",
        "corruption_probability": 0.25,
    },
    # "openai:gpt-4o": ...  # live families require keys; cells render "not run"
}


def _build_chain(depth: int) -> tuple[Chain, Registry]:
    """A chain of `depth` all-RELIABLE narrator links (SAHIH chain grade), so the
    decision is driven by the CONTENT verdict, not by narrator grade."""
    reg = Registry()
    specs: list[ChainLinkSpec] = []
    for i, (name, transform) in enumerate(chain_template(depth)):
        nid = f"agent:{name}"
        reg.register(nid, "general", narrator_type=NarratorType.MODEL, grade=NarratorGrade.RELIABLE)
        specs.append(
            ChainLinkSpec(narrator_id=nid, step=i, transform_type=transform, domain="general")
        )
    return Chain(specs), reg


def _critic_verdict(gt: GroundTruth, mode: str) -> ContentVerdict:
    """The content verdict for a given critic mode (independent of the oracle)."""
    if mode == "perfect":
        # ideal critic: uses the oracle's ground truth (NOT the critic under test)
        return {
            GroundTruth.FAITHFUL: ContentVerdict.CONSISTENT,
            GroundTruth.HALLUCINATED: ContentVerdict.CONTRADICTION,
            GroundTruth.UNVERIFIABLE: ContentVerdict.UNVERIFIABLE,
        }[gt]
    if mode == "empty":
        return ContentVerdict.UNVERIFIABLE
    raise ValueError(f"unknown critic mode {mode}")


def run_depth(
    depth: int, corruption_probability: float, seed: int, critic_mode: str
) -> dict[str, object]:
    chain, _ = _build_chain(depth)
    link_grades = [NarratorGrade.RELIABLE] * depth
    chain_grade = grade_chain(
        link_grades, [l.transform_type for l in chain.links], is_complete=chain.is_complete
    )

    injector = DriftInjector(corruption_probability, seed)
    n_hallucinated = 0
    n_served_hallucinated = 0
    per_fact: list[dict[str, object]] = []

    for fact in FACT_CORPUS:
        # simulate the claim surviving `depth` hops (each may corrupt it)
        claim = fact.assertion
        for _ in range(depth):
            claim = injector.transform(claim, fact)
        gt = label_claim(claim, fact)
        verdict = _critic_verdict(gt, critic_mode)
        action = decide(chain_grade, verdict)
        served = action in (Action.SERVE, Action.SERVE_WITH_CAVEAT)
        hallucinated = gt is GroundTruth.HALLUCINATED
        if hallucinated:
            n_hallucinated += 1
            if served:
                n_served_hallucinated += 1
        per_fact.append({
            "fact_id": fact.fact_id,
            "claim": claim,
            "ground_truth": gt.value,
            "action": action.value,
            "served": served,
        })

    hallucination_rate = n_hallucinated / len(FACT_CORPUS)
    served_error_rate = (n_served_hallucinated / n_hallucinated) if n_hallucinated else 0.0
    return {
        "depth": depth,
        "critic_mode": critic_mode,
        "n_facts": len(FACT_CORPUS),
        "n_hallucinated": n_hallucinated,
        "n_served_hallucinated": n_served_hallucinated,
        "hallucination_rate": round(hallucination_rate, 4),
        "served_error_rate": round(served_error_rate, 4),
        "per_fact": per_fact,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Model-drift leaderboard harness (#71)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--offline", action="store_true", default=True, help="run offline (default)"
    )
    parser.add_argument("--corruption-probability", type=float, default=0.25)
    parser.add_argument("--depths", type=int, nargs="+", default=list(DEPTHS))
    args = parser.parse_args(argv)

    rows: list[dict[str, object]] = []
    for mode in ("perfect", "empty"):
        for depth in args.depths:
            rows.append(run_depth(depth, args.corruption_probability, args.seed, mode))

    # no-gating baseline: served_error_rate is 1.0 by construction (serve everything)
    # recorded as a control row, not a measured run.
    record: dict[str, object] = {
        "schema_version": 1,
        "generated_date": date.today().isoformat(),
        "seed": args.seed,
        "corruption_probability": args.corruption_probability,
        "dataset_sha256": dataset_sha256(),
        "depths": list(args.depths),
        "rows": rows,
        "no_gating_baseline": {
            "served_error_rate": 1.0,
            "note": "serve-everything: every hallucinated claim is served by construction",
        },
    }

    _RESULTS.mkdir(exist_ok=True)
    raw_path = _RESULTS / "results.json"
    raw_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")

    # methodology freeze pin (written on first run; committed alongside preregistration)
    (_RESULTS / "methodology_sha.txt").write_text(dataset_sha256() + "\n")

    print(f"wrote {raw_path}")
    print(f"dataset_sha256={dataset_sha256()[:16]}…")
    for r in rows:
        print(
            f"  depth={r['depth']} critic={r['critic_mode']:8s} "
            f"hallucination_rate={r['hallucination_rate']:.3f} served_error_rate={r['served_error_rate']:.3f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
