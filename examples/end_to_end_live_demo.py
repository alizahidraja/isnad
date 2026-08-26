"""End-to-end live demonstration of ISNAD on a real example.

Run:  DEEPSEEK_API_KEY=sk-... python examples/end_to_end_live_demo.py

Not a synthetic unit test — this runs the *actual* pipeline (evidence-backed
seeded registry → weakest-link grading → live LLM critic → decision matrix →
tamper-evident, detached-signed audit record) on real physics claims, and
verifies a real Live Verify seal over the network.

It shows, in one pass:
1. A correct claim (in the corpus) → ḥasan chain + CONSISTENT → SERVE_WITH_CAVEAT.
2. A correct *paraphrase* (not verbatim) → the live critic understands it → SERVE.
3. A corrupted claim (wrong value) → CONTRADICTION → REVIEW (held, not served).
4. A REJECTED narrator → MAWDU → REJECT_AND_QUARANTINE_NARRATOR.
5. The audit record for a served claim, detached-signed and verified.
6. A Live Verify seal (Edinburgh MSc) → crypto-anchored ʿadālah on day one.
"""

from __future__ import annotations

from isnad import (
    Chain,
    ChainLinkSpec,
    Registry,
    __version__,
    decide,
    grade_chain,
    seed_from_benchmark,
)
from isnad.audit import (
    GradingStrategy,
    hmac_signer,
    hmac_verifier,
    sign_detached,
    verify_detached,
)
from isnad.audit.exporter import build_audit_record_from_nodes
from isnad.audit.schema import ChainNodeAudit, Environment, WeakestLink
from isnad.critics import LLMCritic
from isnad.integrations.liveverify import register_sealed_source, verify_claim
from isnad.types import (
    Action,
    AdalahGrade,
    ChainGrade,
    ContentVerdict,
    NarratorGrade,
    TransformType,
)

CORPUS = [
    "the speed of light in a vacuum is about three hundred million meters per second",
    "force equals mass times acceleration",
    "energy is conserved in an isolated system",
    "the momentum of a photon is p = h/lambda",
]


def build_registry() -> Registry:
    reg = Registry()
    reg.seed("source:openstax", "physics", NarratorGrade.RELIABLE, source="publisher-reputation")
    reg.seed(
        "pdf-scraper@1.2", "physics", NarratorGrade.RELIABLE, source="extraction-fidelity-suite"
    )
    seed_from_benchmark(reg, "ingest-model@v1", "physics", 0.85, benchmark="published-benchmark")
    return reg


def chain_for() -> Chain:
    return Chain([
        ChainLinkSpec("source:openstax", 0, domain="physics"),
        ChainLinkSpec(
            "pdf-scraper@1.2", 1, domain="physics", transform_type=TransformType.DESTRUCTIVE
        ),
        ChainLinkSpec(
            "ingest-model@v1", 2, domain="physics", transform_type=TransformType.GENERATIVE
        ),
    ])


def grade_and_route(
    reg: Registry, critic: LLMCritic, claim: str
) -> tuple[ChainGrade, ContentVerdict, Action]:
    chain = chain_for()
    grades = [reg.get_grade(link.narrator_id, link.domain) for link in chain.links]
    cg = grade_chain(grades, [link.transform_type for link in chain.links], is_complete=True)
    cv = critic.evaluate(claim, claim.lower(), CORPUS, "physics")
    return cg, cv, decide(cg, cv)


def main() -> None:
    print("=" * 72)
    print("ISNAD — live end-to-end demo")
    print("=" * 72)

    reg = build_registry()
    critic = LLMCritic(provider="deepseek")
    print(
        "\n[registry] source RELIABLE · scraper RELIABLE · "
        "model ACCEPTABLE (evidence-backed seeds)\n"
    )

    cases = [
        (
            "correct (in corpus)",
            "the speed of light in a vacuum is about three hundred million meters per second",
        ),
        (
            "correct (paraphrase)",
            "light travels through empty space at roughly 300 million metres per second",
        ),
        (
            "corrupted (wrong value)",
            "the speed of light in a vacuum is five hundred million meters per second",
        ),
    ]
    for label, claim in cases:
        cg, cv, action = grade_and_route(reg, critic, claim)
        print(f"[{label}]")
        print(f"  {claim}")
        print(f"  chain={cg.value.upper()}  content={cv.value}  ->  {action.value.upper()}\n")

    # ── 4. A rejected narrator → active containment ──
    reg.register(
        "source:poisoned", "physics", grade=NarratorGrade.REJECTED, adalah=AdalahGrade.COMPROMISED
    )
    cg = grade_chain([NarratorGrade.REJECTED], [TransformType.PASS_THROUGH], is_complete=True)
    cv = critic.evaluate(
        "the speed of light in a vacuum is five hundred million meters per second",
        "the speed of light in a vacuum is five hundred million meters per second",
        CORPUS,
        "physics",
    )
    print(f"[rejected narrator] chain={cg.value.upper()} -> {decide(cg, cv).value.upper()}\n")

    # ── 5. Audit record + detached signature ──
    cg, cv, action = grade_and_route(reg, critic, cases[0][1])
    record = build_audit_record_from_nodes(
        claim_id="live-demo-001",
        claim_text=cases[0][1],
        final_grade=cg.value,
        grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
        nodes=[
            ChainNodeAudit(
                "source:openstax", "dataset", "reliable", "publisher-trusted", upstream_ids=[]
            ),
            ChainNodeAudit(
                "pdf-scraper@1.2",
                "scraper",
                "reliable",
                "extraction-fidelity",
                upstream_ids=["source:openstax"],
            ),
            ChainNodeAudit(
                "ingest-model@v1",
                "model",
                "acceptable",
                "benchmark-seeded",
                upstream_ids=["pdf-scraper@1.2"],
            ),
        ],
        weakest_link=WeakestLink("ingest-model@v1", "acceptable", "lowest narrator grade"),
        environment=Environment(__version__, "3.13", "darwin"),
    )
    sign_detached(record, hmac_signer("demo-secret"))
    rh = record.integrity.record_hash[:16]
    ds = (record.integrity.detached_signature or "")[:16]
    print(f"[audit] record_hash={rh}…  detached_signature={ds}…")
    print(f"[audit] signature verifies: {verify_detached(record, hmac_verifier('demo-secret'))}\n")

    # ── 6. Live Verify seal (real, network) ──
    print("[live-verify] verifying a real seal: MSc Computer Science, Edinburgh University …")
    result = verify_claim("MSc Computer Science, Edinburgh University\nverify:degrees.ed.ac.uk/c")
    if result.verified:
        sealed = register_sealed_source(reg, result, domain="education")
        print(
            f"[live-verify] VERIFIED — narrator {sealed.narrator_id} = {sealed.grade.value} "
            f"(ʿadālah {sealed.adalah.value}; self_verified={result.self_verified})"
        )
    else:
        print(f"[live-verify] not verified (status={result.status}) — network may be unavailable")


if __name__ == "__main__":
    main()
