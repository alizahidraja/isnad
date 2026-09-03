"""Self-maintaining KB demo — Recipe 1 of docs/onboard-in-a-day.md.

A single runnable script that walks a small knowledge base through the full
isnad pipeline:

1. **SEED** — a registry of prior-only narrators (Estimated, never observed).
2. **INGEST + GRADE** — sample KB claims, each carrying an ordered chain
   (source -> scraper -> model), graded weakest-link.
3. **SURFACE** — print the graded surface: chain grade + provenance + action.
4. **SELF-MAINTAINING LOOP** — new evidence (survival, contradiction,
   quarantine) re-grades a narrator and the served surface changes.
5. **HONEST SURVIVAL** — self-verified survival and duplicate survival are
   refused (no-op), so grades cannot be farmed.

Run::

    uv run python examples/self-maintaining-kb/kb.py

Uses only the public isnad API (``isnad`` and ``isnad.types``). Everything runs
in-memory, so the script is idempotent and needs no API keys or database.
"""

from __future__ import annotations

from dataclasses import dataclass

from isnad import (
    Chain,
    ChainLinkSpec,
    DeterministicRuleCritic,
    Registry,
    adalah_grades_for_chain,
    decide,
    gate_serve,
    grade_chain,
    grades_for_chain,
    make_claim_id,
    normalize_claim_text,
)
from isnad.types import (
    Action,
    ChainGrade,
    ContentVerdict,
    NarratorGrade,
    NarratorType,
    TransformType,
)

DOMAIN = "kb"

CLAIM_A = "Noor 3.1 shipped on 2026-08-29"
CHAIN_A = ["source:internal-docs"]

CLAIM_B = "Noor 3.1 requires Python 3.13"
CHAIN_B = ["source:internal-docs", "scraper:web-generic"]

CLAIM_C = "Noor 3.1 has no known bugs"
CHAIN_C = ["source:fabricated-bot"]

# The KB's known facts. DeterministicRuleCritic is an exact-match stub:
# CONSISTENT means "the claim is verbatim a fact the KB already holds" (not
# semantic agreement). A production KB swaps in an embedding/LLM critic.
CORPUS_DOCS = {
    "A": "Noor 3.1 shipped on 2026-08-29",
    "B": "Noor 3.1 requires Python 3.13",
    "C": "",
}


CLAIMS: dict[str, tuple[str, list[str]]] = {
    "A": (CLAIM_A, CHAIN_A),
    "B": (CLAIM_B, CHAIN_B),
    "C": (CLAIM_C, CHAIN_C),
}


def build_chain(narrator_ids: list[str]) -> Chain:
    """Build a PASS_THROUGH chain — one link per narrator, step = index."""
    return Chain([
        ChainLinkSpec(
            narrator_id,
            step=i,
            domain=DOMAIN,
            transform_type=TransformType.PASS_THROUGH,
        )
        for i, narrator_id in enumerate(narrator_ids)
    ])


def content_verdict_for(claim_text: str, corpus_doc: str) -> ContentVerdict:
    """Run the deterministic rule critic against one corpus document."""
    normalized = normalize_claim_text(claim_text)
    corpus = [normalize_claim_text(corpus_doc)] if corpus_doc.strip() else []
    return DeterministicRuleCritic().evaluate(claim_text, normalized, corpus, DOMAIN)


@dataclass
class ClaimVerdict:
    """The graded surface of one claim: chain grade, content, action, provenance."""

    claim_id: str
    text: str
    chain_grade: ChainGrade
    content_verdict: ContentVerdict
    action: Action
    weakest_link: str
    weakest_grade: NarratorGrade
    prior_only: bool

    @property
    def why(self) -> str:
        return (
            f"chain {self.chain_grade.value.upper()} — weakest link {self.weakest_link} "
            f"({self.weakest_grade.value}); content {self.content_verdict.value.upper()} → "
            f"{self.action.value}"
        )

    @property
    def provenance(self) -> str:
        return "prior-only" if self.prior_only else "observation-backed"


