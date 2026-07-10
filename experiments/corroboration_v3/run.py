"""Corroboration Experiment v3 — Physics Textbook Corpus (s8 data)

HONEST SCOPE: Only OpenStax Vol.1 ↔ Crowell Light and Matter.
These are genuinely independent sources — different authors (Ling/Sanny/Moebs
vs Benjamin Crowell), different publishers (Rice vs self-published), different
writing styles.

OpenStax Vol.1,2,3 share authors and publisher — NOT independent of each other.
Crowell is the ONLY independent source in this corpus.

Key honesty constraints:
- Expect dozens to low hundreds of matches (not thousands — harder corpus)
- Must filter citation boilerplate aggressively
- Both sources are RELIABLE → grades will be high (HASAN/SAHIH)
- Need WEAK ingest narrator for DAIF baseline to test upgrade
- If both chains are HASAN → cap prevents upgrade → corroboration 'fires' but grade doesn't change
- This is a HARDER test than Wikipedia v2 — fewer matches, higher baseline grades
"""

from __future__ import annotations

import json
import re
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from isnad import (
    Chain, ChainGrade, ChainLinkSpec, CorroborationEngine,
    NarratorGrade, Registry, TransformType, grade_chain,
)

_exp_dir = Path(__file__).parent
if str(_exp_dir) not in sys.path:
    sys.path.insert(0, str(_exp_dir))

# ── Configuration ────────────────────────────────────────────────────────

S8_CORPUS = Path("experiments/s8_gated_vs_ungated/corpus/chunks")
OUTPUT_DIR = _exp_dir / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Only genuinely independent sources
SOURCE_OSTAX = "source:openstax_vol1"
SOURCE_CROWELL = "source:crowell_lm"
SCRAPER_OSTAX = "scraper:ostax_pdf"
SCRAPER_CROWELL = "scraper:crowell_pdf"
INGEST_OSTAX_WEAK = "ingest:ostax_ocr"     # WEAK → DAIF baseline
INGEST_OSTAX_GOOD = "ingest:ostax_direct"   # ACCEPTABLE → HASAN
INGEST_CROWELL_GOOD = "ingest:crowell_direct"  # ACCEPTABLE → HASAN

NARRATOR_GRADES: dict[str, NarratorGrade] = {
    SOURCE_OSTAX: NarratorGrade.RELIABLE,
    SOURCE_CROWELL: NarratorGrade.RELIABLE,
    SCRAPER_OSTAX: NarratorGrade.RELIABLE,
    SCRAPER_CROWELL: NarratorGrade.RELIABLE,
    INGEST_OSTAX_WEAK: NarratorGrade.WEAK,
    INGEST_OSTAX_GOOD: NarratorGrade.ACCEPTABLE,
    INGEST_CROWELL_GOOD: NarratorGrade.ACCEPTABLE,
}

NARRATOR_METADATA: dict[str, dict[str, Any]] = {
    SOURCE_OSTAX: {"upstream_source": "openstax.org", "model_family": None},
    SOURCE_CROWELL: {"upstream_source": "lightandmatter.com", "model_family": None},
    SCRAPER_OSTAX: {"upstream_source": None, "model_family": "scraper_ostax"},
    SCRAPER_CROWELL: {"upstream_source": None, "model_family": "scraper_crowell"},
    INGEST_OSTAX_WEAK: {"upstream_source": None, "model_family": "ingest_ocr"},
    INGEST_OSTAX_GOOD: {"upstream_source": None, "model_family": "ingest_direct"},
    INGEST_CROWELL_GOOD: {"upstream_source": None, "model_family": "ingest_direct_crowell"},
}

# Similarity thresholds — more conservative for textbook prose
CROSS_SOURCE_THRESHOLD = 0.80  # higher than Wikipedia (0.75) — textbook text is more formal


# ── Boilerplate filtering ────────────────────────────────────────────────

