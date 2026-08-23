"""Demonstrate endpoint identity drift fix — versioned registry keys.

Run:
    uv run python examples/endpoint_identity_drift_demo.py

Shows that grades resolve to alias@version, so a new deployment does not
inherit trust earned by an older version behind the same service name.
"""

from __future__ import annotations

from isnad.core.chain import Chain, ChainLinkSpec, grades_for_chain
from isnad.core.decision import decide, describe_action
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.matn import DeterministicRuleCritic
from isnad.types import NarratorGrade, TransformType


def hr(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


def main() -> None:
    reg = Registry()
    critic = DeterministicRuleCritic()
    claim = "The photon momentum is p = h/lambda"

    hr("Step 1 — v1.0 earns trust under versioned key ingest-model-v3@1.0")
    reg.register_versioned(
        "openstax-textbook",
        "physics",
        "2024",
        grade=NarratorGrade.RELIABLE,
    )
    reg.register_versioned(
        "ingest-model-v3",
        "physics",
        "1.0",
        grade=NarratorGrade.RELIABLE,
    )
    print("  Registered: openstax-textbook@2024 → RELIABLE")
    print("  Registered: ingest-model-v3@1.0     → RELIABLE")

    hr("Step 2 — Ops deploys v2.0 (same alias, no grade for @2.0 yet)")
    print("  ingest-model-v3@2.0 is not in the registry.")

    hr("Step 3 — New claim arrives through v2.0")
    chain = Chain([
        ChainLinkSpec("openstax-textbook", 0, domain="physics", version="2024"),
        ChainLinkSpec(
            "ingest-model-v3",
            1,
            domain="physics",
            version="2.0",
            transform_type=TransformType.GENERATIVE,
        ),
    ])
    for link in chain.links:
        print(f"  Chain link: {link.narrator_id} @ version={link.version}")

    hr("Step 4 — Version-aware grade lookup (FIXED)")
    print("  get_grade_for_link() resolves alias@version before lookup\n")
    link_grades = grades_for_chain(reg, chain)
    for link, grade in zip(chain.links, link_grades, strict=True):
        print(
            f"  {link.narrator_id:20s}  chain version={link.version:6s}  "
            f"→ grade={grade.value.upper()}"
        )

    transforms = [link.transform_type for link in chain.links]
    chain_grade = grade_chain(link_grades, transforms, is_complete=True)
    verdict = critic.evaluate(claim, claim, [], "physics")
    action = decide(chain_grade, verdict)

    print(f"\n  Chain grade:  {chain_grade.value.upper()}")
    print(f"  Decision:     {action.value.upper()} — {describe_action(chain_grade, verdict)}")
    print("\n  v2.0 is UNGRADED — it does not inherit v1.0's RELIABLE grade.")

    hr("Step 5 — After v2.0 earns trust on its own")
    reg.register_versioned(
        "ingest-model-v3",
        "physics",
        "2.0",
        grade=NarratorGrade.RELIABLE,
    )
    link_grades_after = grades_for_chain(reg, chain)
    chain_grade_after = grade_chain(link_grades_after, transforms, is_complete=True)
    action_after = decide(chain_grade_after, verdict)
    print(f"  ingest-model-v3@2.0 grade: {link_grades_after[1].value.upper()}")
    print(f"  Chain grade now: {chain_grade_after.value.upper()}")
    print(f"  Decision now:    {action_after.value.upper()}")
    print("\n  Each version maintains its own track record under alias@version.")


if __name__ == "__main__":
    main()
