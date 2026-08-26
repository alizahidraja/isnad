"""Negative controls for corroboration experiment v3 (physics corpus).

v2 ran 8 negative controls; v3 ran **none** (the paper's §8.5 admits this is
the weakness of the v3 result). This module closes that gap, using the v3
narrator configuration (OpenStax Vol.1 ↔ Crowell) and adding a 9th control —
the shared retrieved-document hash — which is the new madār signal from #125.

Control categories:
  C1: No matching claim text → zero corroborators
  C2: Correlated chains (shared model family) → independence fails
  C3: All corroborators below grade gate (all DAIF)
  C4: MAWDU base chain → never upgraded
  C5: HASAN base chain → capped (cannot reach SAHIH)
  C6: Same upstream source → madār detected
  C7: min_independent_chains=2, only 1 corroborator
  C8: Empty all_chains
  C9: Shared retrieved-document hash → hard correlation (#125)

Fully deterministic — no embedding model, no API keys, no corpus load.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from isnad import (
    Chain,
    ChainGrade,
    ChainLinkSpec,
    CorroborationEngine,
    SharedLineageDetector,
    TransformType,
)

OUTPUT_DIR = Path(__file__).parent / "results"

# v3 narrator configuration (mirrors run.py, but the controls only need the
# narrator IDs + metadata — the chains are built inline per control).
NARRATOR_METADATA: dict[str, dict[str, Any]] = {
    "source:openstax_vol1": {"upstream_source": "openstax.org", "model_family": None},
    "source:crowell_lm": {"upstream_source": "lightandmatter.com", "model_family": None},
    "scraper:ostax_pdf": {"upstream_source": None, "model_family": "scraper_ostax"},
    "scraper:crowell_pdf": {"upstream_source": None, "model_family": "scraper_crowell"},
    "ingest:ostax_ocr": {"upstream_source": None, "model_family": "ingest_ocr"},
    "ingest:crowell_direct": {"upstream_source": None, "model_family": "ingest_direct_crowell"},
}


def _ostax_weak_chain() -> Chain:
    """OpenStax chain with a WEAK OCR ingest → DAIF baseline."""
    return Chain([
        ChainLinkSpec(
            "source:openstax_vol1", 0, transform_type=TransformType.PASS_THROUGH, domain="general"
        ),
        ChainLinkSpec(
            "scraper:ostax_pdf", 1, transform_type=TransformType.DESTRUCTIVE, domain="general"
        ),
        ChainLinkSpec(
            "ingest:ostax_ocr", 2, transform_type=TransformType.DESTRUCTIVE, domain="general"
        ),
    ])


def _crowell_chain() -> Chain:
    """Crowell chain with good ingest → HASAN."""
    return Chain([
        ChainLinkSpec(
            "source:crowell_lm", 0, transform_type=TransformType.PASS_THROUGH, domain="general"
        ),
        ChainLinkSpec(
            "scraper:crowell_pdf", 1, transform_type=TransformType.DESTRUCTIVE, domain="general"
        ),
        ChainLinkSpec(
            "ingest:crowell_direct", 2, transform_type=TransformType.DESTRUCTIVE, domain="general"
        ),
    ])


@dataclass
class ControlResult:
    name: str
    category: str
    passed: bool
    expected: str
    actual: str
    details: str = ""


def run_controls() -> list[ControlResult]:
    results: list[ControlResult] = []
    engine = CorroborationEngine(min_independent_chains=1)

    # ── C1: No matching claim text ────────────────────────────────
    r = engine.evaluate(
        "a unique physics claim no other chain has",
        ChainGrade.DAIF,
        ["n1"],
        [{"claim_text": "some other text", "chain_grade": "hasan", "narrator_ids": ["n2"]}],
        {},
    )
    results.append(
        ControlResult(
            name="C1: No matching text",
            category="matching",
            passed=not r.upgraded and r.corroborating_chains == 0,
            expected="no upgrade, 0 corroborators",
            actual=f"upgraded={r.upgraded}, corr={r.corroborating_chains}",
            details=f"reason: {r.reason}",
        )
    )

    # ── C2: Shared model family (madār) ───────────────────────────
    # Two different chains whose models share a family — the v3 scraper
    # families are disjoint by design, so construct an explicit shared case.
    corr_meta = {
        "n1": {"model_family": "gpt-4"},
        "n2": {"model_family": "gpt-4"},
    }
    r = engine.evaluate(
        "energy is conserved",
        ChainGrade.DAIF,
        ["n1"],
        [{"claim_text": "energy is conserved", "chain_grade": "hasan", "narrator_ids": ["n2"]}],
        corr_meta,
    )
    score = SharedLineageDetector().compute_independence_score(["n1"], ["n2"], corr_meta)
    results.append(
        ControlResult(
            name="C2: Shared model family (madār)",
            category="independence",
            passed=not r.upgraded and score < 0.8,
            expected="no upgrade, independence < 0.8",
            actual=f"upgraded={r.upgraded}, ind_score={score}",
            details=f"reason: {r.reason}",
        )
    )

    # ── C3: All corroborators below grade gate ────────────────────
    # Attested-distinct lineage so independence passes and the *grade gate*
    # is what blocks (issue #54: unattested chains fail independence first).
    r = engine.evaluate(
        "momentum is conserved",
        ChainGrade.DAIF,
        ["n1"],
        [
            {"claim_text": "momentum is conserved", "chain_grade": "daif", "narrator_ids": ["n2"]},
            {"claim_text": "momentum is conserved", "chain_grade": "daif", "narrator_ids": ["n3"]},
        ],
        {
            "n1": {"model_family": "f1", "upstream_source": "s1"},
            "n2": {"model_family": "f2", "upstream_source": "s2"},
            "n3": {"model_family": "f3", "upstream_source": "s3"},
        },
    )
    results.append(
        ControlResult(
            name="C3: All DAIF corroborators (grade gate)",
            category="grade_gate",
            passed=not r.upgraded and "min grade" in r.reason.lower(),
            expected="no upgrade, all below HASAN gate",
            actual=f"upgraded={r.upgraded}, weight={r.effective_weight}",
            details=f"reason: {r.reason}",
        )
    )

    # ── C4: MAWDU base chain ─────────────────────────────────────
    r = engine.evaluate(
        "perpetual motion is real",
        ChainGrade.MAWDU,
        ["n1"],
        [
            {
                "claim_text": "perpetual motion is real",
                "chain_grade": "sahih",
                "narrator_ids": ["n2"],
            }
        ],
        {},
    )
    results.append(
        ControlResult(
            name="C4: MAWDU base chain",
            category="mawdu",
            passed=not r.upgraded and "MAWDU" in r.reason,
            expected="no upgrade, MAWDU is unrecoverable",
            actual=f"upgraded={r.upgraded}",
            details=f"reason: {r.reason}",
        )
    )

    # ── C5: HASAN base cap ───────────────────────────────────────
    r = engine.evaluate(
        "force equals mass times acceleration",
        ChainGrade.HASAN,
        ["n1"],
        [
            {
                "claim_text": "force equals mass times acceleration",
                "chain_grade": "sahih",
                "narrator_ids": ["n2"],
            },
            {
                "claim_text": "force equals mass times acceleration",
                "chain_grade": "sahih",
                "narrator_ids": ["n3"],
            },
        ],
        {},
    )
    results.append(
        ControlResult(
            name="C5: HASAN cap (cannot reach SAHIH)",
            category="cap",
            passed=not r.upgraded and r.upgraded_grade == ChainGrade.HASAN,
            expected="no upgrade, HASAN stays HASAN",
            actual=f"upgraded={r.upgraded}, grade={r.upgraded_grade.value}",
            details=f"effective_weight={r.effective_weight:.1f}",
        )
    )

    # ── C6: Shared upstream source (the v3 fixture-3 pattern) ────
    # Both chains trace to openstax.org — the madār case the v3 corpus was
    # built to surface.
    src_meta = {
        "scraper_a": {"upstream_source": "openstax.org"},
        "scraper_b": {"upstream_source": "openstax.org"},
    }
    r = engine.evaluate(
        "work is force times distance",
        ChainGrade.DAIF,
        ["scraper_a"],
        [
            {
                "claim_text": "work is force times distance",
                "chain_grade": "hasan",
                "narrator_ids": ["scraper_b"],
            }
        ],
        src_meta,
    )
    score2 = SharedLineageDetector().compute_independence_score(
        ["scraper_a"], ["scraper_b"], src_meta
    )
    results.append(
        ControlResult(
            name="C6: Shared upstream source (openstax.org)",
            category="independence",
            passed=not r.upgraded and score2 < 0.8,
            expected="no upgrade, shared source → discount",
            actual=f"upgraded={r.upgraded}, ind_score={score2}",
            details=f"reason: {r.reason}",
        )
    )

    # ── C7: min_independent_chains=2, only 1 corroborator ────────
    engine2 = CorroborationEngine(min_independent_chains=2)
    r = engine2.evaluate(
        "power is work per unit time",
        ChainGrade.DAIF,
        ["n1"],
        [
            {
                "claim_text": "power is work per unit time",
                "chain_grade": "hasan",
                "narrator_ids": ["n2"],
            }
        ],
        {
            "n1": {"model_family": "f1", "upstream_source": "s1"},
            "n2": {"model_family": "f2", "upstream_source": "s2"},
        },
    )
    results.append(
        ControlResult(
            name="C7: min_independent_chains=2, only 1 corroborator",
            category="count_gate",
            passed=not r.upgraded and "have 1" in r.reason,
            expected="no upgrade, need ≥2 independent chains",
            actual=f"upgraded={r.upgraded}, independent={r.independent_chains}",
            details=f"reason: {r.reason}",
        )
    )

    # ── C8: Empty all_chains ──────────────────────────────────────
    r = engine.evaluate(
        "the atom has a nucleus",
        ChainGrade.DAIF,
        ["n1"],
        [],
        {},
    )
    results.append(
        ControlResult(
            name="C8: Empty all_chains",
            category="matching",
            passed=not r.upgraded and r.corroborating_chains == 0,
            expected="no upgrade, no chains at all",
            actual=f"upgraded={r.upgraded}, corr={r.corroborating_chains}",
            details=f"reason: {r.reason}",
        )
    )

    # ── C9: Shared retrieved-document hash (#125) ────────────────
    # Two chains with disjoint narrators AND distinct lineages, but both
    # retrieved the same document — the new hard-correlation signal that v2
    # (which predates #125) could not test.
    r = engine.evaluate_direct(
        base_chain_grade=ChainGrade.DAIF,
        base_narrators=["source:A", "model:A"],
        corroborating_chains=[
            {
                "grade": "hasan",
                "narrators": ["source:B", "model:B"],
                "document_hashes": ["shared-report-hash"],
            }
        ],
        narrator_metadata={
            "source:A": {"model_family": None, "upstream_source": "openstax.org"},
            "model:A": {"model_family": "fam-a", "upstream_source": "openstax.org"},
            "source:B": {"model_family": None, "upstream_source": "lightandmatter.com"},
            "model:B": {"model_family": "fam-b", "upstream_source": "lightandmatter.com"},
        },
        base_document_hashes={"shared-report-hash"},
    )
    results.append(
        ControlResult(
            name="C9: Shared retrieved-document hash (#125)",
            category="independence",
            passed=not r.upgraded and r.independent_chains == 0,
            expected="no upgrade, shared doc hash → hard correlation",
            actual=f"upgraded={r.upgraded}, independent={r.independent_chains}",
            details=f"reason: {r.reason}",
        )
    )

    return results


def run_and_report() -> dict[str, Any]:
    controls = run_controls()
    passed = sum(1 for c in controls if c.passed)
    total = len(controls)

    print("=" * 70)
    print("NEGATIVE CONTROLS — v3 PHYSICS CORPUS (should NOT corroborate)")
    print("=" * 70)
    for c in controls:
        status = "✅" if c.passed else "❌ FAIL"
        print(f"\n  {status} {c.name}")
        print(f"     Category: {c.category}")
        print(f"     Expected: {c.expected}")
        print(f"     Actual:   {c.actual}")
        if not c.passed:
            print(f"     DETAILS:  {c.details}")

    print(f"\n{'=' * 70}")
    print(f"CONTROLS: {passed}/{total} passed")
    if passed == total:
        print("✅ ALL NEGATIVE CONTROLS PASS — corroboration is properly gated")
    else:
        print(f"❌ {total - passed} CONTROLS FAILED — investigate immediately")
    print("=" * 70)

    report = {
        "total": total,
        "passed": passed,
        "all_passed": passed == total,
        "controls": [
            {
                "name": c.name,
                "category": c.category,
                "passed": c.passed,
                "expected": c.expected,
                "actual": c.actual,
                "details": c.details,
            }
            for c in controls
        ],
    }
    path = OUTPUT_DIR / "negative_controls.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved: {path}")

    return report


if __name__ == "__main__":
    run_and_report()