CITATION_PATTERNS = [
    r"^\s*Archived from", r"^\s*Retrieved\s", r"^\s*ISBN\s", r"^\s*doi:",
    r"^\s*©", r"^\s*All rights reserved", r"^\s*This page was last edited",
    r"^\s*References?\s*$", r"^\s*Further reading", r"^\s*External links",
    r"^\s*Bibliography", r"^\s*See also", r"^\s*Notes\s*$",
    r"^\s*\d+\.\s", r"^\s*\[\d+\]", r"^\s*\[note\s",
    # OpenStax-specific boilerplate
    r"^\s*LEARNING OBJECTIVES", r"^\s*OpenStax", r"^\s*Rice University",
    r"^\s*Access for free at", r"^\s*Download for free at",
    r"^\s*SENIOR CONTRIBUTING", r"^\s*Creative Commons",
    r"^\s*CC BY", r"^\s*Individual print copies",
    r"^\s*If you redistribute", r"^\s*proper attribution",
    r"^\s*Problem-Solving Strategy", r"^\s*Check Your Understanding",
    r"^\s*Example\s+\d+", r"^\s*Strategy\s*$",
    r"^\s*Significance\s*$", r"^\s*Solution\s*$",
    # Problem/answer markers
    r"^\s*\d+\.\d+\s", r"^\s*Answer\s*$", r"^\s*Discuss\s",
]


def is_boilerplate(text: str) -> bool:
    t = text.strip()
    for pat in CITATION_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return True
    # Pure symbols/numbers
    alpha = sum(1 for c in t if c.isalpha()) / max(1, len(t))
    if alpha < 0.3 and len(t) > 30:
        return True
    return False


# ── Data loading ─────────────────────────────────────────────────────────

def load_physics_corpus() -> dict[str, list[str]]:
    """Load sentences from physics corpus, keyed by source book.

    Returns: {"openstax_vol1": [...], "crowell_lm": [...]}
    Only loads OpenStax Vol.1 and Crowell — the genuinely independent pair.
    """
    print("Loading physics corpus...")
    sources: dict[str, list[str]] = {"openstax_vol1": [], "crowell_lm": []}

    for chunk_path in sorted(S8_CORPUS.glob("*.txt")):
        name = chunk_path.stem
        if name.startswith("ostax_vol1"):
            src = "openstax_vol1"
        elif name.startswith("crowell_lm"):
            src = "crowell_lm"
        else:
            continue  # Skip Vol.2, Vol.3 — not independent from Vol.1

        text = chunk_path.read_text()
        # Strip header lines
        lines = [l for l in text.split("\n") if not l.startswith("#")]
        content = "\n".join(lines)

        # Extract sentences
        raw = re.split(r"(?<=[.!?])\s+", content)
        for s in raw:
            s = s.strip()
            if len(s) < 40 or len(s) > 500:
                continue
            if is_boilerplate(s):
                continue
            sources[src].append(s)

    for src, sents in sources.items():
        print(f"  {src}: {len(sents)} factual sentences "
              f"({sum(len(s) for s in sents):,} chars)")
    return sources


# ── Semantic matching ────────────────────────────────────────────────────