def prior_only_narrators(reg: Registry, chain: Chain) -> list[str]:
    """Narrator ids in the chain whose grade rests on priors, not observations."""
    return [
        link.narrator_id
        for link in chain.links
        if reg.evidence_provenance(link.narrator_id, link.domain).prior_only
    ]


def grade_claim(
    reg: Registry,
    claim_text: str,
    narrator_ids: list[str],
    corpus_doc: str,
) -> ClaimVerdict:
    """Grade one claim: chain grade (weakest-link) -> content -> action."""
    chain = build_chain(narrator_ids)
    link_grades = grades_for_chain(reg, chain)
    link_transforms = [link.transform_type for link in chain.links]
    link_adalah = adalah_grades_for_chain(reg, chain)
    chain_grade = grade_chain(
        link_grades,
        link_transforms,
        chain.is_complete,
        link_adalah_grades=link_adalah,
    )
    content_verdict = content_verdict_for(claim_text, corpus_doc)
    action = gate_serve(
        decide(chain_grade, content_verdict),
        prior_only_narrators(reg, chain),
    )
    weakest_idx = min(range(len(chain.links)), key=lambda i: link_grades[i])
    return ClaimVerdict(
        claim_id=make_claim_id(claim_text),
        text=claim_text,
        chain_grade=chain_grade,
        content_verdict=content_verdict,
        action=action,
        weakest_link=chain.links[weakest_idx].narrator_id,
        weakest_grade=link_grades[weakest_idx],
        prior_only=bool(prior_only_narrators(reg, chain)),
    )


def served_surface(verdicts: list[ClaimVerdict]) -> list[ClaimVerdict]:
    """The served surface: only SERVE / SERVE_WITH_CAVEAT verdicts."""
    return [v for v in verdicts if v.action in (Action.SERVE, Action.SERVE_WITH_CAVEAT)]


def surface_label(verdicts: dict[str, ClaimVerdict]) -> str:
    """Human-readable served-surface label, e.g. ``A (serve_with_caveat)``."""
    served = [
        f"{label} ({v.action.value})"
        for label, v in verdicts.items()
        if v.action in (Action.SERVE, Action.SERVE_WITH_CAVEAT)
    ]
    return ", ".join(served) if served else "(empty)"


def seed_priors(reg: Registry) -> None:
    """Seed the demo narrators as prior-only BOOTSTRAP_SEED evidence."""
    reg.seed(
        "source:internal-docs",
        DOMAIN,
        NarratorGrade.RELIABLE,
        narrator_type=NarratorType.SOURCE,
        source="operator",
    )
    reg.seed(
        "source:changelog",
        DOMAIN,
        NarratorGrade.RELIABLE,
        narrator_type=NarratorType.SOURCE,
        source="operator",
    )
    reg.seed(
        "scraper:web-generic",
        DOMAIN,
        NarratorGrade.WEAK,
        narrator_type=NarratorType.SCRAPER,
        source="extraction-fidelity",
    )
    reg.seed(
        "model:gpt-4o",
        DOMAIN,
        NarratorGrade.ACCEPTABLE,
        narrator_type=NarratorType.MODEL,
        source="benchmark:MMLU",
    )
    reg.seed(
        "source:fabricated-bot",
        DOMAIN,
        NarratorGrade.REJECTED,
        narrator_type=NarratorType.SOURCE,
        source="operator",
    )


