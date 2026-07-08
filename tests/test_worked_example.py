"""FlagShip Integration Test — the paper's worked example (§4.5), verbatim.

This test ties the repo directly to the paper and is the centerpiece
featured in the README.

Verifies the full end-to-end pipeline on the claim:
  "the momentum of a photon is p = h/λ"

Ingested from OpenStax Vol. 3 through:
  [source → pdf-scraper v1.2 → ingest-analysis M@v (ungraded) → ingest-renderer M@v (ungraded)]

Contradicting an existing "p = mv" claim.
"""

from isnad.core.chain import Chain, ChainLinkSpec, make_claim_id, normalize_claim_text
from isnad.core.grading import grade_chain
from isnad.matn import DeterministicRuleCritic
from isnad.core.decision import decide, describe_action
from isnad.core.registry import Registry
from isnad.types import (
    Action,
    AdalahGrade,
    ChainGrade,
    ContentVerdict,
    DabtGrade,
    NarratorGrade,
    NarratorType,
    TransformType,
)


def test_paper_worked_example_hasan_contradiction() -> None:
    """Paper §4.5: ungraded chain → ḥasan × contradiction → review queue.

    The claim "the momentum of a photon is p = h/λ" ingested from
    OpenStax Vol. 3 through:
    [source → pdf-scraper v1.2 → ingest-analysis M@v (ungraded) →
     ingest-renderer M@v (ungraded)]

    Contradicts existing "p = mv" claim → routed to review, not served.
    """
    # --- 1. Build the transmission chain ---
    chain = Chain(
        [
            ChainLinkSpec(
                "openstax-v3",
                step=0,
                version="latest",
                transform_type=TransformType.PASS_THROUGH,
                domain="physics-quantum",
                trace_id="trace-001",
            ),
            ChainLinkSpec(
                "pdf-scraper",
                step=1,
                version="1.2",
                transform_type=TransformType.DESTRUCTIVE,
                domain="physics-quantum",
                trace_id="trace-002",
            ),
            ChainLinkSpec(
                "ingest-analysis",
                step=2,
                version="v",
                transform_type=TransformType.GENERATIVE,
                domain="physics-quantum",
                trace_id="trace-003",
            ),
            ChainLinkSpec(
                "ingest-renderer",
                step=3,
                version="v",
                transform_type=TransformType.GENERATIVE,
                domain="physics-quantum",
                trace_id="trace-004",
            ),
        ]
    )

    assert chain.is_complete, "Chain must be complete (ittiṣāl holds)"
    assert len(chain.links) == 4

    # --- 2. Set up the narrator registry ---
    reg = Registry()

    # Source: publisher-trusted (ʿadālah high)
    reg.register(
        "openstax-v3",
        "physics-quantum",
        narrator_type=NarratorType.SOURCE,
        grade=NarratorGrade.RELIABLE,
        adalah=AdalahGrade.HIGH,
    )

    # PDF scraper: high extraction fidelity
    reg.register(
        "pdf-scraper",
        "physics-quantum",
        narrator_type=NarratorType.SCRAPER,
        grade=NarratorGrade.RELIABLE,
        dabt=DabtGrade.HIGH,
        model_version="1.2",
    )

    # Both ingest models: UNGRADED (recent version bump)
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

    # --- 3. Grade the chain ---
    link_grades = [reg.get_grade(link.narrator_id, link.domain) for link in chain.links]
    link_transforms = [link.transform_type for link in chain.links]

    assert link_grades == [
        NarratorGrade.RELIABLE,  # source
        NarratorGrade.RELIABLE,  # scraper
        NarratorGrade.UNGRADED,  # ingest-analysis
        NarratorGrade.UNGRADED,  # ingest-renderer
    ]

    chain_grade = grade_chain(
        link_grades,
        link_transforms,
        is_complete=chain.is_complete,
    )

    # Two ungraded links → HASAN tier (not SAHIH, not DAIF)
    assert chain_grade == ChainGrade.HASAN, (
        f"Expected HASAN (complete but two ungraded links), got {chain_grade}"
    )

    # --- 4. Matn criticism: detect contradiction ---
    claim_text = "the momentum of a photon is p = h/λ"
    normalized = normalize_claim_text(claim_text)
    corpus = ["momentum p = mv"]  # existing claim from classical physics

    critic = DeterministicRuleCritic()
    content_verdict = critic.evaluate(claim_text, normalized, corpus)

    # Should detect contradiction (p=hv vs p=mv pattern)
    assert content_verdict == ContentVerdict.CONTRADICTION, (
        f"Expected CONTRADICTION, got {content_verdict}"
    )

    # --- 5. Decision matrix ---
    action = decide(chain_grade, content_verdict)

    # ḥasan × contradiction → REVIEW; do not serve
    assert action == Action.REVIEW, f"Expected REVIEW (ḥasan × contradiction), got {action}"

    # Verify it's NOT served
    assert action != Action.SERVE
    assert action != Action.SERVE_WITH_CAVEAT
    assert action != Action.QUARANTINE

    description = describe_action(chain_grade, content_verdict)
    assert "review" in description.lower()


