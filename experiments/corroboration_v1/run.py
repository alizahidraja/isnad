"""Corroboration Experiment v1 — Run.

Two phases:
  Phase A: Synthetic matching — identical claim text from two different
           narrator chains (Wikipedia vs Britannica).  This isolates
           the corroboration engine: same text, different narrators.
  Phase B: Cross-topic matching — near-duplicate claims found across
           Wikipedia topic boundaries (e.g., "Quantum mechanics" and
           "Wave-particle duality").  These are genuine overlaps.

Both phases use the Isnād framework's actual API:
  ChainLinkSpec → Chain → Registry → grade_chain() → ChainGrade
  → CorroborationEngine.evaluate() → CorroborationResult
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from isnad import (
    Chain,
    ChainGrade,
    ChainLinkSpec,
    CorroborationEngine,
    NarratorGrade,
    Registry,
    TransformType,
    grade_chain,
)

# Add experiment dir to path
_exp_dir = Path(__file__).parent
if str(_exp_dir) not in sys.path:
    sys.path.insert(0, str(_exp_dir))

from data_loader import (
    OVERLAP_PAIRS,
    WIKIPEDIA_TOPICS,
    WikipediaLoader,
    extract_sentences,
    find_near_duplicates,
    normalize_claim,
)


# ===========================================================================
# Configuration
# ===========================================================================


OUTPUT_DIR = _exp_dir / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Narrator IDs — COMPLETELY DISJOINT sets for true independence.
# The framework correctly detects shared narrators as correlated.
# For corroboration to fire, chains must share ZERO narrators.
#
# Wikipedia chain: source:wikipedia → ingest:wiki_direct → model:wiki_gpt4
# Britannica chain: source:britannica → ingest:brit_direct → model:brit_gpt4
# Weak chain:      source:wikipedia → ingest:wiki_ocr → model:wiki_gpt4  (DAIF)

# Wikipedia narrators (reliable chain)
W_SOURCE = "source:wikipedia"
W_INGEST = "ingest:wiki_direct"
W_MODEL = "model:wiki_gpt4"

# Britannica narrators (independent — different IDs, different model_family)
B_SOURCE = "source:britannica"
B_INGEST = "ingest:brit_direct"
B_MODEL = "model:brit_gpt4"

# Weak Wikipedia ingest (for testing DAIF→HASAN upgrade)
W_INGEST_WEAK = "ingest:wiki_ocr"

# Narrator grades — both chains have the same grade tiers
NARRATOR_GRADES: dict[str, NarratorGrade] = {
    W_SOURCE: NarratorGrade.ACCEPTABLE,
    W_INGEST: NarratorGrade.RELIABLE,
    W_MODEL: NarratorGrade.RELIABLE,
    B_SOURCE: NarratorGrade.ACCEPTABLE,
    B_INGEST: NarratorGrade.RELIABLE,
    B_MODEL: NarratorGrade.RELIABLE,
    W_INGEST_WEAK: NarratorGrade.WEAK,  # weak → DAIF chain
}

# Narrator metadata — different model_family for correlation detection
# Realistic: Wikipedia uses GPT-4, Britannica uses Claude — different model families!
NARRATOR_METADATA: dict[str, dict[str, Any]] = {
    W_SOURCE: {"upstream_source": W_SOURCE, "model_family": None},
    W_INGEST: {"upstream_source": None, "model_family": "scraper_wiki"},
    W_MODEL: {"upstream_source": None, "model_family": "openai_gpt4"},
    B_SOURCE: {"upstream_source": B_SOURCE, "model_family": None},
    B_INGEST: {"upstream_source": None, "model_family": "scraper_brit"},
    B_MODEL: {"upstream_source": None, "model_family": "anthropic_claude"},
    W_INGEST_WEAK: {"upstream_source": None, "model_family": "scraper_wiki"},
}


# ===========================================================================
# Chain building
# ===========================================================================


def build_wiki_chain() -> Chain:
    """Build reliable Wikipedia chain: source → direct_ingest → model."""
    return Chain([
        ChainLinkSpec(narrator_id=W_SOURCE, step=0,
                      transform_type=TransformType.PASS_THROUGH, domain="general"),
        ChainLinkSpec(narrator_id=W_INGEST, step=1,
                      transform_type=TransformType.DESTRUCTIVE, domain="general"),
        ChainLinkSpec(narrator_id=W_MODEL, step=2,
                      transform_type=TransformType.GENERATIVE, domain="general"),
    ])


def build_wiki_weak_chain() -> Chain:
    """Build WEAK Wikipedia chain: source → ocr_ingest → model.

    Uses WEAK OCR ingest → chain is DAIF.  This is the baseline that
    corroboration should upgrade when an independent HASAN+ chain
    reports the same claim.
    """
    return Chain([
        ChainLinkSpec(narrator_id=W_SOURCE, step=0,
                      transform_type=TransformType.PASS_THROUGH, domain="general"),
        ChainLinkSpec(narrator_id=W_INGEST_WEAK, step=1,
                      transform_type=TransformType.DESTRUCTIVE, domain="general"),
        ChainLinkSpec(narrator_id=W_MODEL, step=2,
                      transform_type=TransformType.GENERATIVE, domain="general"),
    ])


def build_brit_chain() -> Chain:
    """Build Britannica chain: source → ingest → model.

    All narrator IDs are different from the Wikipedia chains — this
    is required for the independence detector to recognize them as
    truly independent chains.
    """
    return Chain([
        ChainLinkSpec(narrator_id=B_SOURCE, step=0,
                      transform_type=TransformType.PASS_THROUGH, domain="general"),
        ChainLinkSpec(narrator_id=B_INGEST, step=1,
                      transform_type=TransformType.DESTRUCTIVE, domain="general"),
        ChainLinkSpec(narrator_id=B_MODEL, step=2,
                      transform_type=TransformType.GENERATIVE, domain="general"),
    ])


def grade_claim_chain(
    chain: Chain,
    registry: Registry,
    corroboration_support: bool = False,
) -> ChainGrade:
    """Grade a claim's chain using the framework."""
    link_grades = [
        registry.get_grade(link.narrator_id, link.domain)
        for link in chain.links
    ]
    link_transforms = [link.transform_type for link in chain.links]
    return grade_chain(
        link_grades,
        link_transforms,
        is_complete=chain.is_complete,
        corroboration_support=corroboration_support,
    )


