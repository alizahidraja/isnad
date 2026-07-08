"""Paper's worked example (§4.5) as a standalone narrated demo.

Run: make demo   OR   uv run python examples/worked_example.py

This traces the paper's photon-momentum claim through the full pipeline.
"""

from isnad.chain import Chain, ChainLinkSpec, normalize_claim_text
from isnad.grading import grade_chain
from isnad.matn import DeterministicRuleCritic
from isnad.matrix import decide, describe_action
from isnad.registry import Registry
from isnad.types import (
    AdalahGrade,
    DabtGrade,
    NarratorGrade,
    NarratorType,
    TransformType,
)


def hr(title: str = "") -> None:
    if title:
        print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")
    else:
        print("─" * 60)


def main() -> None:
    print("=" * 64)
    print("  Isnād–Rijāl Framework — Paper's Worked Example (§4.5)")
    print("=" * 64)

    # ── The claim ──────────────────────────────────────────────
    claim_text = "the momentum of a photon is p = h/λ"
    print(f'\n📝 CLAIM: "{claim_text}"')
    print("   Source: OpenStax University Physics Vol. 3 (CC-BY)")

    # ── Build the transmission chain ──────────────────────────
    hr("1. BUILD THE ISNĀD (TRANSMISSION CHAIN)")

    chain = Chain(
        [
            ChainLinkSpec(
                "openstax-v3",
                step=0,
                version="latest",
                domain="physics-quantum",
                trace_id="trace-001",
                transform_type=TransformType.PASS_THROUGH,
            ),
            ChainLinkSpec(
                "pdf-scraper",
                step=1,
                version="1.2",
                domain="physics-quantum",
                trace_id="trace-002",
                transform_type=TransformType.DESTRUCTIVE,
            ),
            ChainLinkSpec(
                "ingest-analysis",
                step=2,
                version="v",
                domain="physics-quantum",
                trace_id="trace-003",
                transform_type=TransformType.GENERATIVE,
            ),
            ChainLinkSpec(
                "ingest-renderer",
                step=3,
                version="v",
                domain="physics-quantum",
                trace_id="trace-004",
                transform_type=TransformType.GENERATIVE,
            ),
        ]
    )

    for link in chain.links:
        xform = link.transform_type.value.upper()
        print(f"   Step {link.step}: {link.narrator_id}@{link.version}  [{xform}]")
    status = "COMPLETE" if chain.is_complete else "MUNQAṬIʿ (gap)"
    print(f"\n   Completeness (ittiṣāl): {'✓' if chain.is_complete else '✗'} {status}")

    # ── Narrator registry ─────────────────────────────────────
    hr("2. CONSULT THE RIJĀL REGISTRY (NARRATOR GRADES)")

    reg = Registry()
    reg.register(
        "openstax-v3",
        "physics-quantum",
        narrator_type=NarratorType.SOURCE,
        grade=NarratorGrade.RELIABLE,
        adalah=AdalahGrade.HIGH,
    )
    reg.register(
        "pdf-scraper",
        "physics-quantum",
        narrator_type=NarratorType.SCRAPER,
        grade=NarratorGrade.RELIABLE,
        dabt=DabtGrade.HIGH,
        model_version="1.2",
    )
    reg.register(
        "ingest-analysis",
        "physics-quantum",
        narrator_type=NarratorType.MODEL,
        grade=NarratorGrade.UNGRADED,
        model_version="v",
    )
    reg.register(
        "ingest-renderer",
        "physics-quantum",
        narrator_type=NarratorType.MODEL,
        grade=NarratorGrade.UNGRADED,
        model_version="v",
    )

    for link in chain.links:
        grade = reg.get_grade(link.narrator_id, link.domain)
        label = f"({grade.value.upper()})"
        print(f"   {link.narrator_id} / {link.domain}: {label}")

    # ── Chain grading ─────────────────────────────────────────
    hr("3. GRADE THE CHAIN (WEAKEST-LINK RULE)")

    link_grades = [reg.get_grade(link.narrator_id, link.domain) for link in chain.links]
    link_transforms = [link.transform_type for link in chain.links]
    chain_grade = grade_chain(link_grades, link_transforms, is_complete=chain.is_complete)

    print(f"   Narrator grades:  {' → '.join(g.value.upper() for g in link_grades)}")
    print(f"   Transform types:  {' → '.join(t.value.upper() for t in link_transforms)}")
    print(f"\n   ▶ Chain grade: {chain_grade.value.upper()}  (two ungraded links → ḥasan-tier)")

    # ── Matn criticism ────────────────────────────────────────
    hr("4. MATN CRITICISM (CONTENT CHECK, INDEPENDENT OF CHAIN)")

    normalized = normalize_claim_text(claim_text)
    corpus = ["momentum p = mv"]  # classical mechanics claim already in KB

    critic = DeterministicRuleCritic()
    content_verdict = critic.evaluate(claim_text, normalized, corpus)

    print(f"   New claim:       {normalized}")
    print(f"   Corpus claim:    {corpus[0]}")
    print(f"\n   ▶ Content verdict: {content_verdict.value.upper()}  (p=h/λ contradicts p=mv)")

    # ── Decision matrix ───────────────────────────────────────
    hr("5. DECISION MATRIX (4×2 ROUTER)")

    action = decide(chain_grade, content_verdict)
    description = describe_action(chain_grade, content_verdict)

    print(f"   Chain grade:   {chain_grade.value.upper()}")
    print(f"   Content:       {content_verdict.value.upper()}")
    print(f"   {'─' * 42}")
    print(f"   ▶ ACTION:      {action.value.upper()}")
    print(f"   ▶ Rationale:   {description}")

    # ── Variant: all narrators RELIABLE ───────────────────────
    hr("6. VARIANT: BOTH INGEST MODELS GRADED RELIABLE")

    reg2 = Registry()
    for nid in ["openstax-v3", "pdf-scraper", "ingest-analysis", "ingest-renderer"]:
        reg2.register(nid, "physics-quantum", grade=NarratorGrade.RELIABLE)

    link_grades2 = [reg2.get_grade(link.narrator_id, link.domain) for link in chain.links]
    chain_grade2 = grade_chain(link_grades2, link_transforms, is_complete=chain.is_complete)
    action2 = decide(chain_grade2, content_verdict)
    desc2 = describe_action(chain_grade2, content_verdict)

    print(f"   Narrator grades:  {' → '.join('RELIABLE' for _ in link_grades2)}")
    print(f"   ▶ Chain grade:    {chain_grade2.value.upper()}  (all reliable → ṣaḥīḥ-tier)")
    print(f"   ▶ Content:        {content_verdict.value.upper()}")
    print(f"   ▶ ACTION:         {action2.value.upper()}")
    print(f"   ▶ Rationale:      {desc2}")

    # ── Wrap-up ───────────────────────────────────────────────
    hr()
    print("  The difference: without narrator grades, a contradiction is")
    print("  just a conflict to resolve.  WITH the framework, the chain")
    print("  quality tells the reviewer WHICH claim to trust more, and")
    print("  whether the conflict signals a defect or a genuine regime")
    print("  distinction.  This is what rijāl methodology adds over")
    print("  plain execution-provenance logging.\n")
    print("  📄 Paper:  https://doi.org/10.5281/zenodo.21211290")
    print("  📋 Gist:   https://gist.github.com/alizahidraja/56beaadf493976182f38aa602b8958e2")
    print("=" * 64)


if __name__ == "__main__":
    main()
