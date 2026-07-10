"""Negative controls for corroboration experiment v2.

Systematically tests scenarios where corroboration SHOULD NOT fire.
If any control fails (corroboration fires when it shouldn't), there's
a bug in the framework or experiment design.

Control categories:
  C1: No matching claim text → zero corroborators
  C2: Below-threshold similarity → semantic mismatch
  C3: Correlated chains (shared model family) → independence fails
  C4: All corroborators below grade gate (all DAIF)
  C5: MAWDU base chain → never upgraded
  C6: HASAN base chain → capped (cannot reach SAHIH)
  C7: Same source/upstream → madār detected
  C8: Empty narrator metadata → ambiguous independence
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from isnad import (
    Chain, ChainGrade, ChainLinkSpec, CorroborationEngine,
    NarratorGrade, Registry, TransformType, grade_chain,
)

OUTPUT_DIR = Path(__file__).parent / "results"


@dataclass
class ControlResult:
    name: str
    category: str
    passed: bool
    expected: str  # what we expected
    actual: str    # what we got
    details: str = ""


def build_reg_chain() -> Chain:
    return Chain([
        ChainLinkSpec("source:wikipedia", 0, transform_type=TransformType.PASS_THROUGH, domain="general"),
        ChainLinkSpec("ingest:wiki_ocr", 1, transform_type=TransformType.DESTRUCTIVE, domain="general"),
        ChainLinkSpec("model:wiki_gpt4", 2, transform_type=TransformType.GENERATIVE, domain="general"),
    ])


def setup_engine() -> CorroborationEngine:
    return CorroborationEngine(min_independent_chains=1)


def run_controls() -> list[ControlResult]:
    results: list[ControlResult] = []
    engine = setup_engine()

    # ── C1: No matching claim text ────────────────────────────────
    r = engine.evaluate(
        "unique claim no other chain has",
        ChainGrade.DAIF,
        ["n1"],
        [{"claim_text": "some other text", "chain_grade": "hasan", "narrator_ids": ["n2"]}],
        {},
    )
    results.append(ControlResult(
        name="C1: No matching text",
        category="matching",
        passed=not r.upgraded and r.corroborating_chains == 0,
        expected="no upgrade, 0 corroborators",
        actual=f"upgraded={r.upgraded}, corr={r.corroborating_chains}",
        details=f"reason: {r.reason}",
    ))

    # ── C2: Correlated chains (shared model_family) ───────────────
    corr_meta = {
        "n1": {"model_family": "gpt-4"},
        "n2": {"model_family": "gpt-4"},
    }
    r = engine.evaluate(
        "gravity exists",
        ChainGrade.DAIF,
        ["n1"],
        [{"claim_text": "gravity exists", "chain_grade": "hasan", "narrator_ids": ["n2"]}],
        corr_meta,
    )
    from isnad import SharedLineageDetector
    score = SharedLineageDetector().compute_independence_score(["n1"], ["n2"], corr_meta)
    results.append(ControlResult(
        name="C2: Shared model family (madār)",
        category="independence",
        passed=not r.upgraded and score < 0.8,
        expected=f"no upgrade, independence < 0.8",
        actual=f"upgraded={r.upgraded}, ind_score={score}",
        details=f"reason: {r.reason}",
    ))

    # ── C3: All corroborators below grade gate ────────────────────
    r = engine.evaluate(
        "earth is round",
        ChainGrade.DAIF,
        ["n1"],
        [
            {"claim_text": "earth is round", "chain_grade": "daif", "narrator_ids": ["n2"]},
            {"claim_text": "earth is round", "chain_grade": "daif", "narrator_ids": ["n3"]},
        ],
        {},
    )
    results.append(ControlResult(
        name="C3: All DAIF corroborators (grade gate)",
        category="grade_gate",
        passed=not r.upgraded and "min grade" in r.reason.lower(),
        expected="no upgrade, all below HASAN gate",
        actual=f"upgraded={r.upgraded}, weight={r.effective_weight}",
        details=f"reason: {r.reason}",
    ))

    # ── C4: MAWDU base chain ─────────────────────────────────────
    r = engine.evaluate(
        "fake news",
        ChainGrade.MAWDU,
        ["n1"],
        [{"claim_text": "fake news", "chain_grade": "sahih", "narrator_ids": ["n2"]}],
        {},
    )
    results.append(ControlResult(
        name="C4: MAWDU base chain",
        category="mawdu",
        passed=not r.upgraded and "MAWDU" in r.reason,
        expected="no upgrade, MAWDU is unrecoverable",
        actual=f"upgraded={r.upgraded}",
        details=f"reason: {r.reason}",
    ))

    # ── C5: HASAN base cap ───────────────────────────────────────
    r = engine.evaluate(
        "speed of light is constant",
        ChainGrade.HASAN,
        ["n1"],
        [
            {"claim_text": "speed of light is constant", "chain_grade": "sahih", "narrator_ids": ["n2"]},
            {"claim_text": "speed of light is constant", "chain_grade": "sahih", "narrator_ids": ["n3"]},
        ],
        {},
    )
    results.append(ControlResult(
        name="C5: HASAN cap (cannot reach SAHIH)",
        category="cap",
        passed=not r.upgraded and r.upgraded_grade == ChainGrade.HASAN,
        expected="no upgrade, HASAN stays HASAN",
        actual=f"upgraded={r.upgraded}, grade={r.upgraded_grade.value}",
        details=f"effective_weight={r.effective_weight:.1f}",
    ))

    # ── C6: Shared upstream source ───────────────────────────────
    src_meta = {
        "scraper_a": {"upstream_source": "same-site.com"},
        "scraper_b": {"upstream_source": "same-site.com"},
    }
    r = engine.evaluate(
        "water boils at 100C",
        ChainGrade.DAIF,
        ["scraper_a"],
        [{"claim_text": "water boils at 100C", "chain_grade": "hasan", "narrator_ids": ["scraper_b"]}],
        src_meta,
    )
    score2 = SharedLineageDetector().compute_independence_score(["scraper_a"], ["scraper_b"], src_meta)
    results.append(ControlResult(
        name="C6: Shared upstream source",
        category="independence",
        passed=not r.upgraded and score2 < 0.8,
        expected=f"no upgrade, shared source → partial discount",
        actual=f"upgraded={r.upgraded}, ind_score={score2}",
        details=f"reason: {r.reason}",
    ))

    # ── C7: Single corroborator with effective weight < threshold (min_independent_chains=2) ──
    engine2 = CorroborationEngine(min_independent_chains=2)
    r = engine2.evaluate(
        "F=ma",
        ChainGrade.DAIF,
        ["n1"],
        [{"claim_text": "F=ma", "chain_grade": "hasan", "narrator_ids": ["n2"]}],
        {},
    )
    results.append(ControlResult(
        name="C7: min_independent_chains=2, only 1 corroborator",
        category="count_gate",
        passed=not r.upgraded and "have 1" in r.reason,
        expected="no upgrade, need ≥2 independent chains",
        actual=f"upgraded={r.upgraded}, independent={r.independent_chains}",
        details=f"reason: {r.reason}",
    ))

    # ── C8: Empty all_chains ──────────────────────────────────────
    r = engine.evaluate(
        "something",
        ChainGrade.DAIF,
        ["n1"],
        [],
        {},
    )
    results.append(ControlResult(
        name="C8: Empty all_chains",
        category="matching",
        passed=not r.upgraded and r.corroborating_chains == 0,
        expected="no upgrade, no chains at all",
        actual=f"upgraded={r.upgraded}, corr={r.corroborating_chains}",
        details=f"reason: {r.reason}",
    ))

    return results


def run_and_report() -> dict[str, Any]:
    controls = run_controls()
    passed = sum(1 for c in controls if c.passed)
    total = len(controls)

    print("=" * 70)
    print("NEGATIVE CONTROLS — Corroboration Should NOT Fire Here")
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

    # Save to JSON
    report = {
        "total": total, "passed": passed,
        "all_passed": passed == total,
        "controls": [
            {"name": c.name, "category": c.category, "passed": c.passed,
             "expected": c.expected, "actual": c.actual, "details": c.details}
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
