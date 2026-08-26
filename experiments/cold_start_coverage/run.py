"""Cold-start coverage measurement (issue #33).

With evidence-backed seeding (``Registry.seed``), a seeded pipeline can serve —
but coverage is still bound by the content critic: a claim only SERVEs when the
critic returns CONSISTENT. This measures, for a set of clean claims that a seeded
pipeline *should* serve, what fraction the decision matrix actually serves under
each critic.

Run:
    DEEPSEEK_API_KEY=sk-... python experiments/cold_start_coverage/run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from isnad import Chain, ChainLinkSpec, Registry, decide, grade_chain, seed_from_benchmark
from isnad.critics import EmbeddingCritic, HybridCritic, LLMCritic, LocalNLICritic
from isnad.matn import DeterministicRuleCritic
from isnad.types import Action, NarratorGrade, TransformType

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "critic_eval"))
from eval_set import CONSISTENT_CASES, CORPUS  # noqa: E402

DOMAIN = "physics"


def build_registry() -> Registry:
    """A cold-start registry: narrators seeded from their external evidence."""
    reg = Registry()
    # A publisher's reputation seeds the source's integrity.
    reg.seed("source:openstax", DOMAIN, NarratorGrade.RELIABLE, source="publisher")
    # An extraction-fidelity suite seeds the scraper's precision.
    reg.seed("pdf-scraper@1.2", DOMAIN, NarratorGrade.RELIABLE, source="extraction-fidelity")
    # A published benchmark accuracy seeds the model's precision.  0.85 → ACCEPTABLE,
    # so the chain grades ḥasan (not ṣaḥīḥ) — the case where the critic decides.
    seed_from_benchmark(reg, "ingest-model@v1", DOMAIN, 0.85, benchmark="mmlu")
    return reg


def chain_for() -> Chain:
    return Chain([
        ChainLinkSpec("source:openstax", 0, domain=DOMAIN),
        ChainLinkSpec(
            "pdf-scraper@1.2", 1, domain=DOMAIN, transform_type=TransformType.DESTRUCTIVE
        ),
        ChainLinkSpec("ingest-model@v1", 2, domain=DOMAIN, transform_type=TransformType.GENERATIVE),
    ])


def measure_coverage(critic, registry: Registry, claims: list[str], corpus: list[str]) -> float:
    served = 0
    for claim in claims:
        chain = chain_for()
        grades = [registry.get_grade(l.narrator_id, l.domain) for l in chain.links]
        chain_grade = grade_chain(grades, [l.transform_type for l in chain.links], is_complete=True)
        verdict = critic.evaluate(claim, claim.lower(), corpus, DOMAIN)
        action = decide(chain_grade, verdict)
        if action in (Action.SERVE, Action.SERVE_WITH_CAVEAT):
            served += 1
    return served / len(claims)


def main() -> None:
    reg = build_registry()
    chain_grade = grade_chain(
        [reg.get_grade(l.narrator_id, l.domain) for l in chain_for().links],
        [l.transform_type for l in chain_for().links],
        is_complete=True,
    )
    print(
        f"seeded chain grade: {chain_grade.value.upper()}  "
        f"(source=RELIABLE, scraper=RELIABLE, model=ACCEPTABLE via benchmark)"
    )

    claims = [c for c, _ in CONSISTENT_CASES]  # 20 clean claims the pipeline should serve

    critics = [
        ("DeterministicRuleCritic (stub)", DeterministicRuleCritic()),
        ("EmbeddingCritic (TF-IDF)", EmbeddingCritic()),
        ("LocalNLICritic (DeBERTa NLI)", LocalNLICritic()),
        ("HybridCritic (MiniLM → NLI)", HybridCritic()),
        ("LLMCritic (DeepSeek)", LLMCritic(provider="deepseek")),
    ]

    print(f"\nCoverage on {len(claims)} clean claims (seeded pipeline):")
    for name, critic in critics:
        cov = measure_coverage(critic, reg, claims, CORPUS)
        print(f"  {name:34s} {cov:.0%}")

    print(
        "\nReading: a seeded chain grades ḥasan; the matrix serves it only when the "
        "critic says CONSISTENT (ḥasan × UNVERIFIABLE → REVIEW). Verbatim corpus facts "
        "are CONSISTENT to every critic; the *paraphrases* separate them — the stub/NLI "
        "critics say UNVERIFIABLE and hold them for review, while the LLM critic "
        "understands the paraphrase and serves them."
    )


if __name__ == "__main__":
    main()