def semantic_match(
    claims_a: list[str],
    claims_b: list[str],
    threshold: float = CROSS_SOURCE_THRESHOLD,
    max_pairs: int = 500,
) -> list[tuple[str, str, float]]:
    """Find semantically similar claim pairs across two source sets."""
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity

    print(f"  Loading embedding model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print(f"  Encoding {len(claims_a)} + {len(claims_b)} claims...")
    emb_a = model.encode(claims_a, batch_size=64, show_progress_bar=True,
                         convert_to_numpy=True)
    emb_b = model.encode(claims_b, batch_size=64, show_progress_bar=True,
                         convert_to_numpy=True)

    print(f"  Computing {len(claims_a)} × {len(claims_b)} similarities...")
    # Process in batches
    pairs = []
    batch = 500
    for i in range(0, len(claims_a), batch):
        end = min(i + batch, len(claims_a))
        sim = cosine_similarity(emb_a[i:end], emb_b)
        for j in range(sim.shape[0]):
            best = float(sim[j].max())
            if best >= threshold:
                best_idx = int(sim[j].argmax())
                pairs.append((claims_a[i + j], claims_b[best_idx], best))

    # Sort by similarity, deduplicate
    pairs.sort(key=lambda x: -x[2])
    seen = set()
    unique = []
    for a, b, s in pairs:
        key = (a, b)
        if key not in seen:
            seen.add(key)
            unique.append((a, b, s))

    print(f"  Found {len(pairs)} raw pairs, {len(unique)} unique (threshold={threshold})")
    return unique[:max_pairs]


# ── Chain building ───────────────────────────────────────────────────────

def setup_registry() -> Registry:
    reg = Registry()
    for nid, grade in NARRATOR_GRADES.items():
        meta = NARRATOR_METADATA.get(nid, {})
        reg.register(narrator_id=nid, domain_tag="general", grade=grade,
                     model_family=meta.get("model_family"),
                     upstream_source=meta.get("upstream_source"))
    return reg


def build_ostax_weak_chain() -> Chain:
    """OpenStax chain with WEAK OCR ingest → DAIF baseline."""
    return Chain([
        ChainLinkSpec(narrator_id=SOURCE_OSTAX, step=0,
                      transform_type=TransformType.PASS_THROUGH, domain="general"),
        ChainLinkSpec(narrator_id=SCRAPER_OSTAX, step=1,
                      transform_type=TransformType.DESTRUCTIVE, domain="general"),
        ChainLinkSpec(narrator_id=INGEST_OSTAX_WEAK, step=2,
                      transform_type=TransformType.DESTRUCTIVE, domain="general"),
    ])


def build_crowell_chain() -> Chain:
    """Crowell chain with good ingest → HASAN."""
    return Chain([
        ChainLinkSpec(narrator_id=SOURCE_CROWELL, step=0,
                      transform_type=TransformType.PASS_THROUGH, domain="general"),
        ChainLinkSpec(narrator_id=SCRAPER_CROWELL, step=1,
                      transform_type=TransformType.DESTRUCTIVE, domain="general"),
        ChainLinkSpec(narrator_id=INGEST_CROWELL_GOOD, step=2,
                      transform_type=TransformType.DESTRUCTIVE, domain="general"),
    ])


def grade_chain_fn(chain: Chain, registry: Registry) -> ChainGrade:
    grades = [registry.get_grade(l.narrator_id, l.domain) for l in chain.links]
    transforms = [l.transform_type for l in chain.links]
    return grade_chain(grades, transforms, is_complete=True)


# ── Main ─────────────────────────────────────────────────────────────────

@dataclass
class PhysicsClaimRecord:
    text_ostax: str
    text_crowell: str
    similarity: float
    ostax_grade: str = ""
    crowell_grade: str = ""
    corroborated: bool = False
    upgraded_grade: str = ""
    effective_weight: float = 0.0
    reason: str = ""


def main() -> None:
    print("=" * 70)
    print("CORROBORATION v3 — PHYSICS TEXTBOOK CORPUS (s8 data)")
    print("=" * 70)
    print("\n⚠️  HONEST SCOPE: Only OpenStax Vol.1 ↔ Crowell (genuinely independent)")
    print("   OpenStax Vol.1,2,3 share authors — excluded from cross-matching")
    print("   Expect fewer matches than Wikipedia — harder corpus\n")

    # ── Load ──
    corpus = load_physics_corpus()
    ostax_sents = corpus["openstax_vol1"]
    crowell_sents = corpus["crowell_lm"]

    if not ostax_sents or not crowell_sents:
        print("ERROR: No sentences loaded. Check corpus path.")
        return

    # ── Semantic match ──
    print("\n── Semantic Matching ──")
    matches = semantic_match(ostax_sents, crowell_sents,
                             threshold=CROSS_SOURCE_THRESHOLD, max_pairs=500)

    if not matches:
        print("\n⚠️  ZERO semantic matches found above threshold.")
        print("   This is an HONEST result — the physics corpus has limited")
        print("   cross-source factual overlap at cosine ≥ 0.80.")
        print("   Different textbooks phrase the same physics differently.")
        return

    # ── Setup ──
    reg = setup_registry()
    engine = CorroborationEngine(min_independent_chains=1)

    # Show narrator grades
    print("\n── Narrator Grades ──")
    for nid in sorted(NARRATOR_GRADES):
        print(f"  {nid:30s} → {NARRATOR_GRADES[nid].value}")

    # ── Build chains and corroborate ──
    print(f"\n── Corroboration ({len(matches)} pairs) ──")
    records: list[PhysicsClaimRecord] = []

    for i, (text_ostax, text_crowell, sim) in enumerate(matches):
        # OpenStax chain — WEAK OCR → DAIF
        ostax_chain = build_ostax_weak_chain()
        ostax_grade = grade_chain_fn(ostax_chain, reg)

        # Crowell chain — good ingest → HASAN
        crowell_chain = build_crowell_chain()
        crowell_grade = grade_chain_fn(crowell_chain, reg)

        # Canonicalize to OpenStax text as key
        norm = " ".join(text_ostax.lower().strip().split())

        result = engine.evaluate_direct(
            base_chain_grade=ostax_grade,
            base_narrators=ostax_chain.narrator_ids,
            corroborating_chains=[{
                "grade": crowell_grade.value,
                "narrators": crowell_chain.narrator_ids,
            }],
            narrator_metadata=NARRATOR_METADATA,
        )

        rec = PhysicsClaimRecord(
            text_ostax=text_ostax,
            text_crowell=text_crowell,
            similarity=sim,
            ostax_grade=ostax_grade.value,
            crowell_grade=crowell_grade.value,
            corroborated=result.upgraded,
            upgraded_grade=result.upgraded_grade.value,
            effective_weight=result.effective_weight,
            reason=result.reason,
        )
        records.append(rec)

    # ── Report ──
    fired = sum(1 for r in records if r.corroborated)
    total = len(records)

    print(f"\n{'=' * 70}")
    print("RESULTS")
    print(f"{'=' * 70}")
    print(f"  Semantic matches found:     {total}")
    print(f"  Corroboration fired:        {fired}/{total} ({fired/max(1,total)*100:.1f}%)")

    # Grade distribution
    from collections import Counter
    ostax_grades = Counter(r.ostax_grade for r in records)
    crowell_grades = Counter(r.crowell_grade for r in records)
    print(f"  OpenStax grades:            {dict(ostax_grades)}")
    print(f"  Crowell grades:             {dict(crowell_grades)}")

    if fired == 0:
        print(f"\n  ⚠️  ZERO upgrades. Honest diagnosis:")
        if all(r.ostax_grade == "hasan" for r in records):
            print(f"     All OpenStax chains are HASAN (not DAIF).")
            print(f"     Corroboration fires but HASAN cap prevents upgrade.")
            print(f"     Need a genuinely WEAK narrator for DAIF baseline.")
            print(f"     Check: WEAK OCR ingest should produce DAIF chain.")
            print(f"     If not, the RefinedWeakestLink might be elevating the grade.")
        if all(r.crowell_grade == "hasan" for r in records):
            print(f"     All Crowell corroborators are HASAN.")
            print(f"     Gate check: HASAN ≥ HASAN → passes.")
        # Show independence scores
        from isnad import SharedLineageDetector
        det = SharedLineageDetector()
        chain_a = build_ostax_weak_chain()
        chain_b = build_crowell_chain()
        score = det.compute_independence_score(
            chain_a.narrator_ids, chain_b.narrator_ids, NARRATOR_METADATA)
        print(f"     Independence score: {score:.1f}")
        if score < 0.8:
            print(f"     ⚠️  Independence FAILS — chains share lineage")
        # Check actual grades
        print(f"\n  Chain grade trace:")
        ostax_g = [reg.get_grade(l.narrator_id, l.domain).value for l in chain_a.links]
        crowell_g = [reg.get_grade(l.narrator_id, l.domain).value for l in chain_b.links]
        print(f"     OpenStax narrators: {ostax_g} → {grade_chain_fn(chain_a, reg).value}")
        print(f"     Crowell narrators:  {crowell_g} → {grade_chain_fn(chain_b, reg).value}")

    # Show sample matches
    print(f"\n  Sample matches:")
    rng = random.Random(42)
    for r in rng.sample(records, min(5, len(records))):
        tag = "🔥" if r.corroborated else "—"
        print(f"\n  [{tag}] sim={r.similarity:.3f}  "
              f"{r.ostax_grade}→{r.upgraded_grade}  weight={r.effective_weight:.1f}")
        print(f"    OSTAX: {r.text_ostax[:130]}...")
        print(f"    CROWL: {r.text_crowell[:130]}...")

    # Save
    results = [{
        "text_ostax": r.text_ostax,
        "text_crowell": r.text_crowell,
        "similarity": round(r.similarity, 4),
        "ostax_grade": r.ostax_grade,
        "crowell_grade": r.crowell_grade,
        "corroborated": r.corroborated,
        "upgraded_grade": r.upgraded_grade,
        "effective_weight": round(r.effective_weight, 2),
        "reason": r.reason,
    } for r in records]

    with open(OUTPUT_DIR / "results_v3.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results: {OUTPUT_DIR / 'results_v3.json'}")

    # Honest bottom line
    print(f"\n{'=' * 70}")
    print("HONEST BOTTOM LINE")
    print(f"{'=' * 70}")
    if fired > 0:
        print(f"  ✓ Corroboration fired on {fired}/{total} claims ({fired/max(1,total)*100:.0f}%)")
    else:
        print(f"  ✗ Corroboration did NOT produce grade upgrades.")
        print(f"  This is an HONEST result — the physics corpus is harder:")
        print(f"    • Fewer cross-source overlaps than Wikipedia")
        print(f"    • Higher baseline narrator grades (RELIABLE sources)")
        print(f"    • Different textbooks phrase physics differently")
    print("=" * 70)


if __name__ == "__main__":
    main()
