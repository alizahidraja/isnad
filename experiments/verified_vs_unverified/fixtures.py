"""Hand-authored scenarios for the verified-vs-unverified A/B demonstration.

THIS FILE KNOWS GROUND TRUTH.  It is the injection manifest, not the
grading logic.  The runner (`run.py`) uses it ONLY at the end, to report
"caught" vs "missed".  The grading/gating path never imports this file.

ISNAD has TWO independent defenses, and an honest demonstration must show
both working AND both failing in concert:

  1. Chain grading (isnād/rijāl)  — catches weak/corrupt transmitters
  2. Content criticism (matn)     — catches wrong content via corpus

A real MISS requires BOTH to fail simultaneously:
  - stale grade    : chain looks sound (narrator still graded RELIABLE) AND
                     corruption is too subtle for the content critic (#4)
  - fabricated chain: chain looks sound (source graded RELIABLE) AND the
                     fabricated claim is plausible (#11)

The six scenarios:
  A. clean pass         — correct claim, sound chain          → served
  B. weak narrator      — weak scraper actually corrupts      → caught (chain)
  C. stale grade        — RELIABLE-but-drifted, subtle error  → MISSED  (#4)
  D. fabricated source  — RELIABLE source, plausible lie      → MISSED  (#11)
  E. corroboration win  — DAIF chain upgraded by 2nd source   → recovered
  F. ilal (contradict)  — sound chain, contradicted content   → review
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Narrators (physics domain)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Narrator:
    narrator_id: str
    narrator_type: str  # source | scraper | model
    grade: str  # reliable | acceptable | weak | rejected | ungraded
    model_family: str | None = None
    upstream_source: str | None = None


NARRATORS: dict[str, Narrator] = {
    # Sources — two genuinely independent textbooks
    "source:openstax-vol3": Narrator(
        "source:openstax-vol3", "source", "reliable", upstream_source="openstax.org"
    ),
    "source:crowell-light-matter": Narrator(
        "source:crowell-light-matter", "source", "reliable", upstream_source="lightandmatter.com"
    ),
    # Scrapers
    "pdf-scraper@1.2": Narrator("pdf-scraper@1.2", "scraper", "acceptable"),
    "pdf-scraper@0.9-legacy": Narrator("pdf-scraper@0.9-legacy", "scraper", "weak"),
    # A scraper still graded RELIABLE but which has silently drifted (stale grade)
    "pdf-scraper@2.0": Narrator("pdf-scraper@2.0", "scraper", "reliable"),
    # Ingest models
    "ingest@good": Narrator("ingest@good", "model", "acceptable", model_family="ingest-good"),
    "ingest@excellent": Narrator(
        "ingest@excellent", "model", "reliable", model_family="ingest-excellent"
    ),
    "ingest@weak": Narrator("ingest@weak", "model", "rejected", model_family="ingest-weak"),
}


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    id: str
    query: str
    chain: list[tuple[str, str]]  # (narrator_id, transform_type)
    claim: str  # the claim the pipeline produces
    correct: bool  # ground truth: is the claim correct?
    failure_mode: str  # human-readable label for the report
    note: str = ""

    @property
    def narrator_ids(self) -> list[str]:
        return [nid for nid, _ in self.chain]


SCENARIOS: list[Scenario] = [
    # A — clean pass (baseline: no false positive)
    Scenario(
        id="A-clean-pass",
        query="What is the momentum of a photon?",
        chain=[
            ("source:openstax-vol3", "pass_through"),
            ("pdf-scraper@1.2", "destructive"),
            ("ingest@good", "generative"),
        ],
        claim="The momentum of a photon is p = h/λ, where h is Planck's constant and λ is the wavelength.",
        correct=True,
        failure_mode="clean",
        note="Sound chain, correct claim. ISNAD serves it. Baseline — no false positive.",
    ),
    # B — weak-narrator corruption (the catch via chain grading)
    Scenario(
        id="B-weak-narrator",
        query="Is mechanical energy conserved in an isolated system?",
        chain=[
            ("source:openstax-vol3", "pass_through"),
            ("pdf-scraper@0.9-legacy", "destructive"),
            ("ingest@good", "generative"),
        ],
        claim="Mechanical energy is NOT conserved in an isolated system without non-conservative forces.",
        correct=False,
        failure_mode="weak-narrator-corruption",
        note="The weak scraper flips 'conserved' → 'not conserved'. The weak link "
        "is real, and ISNAD's weakest-link rule catches it. The content critic "
        "also flags 'not conserved' independently.",
    ),
    # C — stale grade (the MISS, ties to issue #4)
    Scenario(
        id="C-stale-grade",
        query="What is the value of the fine-structure constant?",
        chain=[
            ("source:openstax-vol3", "pass_through"),
            ("pdf-scraper@2.0", "destructive"),
            ("ingest@excellent", "generative"),
        ],
        claim="The fine-structure constant α is approximately 1/137.028.",
        correct=False,
        failure_mode="stale-grade",
        note="The scraper is graded RELIABLE but has silently drifted and now "
        "corrupts the last digits (true value ≈ 1/137.036). The chain is "
        "SAHIH (all reliable), so chain grading passes it. The corruption is "
        "too subtle for the content critic (UNVERIFIABLE). BOTH defenses "
        "fail → served with caveat. This is issue #4 — grades need re-check.",
    ),
    # D — fabricated clean chain (the MISS, ties to issue #11)
    Scenario(
        id="D-fabricated-source",
        query="What happens to the Lorentz factor as velocity approaches c?",
        chain=[
            ("source:crowell-light-matter", "pass_through"),
            ("pdf-scraper@2.0", "destructive"),
            ("ingest@excellent", "generative"),
        ],
        claim="The Lorentz factor γ approaches zero as an object's velocity approaches the speed of light.",
        correct=False,
        failure_mode="fabricated-clean-chain",
        note="Every narrator looks RELIABLE, but the SOURCE itself is wrong on "
        "this point (γ → ∞, not 0, as v → c). A clean chain faithfully "
        "transmitting a fabricated claim. Chain grading cannot see a bad "
        "source behind a clean chain; the content critic returns UNVERIFIABLE "
        "on a plausible-sounding lie. BOTH fail → served. Issue #11.",
    ),
    # E — corroboration win (DAIF upgraded by a second independent source)
    Scenario(
        id="E-corroboration",
        query="Is the speed of light in a vacuum constant?",
        chain=[
            ("source:openstax-vol3", "pass_through"),
            ("pdf-scraper@0.9-legacy", "destructive"),
            ("ingest@good", "generative"),
        ],
        claim="The speed of light in a vacuum is constant, c ≈ 3.0 × 10⁸ m/s.",
        correct=True,
        failure_mode="corroboration",
        note="Chain A is DAIF (weak scraper). But a second independent chain "
        "(Crowell source, different ingest model) asserts the same claim, "
        "upgrading it DAIF → HASAN. Corroboration recovers a claim that "
        "would otherwise need review.",
    ),
    # F — ʿilal (hidden defect): sound chain, contradicted content
    Scenario(
        id="F-ilal",
        query="What is the momentum of a moving object?",
        chain=[
            ("source:openstax-vol3", "pass_through"),
            ("pdf-scraper@1.2", "destructive"),
            ("ingest@good", "generative"),
        ],
        claim="The momentum of a moving object is p = h/λ.",
        correct=False,
        failure_mode="ilal",
        note="Sound chain, but the content contradicts the corpus (classical "
        "p = mv vs quantum p = h/λ — the claim is missing its regime "
        "qualifier). A sound chain carrying contradicted content is the "
        "ʿilal case — routed to human review, not served. Content criticism "
        "catches what chain grading cannot.",
    ),
]

# The second, genuinely independent corroborating chain for scenario E.
# Different source AND different ingest model family, so the independence
# detector does NOT flag it as correlated.
CORROBORATING_CHAIN_FOR_E: list[tuple[str, str]] = [
    ("source:crowell-light-matter", "pass_through"),
    ("pdf-scraper@1.2", "destructive"),
    ("ingest@excellent", "generative"),
]
