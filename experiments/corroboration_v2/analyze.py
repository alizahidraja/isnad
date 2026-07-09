"""Analyze v2 experiment results."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "results"

def load() -> list[dict]:
    path = OUTPUT_DIR / "results_v2.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run run.py first.")
        return []
    with open(path) as f:
        return json.load(f)

def main() -> None:
    results = load()
    if not results:
        return

    print("=" * 70)
    print("CORROBORATION v2 — ANALYSIS")
    print("=" * 70)

    total = len(results)
    fired = sum(1 for r in results if r["corroborated"])
    upgraded = sum(1 for r in results if r["corroborated"] and r["reg_grade"] != r.get("upgraded_grade"))

    print(f"\nTotal claims:       {total}")
    print(f"Corroborated:       {fired} ({fired/max(1,total)*100:.1f}%)")
    print(f"Grade upgraded:     {upgraded} ({upgraded/max(1,total)*100:.1f}%)")

    # By phase
    phases = Counter(r["phase"] for r in results)
    for p, count in phases.most_common():
        p_fired = sum(1 for r in results if r["phase"] == p and r["corroborated"])
        print(f"  {p:20s}: {p_fired}/{count} ({p_fired/max(1,count)*100:.1f}%)")

    # Similarity distribution
    sims = [r["similarity"] for r in results]
    if sims:
        print(f"\nSimilarity range: {min(sims):.3f} – {max(sims):.3f}")
        print(f"Similarity mean:  {sum(sims)/len(sims):.3f}")

    # Grade distribution
    reg_grades = Counter(r["reg_grade"] for r in results)
    sim_grades = Counter(r["sim_grade"] for r in results if r.get("sim_grade"))
    print(f"\nRegular grades: {dict(reg_grades)}")
    print(f"Simple grades:  {dict(sim_grades)}")

    # Failure reasons
    failures = [r for r in results if not r["corroborated"]]
    if failures:
        reasons = Counter(r.get("reason", "?") for r in failures)
        print(f"\nFailure reasons ({len(failures)} total):")
        for reason, count in reasons.most_common(5):
            print(f"  {count:4d}x {reason[:80]}")

    # Success sample
    successes = [r for r in results if r["corroborated"]]
    if successes:
        print(f"\nSample upgrades:")
        for r in successes[:5]:
            print(f"  [{r['phase']}] sim={r['similarity']:.3f} "
                  f"{r['reg_grade']}→{r['upgraded_grade']} "
                  f"weight={r['effective_weight']:.1f}")
            print(f"    {r['text'][:120]}...")

    print(f"\n{'=' * 70}")
    if fired > 0:
        print(f"✓ Corroboration fires on {fired/max(1,total)*100:.1f}% of semantically-matched claims")
        print(f"  Cross-source semantic matching is WORKING.")
    else:
        print("⚠️  No corroboration. Check:")
        print("  1. Similarity threshold too high?")
        print("  2. Grades all HASAN? (need some DAIF baselines)")
        print("  3. Independence check failing?")
    print("=" * 70)


if __name__ == "__main__":
    main()
