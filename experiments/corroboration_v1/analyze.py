"""Analyze corroboration experiment results.

Generates:
  - Summary statistics
  - Grade distribution before/after corroboration
  - Per-narrator grade impact analysis
  - Recommendations for paper §8
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "results"


def load_results() -> list[dict]:
    """Load experiment results."""
    path = OUTPUT_DIR / "results.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run run.py first.")
        return []
    with open(path) as f:
        return json.load(f)


def analyze_grade_distribution(results: list[dict]) -> dict:
    """Analyze chain grade distributions."""
    base_grades = Counter(r["wiki_grade"] for r in results)
    brit_grades = Counter(r["brit_grade"] for r in results if r["brit_grade"])
    upgraded = Counter(
        r["upgraded_grade"] for r in results
        if r["corroborated"] and r["upgraded_grade"]
    )
    return {
        "wiki_base_grades": dict(base_grades),
        "brit_grades": dict(brit_grades),
        "upgraded_grades": dict(upgraded),
    }


def analyze_by_phase(results: list[dict]) -> dict:
    """Breakdown by experiment phase."""
    synth_weak = [r for r in results if r["phase"] == "synthetic_weak"]
    synth_hasan = [r for r in results if r["phase"] == "synthetic_hasan"]
    cross_weak = [r for r in results if r["phase"] == "cross_topic_weak"]
    cross_hasan = [r for r in results if r["phase"] == "cross_topic_hasan"]

    return {
        "phase_a_weak": {
            "total": len(synth_weak),
            "corroborated": sum(1 for r in synth_weak if r["corroborated"]),
            "rate": sum(1 for r in synth_weak if r["corroborated"]) / max(1, len(synth_weak)),
        },
        "phase_a_hasan": {
            "total": len(synth_hasan),
            "corroborated": sum(1 for r in synth_hasan if r["corroborated"]),
            "rate": sum(1 for r in synth_hasan if r["corroborated"]) / max(1, len(synth_hasan)),
        },
        "phase_b_weak": {
            "total": len(cross_weak),
            "corroborated": sum(1 for r in cross_weak if r["corroborated"]),
            "rate": sum(1 for r in cross_weak if r["corroborated"]) / max(1, len(cross_weak)),
        },
        "phase_b_hasan": {
            "total": len(cross_hasan),
            "corroborated": sum(1 for r in cross_hasan if r["corroborated"]),
            "rate": sum(1 for r in cross_hasan if r["corroborated"]) / max(1, len(cross_hasan)),
        },
    }


def analyze_failure_reasons(results: list[dict]) -> tuple[list[dict], list[dict]]:
    """Collect reasons why corroboration did NOT fire.
    
    Returns (true_failures, capped) where:
      - true_failures: DAIF chains that should have upgraded but didn't
      - capped: HASAN chains where the cap prevented SAHIH upgrade (expected)
    """
    true_failures = []
    capped = []
    for r in results:
        if not r["corroborated"] and r.get("reason"):
            entry = {
                "topic": r["topic"],
                "phase": r["phase"],
                "wiki_grade": r["wiki_grade"],
                "brit_grade": r.get("brit_grade"),
                "reason": r["reason"],
                "overlap_score": r.get("overlap_score", 0),
            }
            if r["wiki_grade"] == "hasan":
                capped.append(entry)  # expected: cap prevents HASAN→SAHIH
            else:
                true_failures.append(entry)
    return true_failures, capped


def main() -> None:
    results = load_results()
    if not results:
        return

    print("=" * 60)
    print("CORROBORATION EXPERIMENT — ANALYSIS")
    print("=" * 60)

    # ── Overall stats ──
    total = len(results)
    corroborated = sum(1 for r in results if r["corroborated"])
    upgraded = sum(
        1 for r in results
        if r["corroborated"]
        and r["upgraded_grade"] is not None
        and r["upgraded_grade"] != r["wiki_grade"]
    )

    print(f"\nTotal claims:       {total}")
    print(f"Corroborated:       {corroborated} ({corroborated/max(1,total)*100:.1f}%)")
    print(f"Grade upgraded:     {upgraded} ({upgraded/max(1,total)*100:.1f}%)")

    # ── By phase ──
    by_phase = analyze_by_phase(results)
    print(f"\nPhase A - Weak (DAIF→HASAN): {by_phase['phase_a_weak']['total']} claims, "
          f"{by_phase['phase_a_weak']['corroborated']} corroborated "
          f"({by_phase['phase_a_weak']['rate']*100:.1f}%)")
    print(f"Phase A - HASAN (cap test):  {by_phase['phase_a_hasan']['total']} claims, "
          f"{by_phase['phase_a_hasan']['corroborated']} corroborated "
          f"({by_phase['phase_a_hasan']['rate']*100:.1f}%)")
    print(f"Phase B - Weak (DAIF→HASAN): {by_phase['phase_b_weak']['total']} claims, "
          f"{by_phase['phase_b_weak']['corroborated']} corroborated "
          f"({by_phase['phase_b_weak']['rate']*100:.1f}%)")
    print(f"Phase B - HASAN (cap test):  {by_phase['phase_b_hasan']['total']} claims, "
          f"{by_phase['phase_b_hasan']['corroborated']} corroborated "
          f"({by_phase['phase_b_hasan']['rate']*100:.1f}%)")

    # ── Grade distribution ──
    dist = analyze_grade_distribution(results)
    print(f"\nWiki base grades:   {dist['wiki_base_grades']}")
    print(f"Brit base grades:   {dist['brit_grades']}")
    print(f"Upgraded grades:    {dist['upgraded_grades']}")

    # ── Failure analysis ──
    true_failures, capped = analyze_failure_reasons(results)
    print(f"\nCapped (HASAN→HASAN, expected): {len(capped)}")
    print(f"True failures (DAIF not upgraded): {len(true_failures)}")
    if true_failures:
        print("  Sample true failures:")
        for f in true_failures[:3]:
            print(f"  • [{f['wiki_grade']}] {f['reason']}")

    # ── Success/blocker diagnosis ──
    print(f"\n{'=' * 60}")
    print("DIAGNOSIS")
    if corroborated == 0:
        print("\n⚠️  Corroboration NEVER fired.")
        print("\nLikely reasons (check these):")
        print("  1. Independence check: Are the two chains' narrators detected as")
        print("     independent? Check that source:narrator metadata has different")
        print("     upstream_source values and no shared model_family.")
        print("  2. Grade gate: Both chains must have grade >= HASAN.")
        print("     Current grades:", dict(Counter(r["wiki_grade"] for r in results)))
        print("  3. Minimum chains: CorroborationEngine requires ≥2 independent chains.")
        print("  4. Claim text matching: Corroboration matches on exact normalized text.")
        print("     In Phase B, different text means no match. Use verify text equality.")
    elif corroborated / max(1, total) < 0.5:
        print(f"\n⚠️  Corroboration fired on only {corroborated/max(1,total)*100:.1f}% of claims.")
        print("   Investigate failure reasons above.")
    else:
        print(f"\n✓ Corroboration fires at {corroborated/max(1,total)*100:.1f}% — promising!")

    # ── Recommendations ──
    print(f"\n{'=' * 60}")
    print("RECOMMENDATIONS FOR PAPER §8")
    if corroborated > 0:
        print("\n1. Include corroboration results in §8 comparison table")
        print("2. Report fire rate and grade upgrade rate")
        print("3. Note: corroboration only fires on exact text matches currently")
        print("4. Consider embedding-based claim matching for broader coverage")
        print("5. Try different narrator grade configurations to explore")
    else:
        print("\n1. Debug: check independence_score computation")
        print("2. Lower the grade floor (use UNGRADED → HASAN mapping)")
        print("3. Try with more generous narrator grades")
        print("4. Ensure metadata has distinct upstream_source for each chain")
        print("5. Manually verify one claim pair end-to-end")

    print("=" * 60)


if __name__ == "__main__":
    main()