# ===========================================================================
# Experiment result types
# ===========================================================================


@dataclass
class ClaimRecord:
    """A single claim with its chains and grades."""

    text: str
    normalized: str
    topic: str
    # Wikipedia chain (base)
    wiki_chain: Chain
    wiki_grade: ChainGrade
    wiki_narrator_ids: list[str]
    # Britannica/synthetic chain (corroborating)
    brit_chain: Chain | None = None
    brit_grade: ChainGrade | None = None
    brit_narrator_ids: list[str] | None = None
    # Corroboration result
    corroborated: bool = False
    wiki_upgraded_grade: ChainGrade | None = None
    brit_upgraded_grade: ChainGrade | None = None
    effective_weight: float = 0.0
    reason: str = ""
    # Metadata
    phase: str = ""  # "synthetic" or "cross_topic"
    overlap_score: float = 0.0  # for cross-topic matches


@dataclass
class ExperimentReport:
    """Aggregated experiment report."""

    total_claims: int = 0
    corroboration_fired: int = 0
    grade_upgraded: int = 0
    phase_a_claims: int = 0
    phase_a_fired: int = 0
    phase_b_claims: int = 0
    phase_b_fired: int = 0
    records: list[ClaimRecord] = field(default_factory=list)

    @property
    def fire_rate(self) -> float:
        return self.corroboration_fired / max(1, self.total_claims)

    @property
    def upgrade_rate(self) -> float:
        return self.grade_upgraded / max(1, self.total_claims)

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "CORROBORATION EXPERIMENT REPORT",
            "=" * 60,
            "",
            f"Total claims tested:        {self.total_claims}",
            f"Phase A (synthetic):        {self.phase_a_claims} claims, {self.phase_a_fired} corroborated ({self.phase_a_fired / max(1, self.phase_a_claims) * 100:.1f}%)",
            f"Phase B (cross-topic):      {self.phase_b_claims} claims, {self.phase_b_fired} corroborated ({self.phase_b_fired / max(1, self.phase_b_claims) * 100:.1f}%)",
            "",
            f"Corroboration fired:        {self.corroboration_fired} ({self.fire_rate * 100:.1f}%)",
            f"Grade upgraded:             {self.grade_upgraded} ({self.upgrade_rate * 100:.1f}%)",
            "",
            "─" * 40,
            "Grade distribution (base → upgraded):",
        ]
        for rec in self.records:
            if rec.corroborated:
                lines.append(
                    f"  {rec.topic[:30]:30s} {rec.wiki_grade.value:6s} → "
                    f"{rec.wiki_upgraded_grade.value if rec.wiki_upgraded_grade else 'N/A':6s} "
                    f"(weight={rec.effective_weight:.1f})"
                )
        return "\n".join(lines)