def test_paper_worked_example_sahih_contradiction() -> None:
    """Paper §4.5 continued: if both ingest steps were RELIABLE in quantum domain,
    the same claim lands in the ṣaḥīḥ × contradiction (ʿilal) cell.

    This is the difference the framework adds: the chain quality tells
    the reviewer which to trust more.
    """
    # --- Build the same chain ---
    chain = Chain(
        [
            ChainLinkSpec(
                "openstax-v3",
                step=0,
                domain="physics-quantum",
                transform_type=TransformType.PASS_THROUGH,
            ),
            ChainLinkSpec(
                "pdf-scraper",
                step=1,
                domain="physics-quantum",
                transform_type=TransformType.DESTRUCTIVE,
            ),
            ChainLinkSpec(
                "ingest-analysis",
                step=2,
                domain="physics-quantum",
                transform_type=TransformType.GENERATIVE,
            ),
            ChainLinkSpec(
                "ingest-renderer",
                step=3,
                domain="physics-quantum",
                transform_type=TransformType.GENERATIVE,
            ),
        ]
    )

    # --- Registry: all narrators RELIABLE in physics-quantum ---
    reg = Registry()
    for nid in ["openstax-v3", "pdf-scraper", "ingest-analysis", "ingest-renderer"]:
        reg.register(nid, "physics-quantum", grade=NarratorGrade.RELIABLE)

    link_grades = [reg.get_grade(link.narrator_id, link.domain) for link in chain.links]
    assert all(g == NarratorGrade.RELIABLE for g in link_grades)

    chain_grade = grade_chain(
        link_grades,
        [link.transform_type for link in chain.links],
        is_complete=chain.is_complete,
    )

    # All RELIABLE + complete → SAHIH
    assert chain_grade == ChainGrade.SAHIH

    # --- Matn: same contradiction ---
    critic = DeterministicRuleCritic()
    content_verdict = critic.evaluate(
        "the momentum of a photon is p = h/λ",
        normalize_claim_text("the momentum of a photon is p = h/λ"),
        ["momentum p = mv"],
    )
    assert content_verdict == ContentVerdict.CONTRADICTION

    # --- Decision matrix: SAHIH × CONTRADICTION → REVIEW (ʿilal) ---
    action = decide(chain_grade, content_verdict)
    assert action == Action.REVIEW

    description = describe_action(chain_grade, content_verdict)
    assert "ʿilal" in description.lower() or "highest-value" in description.lower()


def test_paper_worked_example_claim_id_is_deterministic() -> None:
    """The claim_id should be a deterministic hash of the normalized text."""
    claim = "the momentum of a photon is p = h/λ"
    cid1 = make_claim_id(claim)
    cid2 = make_claim_id(claim)
    assert cid1 == cid2
    assert len(cid1) == 64  # SHA-256 hex


def test_paper_worked_example_with_version_bump() -> None:
    """If ingest-analysis is version-bumped, it resets to UNGRADED."""
    reg = Registry()
    reg.register(
        "ingest-analysis",
        "physics-quantum",
        grade=NarratorGrade.RELIABLE,
        model_version="v1",
    )

    assert reg.get_grade("ingest-analysis", "physics-quantum") == NarratorGrade.RELIABLE

    reg.bump_version("ingest-analysis", "physics-quantum", "v2")
    assert reg.get_grade("ingest-analysis", "physics-quantum") == NarratorGrade.UNGRADED