def main() -> None:
    reg = Registry()

    print("ISNAD — Self-maintaining KB demo (Recipe 1)")

    print("[1] SEED — provenance is prior (Estimated)")
    seed_priors(reg)
    for narrator_id in (
        "source:internal-docs",
        "source:changelog",
        "scraper:web-generic",
        "model:gpt-4o",
        "source:fabricated-bot",
    ):
        prov = reg.evidence_provenance(narrator_id, DOMAIN)
        grade = reg.get_grade(narrator_id, DOMAIN)
        print(
            f'    {narrator_id:<24} {grade.value:<12} prior_only={prov.prior_only!s:<5} "Estimated"'
        )

    print("[2] INGEST + GRADE")
    verdicts = {
        label: grade_claim(reg, text, chain, CORPUS_DOCS[label])
        for label, (text, chain) in CLAIMS.items()
    }
    for label in ("A", "B", "C"):
        verdict = verdicts[label]
        print(f"    {label}: {verdict.why}  [{verdict.provenance}]")

    print(f"[3] SERVED SURFACE: {surface_label(verdicts)}")

    print("[4] SELF-MAINTAINING RE-GRADE")

    # 4a — survival: a second source (source:changelog) confirms the claim, and
    # the operator records the survival. source:changelog is a registered
    # narrator, so this is a real observation, not a self-seal.
    reg.record_survival(
        "source:internal-docs",
        DOMAIN,
        make_claim_id(CLAIM_A),
        "source:changelog",
    )
    prov = reg.evidence_provenance("source:internal-docs", DOMAIN)
    va_survived = grade_claim(reg, CLAIM_A, CHAIN_A, CORPUS_DOCS["A"])
    print(
        f"    4a survival      source:internal-docs: observation_backed={prov.observation_backed!s}"
    )
    print(
        f"        A: chain {va_survived.chain_grade.value.upper()} "
        f"-> action {va_survived.action.value}  [{va_survived.provenance}]"
    )

    # 4b — contradiction: the operator records a precision (ḍabṭ) strike against
    # the source (a later correction disagrees with the ship date).
    reg.flag_contradiction(
        "source:internal-docs", DOMAIN, "correction: Noor 3.1 shipped 2026-08-30"
    )
    va_contradicted = grade_claim(reg, CLAIM_A, CHAIN_A, CORPUS_DOCS["A"])
    print(
        "    4b contradiction source:internal-docs: "
        f"{reg.get_grade('source:internal-docs', DOMAIN).value}"
    )
    print(
        f"        A: chain {va_contradicted.chain_grade.value.upper()} "
        f"-> {va_contradicted.action.value}  [{va_contradicted.provenance}]"
    )

    # 4c — quarantine: active containment of a rejected narrator.
    reg.quarantine("source:fabricated-bot", DOMAIN, "fabricated claims")
    fabricated = reg.get("source:fabricated-bot", DOMAIN)
    print(
        "    4c quarantine    source:fabricated-bot: "
        f"{fabricated.grade.value} / {fabricated.adalah_grade.value} / "
        f"inactive={not fabricated.is_active}"
    )
    vc_quarantined = grade_claim(reg, CLAIM_C, CHAIN_C, CORPUS_DOCS["C"])
    print(
        "        SERVED SURFACE: "
        + surface_label({"A": va_contradicted, "B": verdicts["B"], "C": vc_quarantined})
    )

    print("[5] HONEST SURVIVAL: self_verified=True -> no-op; duplicate -> no-op")
    grade_before = reg.get_grade("source:internal-docs", DOMAIN)
    observed_before = reg.evidence_provenance("source:internal-docs", DOMAIN).observed_count
    reg.record_survival(
        "source:internal-docs",
        DOMAIN,
        make_claim_id(CLAIM_A),
        "self-seal",
        self_verified=True,
    )
    reg.record_survival(
        "source:internal-docs",
        DOMAIN,
        make_claim_id(CLAIM_A),
        "source:changelog",
    )
    grade_after = reg.get_grade("source:internal-docs", DOMAIN)
    observed_after = reg.evidence_provenance("source:internal-docs", DOMAIN).observed_count
    print(
        f"    grade {grade_before.value} -> {grade_after.value} (unchanged); "
        f"observed evidence {observed_before} -> {observed_after} (both no-ops)"
    )


if __name__ == "__main__":
    main()