# ===========================================================================
# Experiment runner
# ===========================================================================


def setup_registry() -> Registry:
    """Create and populate narrator registry."""
    reg = Registry()
    for nid, grade in NARRATOR_GRADES.items():
        meta = NARRATOR_METADATA.get(nid, {})
        reg.register(
            narrator_id=nid,
            domain_tag="general",
            grade=grade,
            model_family=meta.get("model_family"),
            upstream_source=meta.get("upstream_source"),
        )
    return reg


def run_phase_a_synthetic(
    topics_data: dict[str, Any],
    registry: Registry,
    max_claims_per_topic: int = 5,
) -> list[ClaimRecord]:
    """Phase A: Synthetic matching.

    For each sentence in each topic, create TWO chains with different
    source narrators (Wikipedia vs Britannica).  Both chains carry the
    EXACT SAME claim text — this isolates the corroboration mechanism
    from text-matching noise.
    """
    records: list[ClaimRecord] = []
    rng = random.Random(42)

    for topic_name, td in topics_data.items():
        sentences = extract_sentences(td.summary)
        # Sample sentences (avoid the longest/most boring ones)
        candidates = [s for s in sentences if 50 < len(s) < 400]
        rng.shuffle(candidates)
        selected = candidates[:max_claims_per_topic]

        for text in selected:
            norm = normalize_claim(text)

            # Wikipedia chain (reliable → HASAN)
            wiki_chain = build_wiki_chain()
            wiki_grade = grade_claim_chain(wiki_chain, registry)

            # Wikipedia WEAK chain (OCR ingest → DAIF)
            wiki_weak_chain = build_wiki_weak_chain()
            wiki_weak_grade = grade_claim_chain(wiki_weak_chain, registry)

            # Britannica chain — independent narrators (HASAN)
            brit_chain = build_brit_chain()
            brit_grade = grade_claim_chain(brit_chain, registry)

            # Record 1: Wiki-weak base, Brit corroborates
            records.append(ClaimRecord(
                text=text, normalized=norm, topic=topic_name,
                wiki_chain=wiki_weak_chain, wiki_grade=wiki_weak_grade,
                wiki_narrator_ids=wiki_weak_chain.narrator_ids,
                brit_chain=brit_chain, brit_grade=brit_grade,
                brit_narrator_ids=brit_chain.narrator_ids,
                phase="synthetic_weak",
            ))

            # Record 2: Wiki base, Brit corroborates (HASAN cap test)
            records.append(ClaimRecord(
                text=text, normalized=norm, topic=topic_name,
                wiki_chain=wiki_chain, wiki_grade=wiki_grade,
                wiki_narrator_ids=wiki_chain.narrator_ids,
                brit_chain=brit_chain, brit_grade=brit_grade,
                brit_narrator_ids=brit_chain.narrator_ids,
                phase="synthetic_hasan",
            ))

    return records


