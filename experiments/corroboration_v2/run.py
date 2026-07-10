"""Corroboration Experiment v2 — Semantic matching on dual Wikipedia corpus.

Three phases:
  Phase A: Within-topic — same topic, regular vs simple English Wikipedia.
           Different text, same facts.  Semantic matching to pair claims.
  Phase B: Cross-topic — different regular Wikipedia topics with semantic overlap.
  Phase C: Cross-source within-topic — regular vs simple for same topic,
           exact-sentence pairs (backup for if semantic matching misses).

Uses the Isnād framework with completely disjoint narrator chains
for regular Wikipedia and Simple English Wikipedia sources.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from isnad import (
    Chain, ChainGrade, ChainLinkSpec, CorroborationEngine,
    NarratorGrade, Registry, TransformType, grade_chain,
)

_exp_dir = Path(__file__).parent
if str(_exp_dir) not in sys.path:
    sys.path.insert(0, str(_exp_dir))

from data_loader import (
    TOPICS, DualWikipediaLoader, extract_factual_sentences, normalize_claim,
)
from semantic_matcher import SemanticMatcher, MatchPair, save_matches, load_matches

# ===========================================================================
# Configuration
# ===========================================================================

OUTPUT_DIR = _exp_dir / "results"
MATCHES_DIR = _exp_dir / "matches"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MATCHES_DIR.mkdir(parents=True, exist_ok=True)

# Narrator IDs — COMPLETELY DISJOINT for regular vs simple Wikipedia.
# These reflect the ACTUAL pipeline: source → ingestion.  No LLM.
# Claims are raw extracted sentences, not LLM-processed.

REG_SOURCE = "source:wikipedia"
REG_INGEST = "ingest:wiki_ocr"      # OCR extraction (WEAK → DAIF baseline)
SIM_SOURCE = "source:wikipedia_simple"
SIM_INGEST = "ingest:simple_direct"  # Direct extraction (RELIABLE → HASAN)

NARRATOR_GRADES: dict[str, NarratorGrade] = {
    REG_SOURCE: NarratorGrade.ACCEPTABLE,
    REG_INGEST: NarratorGrade.WEAK,       # WEAK OCR → DAIF chain
    SIM_SOURCE: NarratorGrade.ACCEPTABLE,
    SIM_INGEST: NarratorGrade.RELIABLE,   # Direct → HASAN chain
}

NARRATOR_METADATA: dict[str, dict[str, Any]] = {
    REG_SOURCE: {"upstream_source": "en.wikipedia.org", "model_family": None},
    REG_INGEST: {"upstream_source": None, "model_family": "scraper_wiki"},
    SIM_SOURCE: {"upstream_source": "simple.wikipedia.org", "model_family": None},
    SIM_INGEST: {"upstream_source": None, "model_family": "scraper_simple"},
}


# ===========================================================================
# Chain building — source → ingest only (no LLM — claims are raw sentences)
# ===========================================================================

def build_reg_weak_chain() -> Chain:
    """Weak chain: Wikipedia source → OCR ingestion (DAIF)."""
    return Chain([
        ChainLinkSpec(narrator_id=REG_SOURCE, step=0,
                      transform_type=TransformType.PASS_THROUGH, domain="general"),
        ChainLinkSpec(narrator_id=REG_INGEST, step=1,
                      transform_type=TransformType.DESTRUCTIVE, domain="general"),
    ])


def build_sim_chain() -> Chain:
    """Strong chain: Simple Wikipedia source → direct ingestion (HASAN)."""
    return Chain([
        ChainLinkSpec(narrator_id=SIM_SOURCE, step=0,
                      transform_type=TransformType.PASS_THROUGH, domain="general"),
        ChainLinkSpec(narrator_id=SIM_INGEST, step=1,
                      transform_type=TransformType.DESTRUCTIVE, domain="general"),
    ])


def _grade_chain(chain: Chain, registry: Registry) -> ChainGrade:
    """Grade a chain using the registry."""
    link_grades = [registry.get_grade(l.narrator_id, l.domain) for l in chain.links]
    link_transforms = [l.transform_type for l in chain.links]
    return grade_chain(link_grades, link_transforms, is_complete=chain.is_complete,
                       corroboration_support=False)


# ===========================================================================
# Result types
# ===========================================================================

@dataclass
class ClaimRecord:
    text: str
    normalized: str
    topic: str
    phase: str  # "cross_source", "cross_topic"
    # Source provenance — for paper-quality traceability
    url_reg: str = ""
    url_sim: str = ""
    page_id_reg: int = 0
    page_id_sim: int = 0
    # Regular Wikipedia chain (base, may be weak)
    reg_chain: Chain | None = None
    reg_grade: ChainGrade | None = None
    reg_narrator_ids: list[str] = field(default_factory=list)
    # Simple Wikipedia chain (corroborating, independent)
    sim_chain: Chain | None = None
    sim_grade: ChainGrade | None = None
    sim_narrator_ids: list[str] = field(default_factory=list)
    # Corroboration result
    corroborated: bool = False
    upgraded_grade: ChainGrade | None = None
    effective_weight: float = 0.0
    reason: str = ""
    similarity: float = 0.0


@dataclass
class ExperimentReport:
    total: int = 0
    fired: int = 0
    upgraded: int = 0
    phase_counts: dict[str, int] = field(default_factory=dict)
    phase_fired: dict[str, int] = field(default_factory=dict)
    records: list[ClaimRecord] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["=" * 70, "CORROBORATION EXPERIMENT v2 — SEMANTIC MATCHING",
                  "=" * 70, ""]
        lines.append(f"Total claims tested:   {self.total}")
        for phase, count in sorted(self.phase_counts.items()):
            f = self.phase_fired.get(phase, 0)
            pct = f / max(1, count) * 100
            lines.append(f"  {phase:30s} {count:4d} claims, {f:4d} corroborated ({pct:.1f}%)")
        lines.append("")
        lines.append(f"Corroboration fired:   {self.fired} ({self.fired / max(1, self.total) * 100:.1f}%)")
        lines.append(f"Grade upgraded:        {self.upgraded} ({self.upgraded / max(1, self.total) * 100:.1f}%)")
        lines.append("")
        lines.append("─" * 40)
        lines.append("Sample upgrades (first 10):")
        for rec in self.records:
            if rec.corroborated and len(lines) < 20:
                lines.append(
                    f"  [{rec.phase}] {rec.topic[:25]:25s} "
                    f"{rec.reg_grade.value:6s} → {rec.upgraded_grade.value if rec.upgraded_grade else 'N/A':6s} "
                    f"sim={rec.similarity:.3f} weight={rec.effective_weight:.1f}"
                )
        return "\n".join(lines)


# ===========================================================================
# Experiment
# ===========================================================================

def setup_registry() -> Registry:
    reg = Registry()
    for nid, grade in NARRATOR_GRADES.items():
        meta = NARRATOR_METADATA.get(nid, {})
        reg.register(narrator_id=nid, domain_tag="general", grade=grade,
                     model_family=meta.get("model_family"),
                     upstream_source=meta.get("upstream_source"))
    return reg


def run_phase_ab(
    match_pairs: list[MatchPair],
    registry: Registry,
    phase: str,
    all_data: dict[str, dict[str, Any]] | None = None,
) -> list[ClaimRecord]:
    """Run corroboration on semantically matched claim pairs.

    Args:
        match_pairs: Semantically matched claim pairs.
        registry: Narrator registry.
        phase: Phase label ("cross_source" or "cross_topic").
        all_data: Optional topic data dict for source URL lookup.
    """
    records = []
    rng = random.Random(42)
    pairs = list(match_pairs)
    rng.shuffle(pairs)
    max_pairs = 500
    pairs = pairs[:max_pairs]

    # Build URL lookup from all_data
    url_lookup: dict[str, dict[str, str]] = {}
    if all_data:
        for topic, sources in all_data.items():
            for src in ("regular", "simple"):
                td = sources.get(src)
                if td and td.url:
                    url_lookup.setdefault(topic, {})[src] = td.url

    for mp in pairs:
        norm = normalize_claim(mp.text_reg)

        reg_chain = build_reg_weak_chain()
        reg_grade = _grade_chain(reg_chain, registry)

        sim_chain = build_sim_chain()
        sim_grade = _grade_chain(sim_chain, registry)

        # Look up source URLs
        reg_url = url_lookup.get(mp.topic_reg, {}).get("regular", "")
        sim_url = url_lookup.get(mp.topic_sim, {}).get("simple", "")

        rec = ClaimRecord(
            text=mp.text_reg,
            normalized=norm,
            topic=f"{mp.topic_reg}↔{mp.topic_sim}",
            phase=phase,
            url_reg=reg_url,
            url_sim=sim_url,
            reg_chain=reg_chain, reg_grade=reg_grade,
            reg_narrator_ids=reg_chain.narrator_ids,
            sim_chain=sim_chain, sim_grade=sim_grade,
            sim_narrator_ids=sim_chain.narrator_ids,
            similarity=mp.similarity,
        )
        records.append(rec)

    return records


def apply_corroboration(
    records: list[ClaimRecord],
    engine: CorroborationEngine,
    narrator_metadata: dict[str, dict[str, Any]],
) -> list[ClaimRecord]:
    """Apply CorroborationEngine to each claim record."""
    # Build all_chains with canonicalized claim_text
    all_chains: list[dict[str, Any]] = []
    for rec in records:
        all_chains.append({
            "claim_text": rec.normalized,
            "chain_grade": rec.reg_grade.value,
            "narrator_ids": rec.reg_narrator_ids,
            "source": "regular_wikipedia",
        })
        all_chains.append({
            "claim_text": rec.normalized,
            "chain_grade": rec.sim_grade.value,
            "narrator_ids": rec.sim_narrator_ids,
            "source": "simple_wikipedia",
        })

    for rec in records:
        result = engine.evaluate(
            claim_text=rec.normalized,
            base_chain_grade=rec.reg_grade,
            base_narrators=rec.reg_narrator_ids,
            all_chains=all_chains,
            narrator_metadata=narrator_metadata,
        )
        rec.corroborated = result.upgraded
        rec.upgraded_grade = result.upgraded_grade
        rec.effective_weight = result.effective_weight
        rec.reason = result.reason

    return records


def build_report(records: list[ClaimRecord]) -> ExperimentReport:
    report = ExperimentReport()
    report.total = len(records)
    report.records = records
    for rec in records:
        report.phase_counts[rec.phase] = report.phase_counts.get(rec.phase, 0) + 1
        if rec.corroborated:
            report.fired += 1
            report.phase_fired[rec.phase] = report.phase_fired.get(rec.phase, 0) + 1
            if rec.upgraded_grade and rec.upgraded_grade != rec.reg_grade:
                report.upgraded += 1
    return report


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    print("=" * 70)
    print("CORROBORATION EXPERIMENT v2 — SEMANTIC MATCHING")
    print("=" * 70)

    # ── Step 1: Load data ───────────────────────────────────────────
    print("\n── Step 1: Load dual Wikipedia data ──\n")
    loader = DualWikipediaLoader()
    all_data = loader.load_all(TOPICS)

    total_reg = sum(len(td["regular"].sentences) for td in all_data.values())
    total_sim = sum(len(td["simple"].sentences) for td in all_data.values())
    print(f"\n  {len(all_data)} topics loaded")
    print(f"  Regular Wikipedia: {total_reg:,} factual sentences")
    print(f"  Simple Wikipedia:  {total_sim:,} factual sentences")

    # ── Step 2: Semantic matching ───────────────────────────────────
    print("\n── Step 2: Semantic matching ──\n")

    matcher = SemanticMatcher()

    # Collect all claims with topic labels
    claims_reg = [
        {"topic": topic, "text": s}
        for topic, td in all_data.items()
        for s in td["regular"].sentences
    ]
    claims_sim = [
        {"topic": topic, "text": s}
        for topic, td in all_data.items()
        for s in td["simple"].sentences
    ]

    # Phase A: Cross-source matching (regular ↔ simple)
    print("\n  Phase A: Cross-source matching (regular ↔ simple) ...")
    cross_source_path = MATCHES_DIR / "cross_source_matches.json"
    if cross_source_path.exists():
        cross_pairs = load_matches(cross_source_path)
        print(f"  Loaded {len(cross_pairs)} cached cross-source matches")
    else:
        cross_pairs = matcher.find_cross_source_matches(
            claims_reg, claims_sim, threshold=0.75, top_k_per_query=3,
        )
        save_matches(cross_pairs, cross_source_path)

    # Phase B: Cross-topic matching (regular ↔ regular, different topics)
    print("\n  Phase B: Cross-topic matching (regular ↔ regular) ...")
    cross_topic_path = MATCHES_DIR / "cross_topic_matches.json"
    if cross_topic_path.exists():
        intra_pairs = load_matches(cross_topic_path)
        print(f"  Loaded {len(intra_pairs)} cached cross-topic matches")
    else:
        intra_pairs = matcher.find_intra_reg_matches(claims_reg, threshold=0.80)
        save_matches(intra_pairs, cross_topic_path)

    # ── Step 3: Setup registry ─────────────────────────────────────
    print("\n── Step 3: Setup narrator registry ──\n")
    registry = setup_registry()
    for nid, g in NARRATOR_GRADES.items():
        print(f"  {nid:30s} → {g.value}")

    # ── Step 4: Run experiment ─────────────────────────────────────
    print("\n── Step 4: Run corroboration ──\n")

    engine = CorroborationEngine(min_independent_chains=1)

    records_a = run_phase_ab(cross_pairs, registry, "cross_source", all_data)
    print(f"  Phase A (cross-source): {len(records_a)} claim pairs")

    records_b = run_phase_ab(intra_pairs, registry, "cross_topic", all_data)
    print(f"  Phase B (cross-topic):  {len(records_b)} claim pairs")

    all_records = records_a + records_b
    all_records = apply_corroboration(all_records, engine, NARRATOR_METADATA)

    # ── Step 5: Report ─────────────────────────────────────────────
    print("\n── Step 5: Results ──\n")
    report = build_report(all_records)
    print(report.summary())

    # Save
    results_json = []
    for rec in all_records:
        results_json.append({
            "text_reg": rec.text[:300],
            "text_sim": getattr(rec, 'text_sim', ''),  # if we add it later
            "topic": rec.topic,
            "phase": rec.phase,
            "url_reg": rec.url_reg,
            "url_sim": rec.url_sim,
            "reg_grade": rec.reg_grade.value if rec.reg_grade else "unknown",
            "sim_grade": rec.sim_grade.value if rec.sim_grade else "unknown",
            "corroborated": rec.corroborated,
            "upgraded_grade": rec.upgraded_grade.value if rec.upgraded_grade else None,
            "effective_weight": round(rec.effective_weight, 2),
            "reason": rec.reason,
            "similarity": round(rec.similarity, 4),
        })

    with open(OUTPUT_DIR / "results_v2.json", "w") as f:
        json.dump(results_json, f, indent=2)
    with open(OUTPUT_DIR / "report_v2.txt", "w") as f:
        f.write(report.summary())
    print(f"\n  Results: {OUTPUT_DIR / 'results_v2.json'}")
    print(f"  Report:  {OUTPUT_DIR / 'report_v2.txt'}")

    # Key metrics
    print(f"\n{'=' * 70}")
    print("KEY METRICS:")
    print(f"  Total claims:        {report.total}")
    print(f"  Corroboration fired: {report.fired}/{report.total} "
          f"({report.fired/max(1,report.total)*100:.1f}%)")
    print(f"  Grade upgraded:      {report.upgraded}/{report.total} "
          f"({report.upgraded/max(1,report.total)*100:.1f}%)")
    for phase in sorted(report.phase_counts):
        c = report.phase_counts[phase]
        f = report.phase_fired.get(phase, 0)
        print(f"  {phase:30s} {f}/{c} ({f/max(1,c)*100:.1f}%)")

    if report.fired > 0:
        print(f"\n✓ Semantic corroboration FIRED on {report.fired} claims!")
    else:
        print("\n⚠️  No corroboration — investigate similarity thresholds or grades")
    print("=" * 70)


if __name__ == "__main__":
    main()