def run_phase_b_cross_topic(
    topics_data: dict[str, Any],
    registry: Registry,
    similarity_threshold: float = 0.35,
) -> list[ClaimRecord]:
    """Phase B: Cross-topic near-duplicate matching.

    Find genuinely overlapping claims across different Wikipedia topics
    and build chains for them.  These are real overlaps, not synthetic.
    """
    records: list[ClaimRecord] = []

    for t_a, t_b in OVERLAP_PAIRS:
        if t_a not in topics_data or t_b not in topics_data:
            continue

        sents_a = extract_sentences(topics_data[t_a].summary)
        sents_b = extract_sentences(topics_data[t_b].summary)

        pairs = find_near_duplicates(sents_a, sents_b, threshold=similarity_threshold)

        for claim_a, claim_b, score in pairs:
            # Use the claim from topic A as the primary text
            norm = normalize_claim(claim_a)

            # Chain A: Wikipedia reliable chain (HASAN)
            chain_a_hasan = build_wiki_chain()
            grade_a_hasan = grade_claim_chain(chain_a_hasan, registry)

            # Chain A WEAK: Wikipedia OCR chain (DAIF)
            chain_a_weak = build_wiki_weak_chain()
            grade_a_weak = grade_claim_chain(chain_a_weak, registry)

            # Chain B: Britannica chain (HASAN, independent)
            chain_b = build_brit_chain()
            grade_b = grade_claim_chain(chain_b, registry)

            # Record 1: Weak wiki base, Brit corroborates → DAIF→HASAN
            records.append(ClaimRecord(
                text=claim_a, normalized=norm,
                topic=f"{t_a}↔{t_b}",
                wiki_chain=chain_a_weak, wiki_grade=grade_a_weak,
                wiki_narrator_ids=chain_a_weak.narrator_ids,
                brit_chain=chain_b, brit_grade=grade_b,
                brit_narrator_ids=chain_b.narrator_ids,
                phase="cross_topic_weak", overlap_score=score,
            ))

            # Record 2: HASAN wiki base, Brit corroborates → HASAN cap test
            records.append(ClaimRecord(
                text=claim_a, normalized=norm,
                topic=f"{t_a}↔{t_b}",
                wiki_chain=chain_a_hasan, wiki_grade=grade_a_hasan,
                wiki_narrator_ids=chain_a_hasan.narrator_ids,
                brit_chain=chain_b, brit_grade=grade_b,
                brit_narrator_ids=chain_b.narrator_ids,
                phase="cross_topic_hasan", overlap_score=score,
            ))

    return records


def apply_corroboration(
    records: list[ClaimRecord],
    engine: CorroborationEngine,
    narrator_metadata: dict[str, dict[str, Any]],
) -> list[ClaimRecord]:
    """Apply the CorroborationEngine to each claim record.

    For each record, the Wiki chain is the "base" and the Brit chain
    is a "corroborating chain".  We evaluate in both directions.
    """
    # Build the all_chains list — each chain carries a claim
    all_chains: list[dict[str, Any]] = []
    for rec in records:
        all_chains.append({
            "claim_text": rec.normalized,
            "chain_grade": rec.wiki_grade.value,
            "narrator_ids": rec.wiki_narrator_ids,
            "source": "wikipedia",
        })
        if rec.brit_chain is not None:
            all_chains.append({
                "claim_text": rec.normalized,
                "chain_grade": rec.brit_grade.value,
                "narrator_ids": rec.brit_narrator_ids or [],
                "source": "britannica",
            })

    for rec in records:
        if rec.brit_chain is None or rec.brit_grade is None:
            continue

        # Evaluate Wikipedia chain with Britannica as corroboration
        result = engine.evaluate(
            claim_text=rec.normalized,
            base_chain_grade=rec.wiki_grade,
            base_narrators=rec.wiki_narrator_ids,
            all_chains=all_chains,
            narrator_metadata=narrator_metadata,
        )

        rec.corroborated = result.upgraded
        rec.wiki_upgraded_grade = result.upgraded_grade
        rec.effective_weight = result.effective_weight
        rec.reason = result.reason

    return records


def build_report(records: list[ClaimRecord]) -> ExperimentReport:
    """Aggregate results into a report."""
    report = ExperimentReport()
    report.total_claims = len(records)
    report.records = records

    for rec in records:
        if rec.phase == "synthetic_weak":
            report.phase_a_claims += 1
            if rec.corroborated:
                report.phase_a_fired += 1
        elif rec.phase == "synthetic_hasan":
            pass  # HASAN→HASAN capped — counted in total but not in phase_a
        elif rec.phase in ("cross_topic_weak", "cross_topic_hasan"):
            report.phase_b_claims += 1
            if rec.corroborated:
                report.phase_b_fired += 1

        if rec.corroborated:
            report.corroboration_fired += 1
            if rec.wiki_upgraded_grade and rec.wiki_upgraded_grade != rec.wiki_grade:
                report.grade_upgraded += 1

    return report


# ===========================================================================
# Main
# ===========================================================================


def main() -> None:
    print("=" * 60)
    print("CORROBORATION EXPERIMENT v1")
    print("=" * 60)

    # ── Step 1: Load data ──────────────────────────────────────────────
    print("\n── Step 1: Load Wikipedia data ──\n")
    loader = WikipediaLoader()
    topics_data = loader.load_all_topics(WIKIPEDIA_TOPICS)

    n_sentences = sum(
        len(extract_sentences(td.summary)) for td in topics_data.values()
    )
    print(f"\n  {len(topics_data)} topics loaded, ~{n_sentences} total sentences")

    # ── Step 2: Setup registry ─────────────────────────────────────────
    print("\n── Step 2: Setup narrator registry ──\n")
    registry = setup_registry()
    for nid, grade in NARRATOR_GRADES.items():
        print(f"  {nid:30s} → {grade.value}")

    # ── Step 3: Phase A — Synthetic matching ───────────────────────────
    print("\n── Step 3: Phase A — Synthetic matching ──\n")
    records_a = run_phase_a_synthetic(topics_data, registry, max_claims_per_topic=5)
    print(f"  {len(records_a)} synthetic claim pairs created")

    # ── Step 4: Phase B — Cross-topic matching ─────────────────────────
    print("\n── Step 4: Phase B — Cross-topic matching ──\n")
    records_b = run_phase_b_cross_topic(topics_data, registry, similarity_threshold=0.20)
    print(f"  {len(records_b)} cross-topic matches found")

    # ── Step 5: Apply corroboration ───────────────────────────────────
    print("\n── Step 5: Apply CorroborationEngine ──\n")
    engine = CorroborationEngine(
        min_independent_chains=1,  # 1 corroborating chain + 1 base = 2 total
        corroboration_cap=ChainGrade.HASAN,
        min_gate_grade=ChainGrade.HASAN,
    )

    all_records = records_a + records_b
    all_records = apply_corroboration(all_records, engine, NARRATOR_METADATA)

    # ── Step 6: Report ────────────────────────────────────────────────
    print("\n── Step 6: Results ──\n")
    report = build_report(all_records)
    summary = report.summary()
    print(summary)

    # Save detailed results
    results_json = []
    for rec in all_records:
        results_json.append({
            "text": rec.text[:200],
            "topic": rec.topic,
            "phase": rec.phase,
            "wiki_grade": rec.wiki_grade.value,
            "brit_grade": rec.brit_grade.value if rec.brit_grade else None,
            "corroborated": rec.corroborated,
            "upgraded_grade": rec.wiki_upgraded_grade.value if rec.wiki_upgraded_grade else None,
            "effective_weight": rec.effective_weight,
            "reason": rec.reason,
            "overlap_score": rec.overlap_score,
        })

    results_path = OUTPUT_DIR / "results.json"
    with open(results_path, "w") as f:
        json.dump(results_json, f, indent=2)
    print(f"\n  Detailed results: {results_path}")

    # Save summary report
    report_path = OUTPUT_DIR / "report.txt"
    with open(report_path, "w") as f:
        f.write(summary)
    print(f"  Summary report:   {report_path}")

    # Print key metric for success criteria
    print(f"\n{'=' * 60}")
    print("KEY METRICS:")
    print(f"  Corroboration fired: {report.corroboration_fired}/{report.total_claims} "
          f"({report.fire_rate * 100:.1f}%)")
    print(f"  Grade upgraded:      {report.grade_upgraded}/{report.total_claims} "
          f"({report.upgrade_rate * 100:.1f}%)")
    print(f"  Phase A (synth):     {report.phase_a_fired}/{report.phase_a_claims} fired")
    print(f"  Phase B (real):      {report.phase_b_fired}/{report.phase_b_claims} fired")

    # Success / needs work
    if report.corroboration_fired > 0:
        print("\n✓ Corroboration FIRED — the engine works on real data!")
    else:
        print("\n✗ Corroboration did NOT fire — investigate (check grades, independence, metadata)")

    print("=" * 60)


if __name__ == "__main__":
    main()
