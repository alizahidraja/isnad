"""Analyze v2 experiment results with statistical measures."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "results"


def load(path: str = "results_v2.json") -> list[dict]:
    p = OUTPUT_DIR / path
    if not p.exists():
        print(f"ERROR: {p} not found. Run run.py first.")
        return []
    with open(p) as f:
        return json.load(f)


def main() -> None:
    results = load()
    if not results:
        return

    print("=" * 70)
    print("CORROBORATION v2 — STATISTICAL ANALYSIS")
    print("=" * 70)

    total = len(results)
    fired = sum(1 for r in results if r["corroborated"])
    upgraded = sum(1 for r in results if r["corroborated"]
                   and r.get("reg_grade") != r.get("upgraded_grade"))

    print(f"\n── OVERVIEW ──")
    print(f"Total claims:         {total}")
    print(f"Corroborated:         {fired} ({fired/max(1,total)*100:.1f}%)")
    print(f"Grade upgraded:       {upgraded} ({upgraded/max(1,total)*100:.1f}%)")

    # ── Phases ──
    phases = Counter(r["phase"] for r in results)
    print(f"\n── BY PHASE ──")
    for p, count in phases.most_common():
        p_fired = sum(1 for r in results if r["phase"] == p and r["corroborated"])
        pct = p_fired / max(1, count) * 100
        print(f"  {p:20s}: {p_fired}/{count} ({pct:.1f}%)")

    # ── Similarity ──
    sims = [r["similarity"] for r in results]
    if sims:
        print(f"\n── SIMILARITY DISTRIBUTION ──")
        print(f"  Min:    {min(sims):.4f}")
        print(f"  Max:    {max(sims):.4f}")
        print(f"  Mean:   {sum(sims)/len(sims):.4f}")
        print(f"  Median: {sorted(sims)[len(sims)//2]:.4f}")
        buckets = [(0.75, 0.80), (0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1.00)]
        for lo, hi in buckets:
            n = sum(1 for s in sims if lo <= s < hi)
            print(f"  [{lo:.2f}-{hi:.2f}): {n:4d} ({n/max(1,total)*100:.1f}%)")

    # ── Grades ──
    print(f"\n── GRADE DISTRIBUTION ──")
    reg_grades = Counter(r.get("reg_grade", "?") for r in results)
    sim_grades = Counter(r.get("sim_grade", "?") for r in results if r.get("sim_grade"))
    print(f"  Regular (base):   {dict(reg_grades)}")
    print(f"  Simple (corrob):  {dict(sim_grades)}")

    # ── Effective weights ──
    weights = [r["effective_weight"] for r in results]
    print(f"\n── EFFECTIVE WEIGHT ──")
    print(f"  Min:    {min(weights):.1f}")
    print(f"  Max:    {max(weights):.1f}")
    print(f"  Mean:   {sum(weights)/len(weights):.1f}")
    wdist = Counter(round(w, 0) for w in weights)
    for w, c in sorted(wdist.items()):
        print(f"  {w:.0f}: {c:4d} ({c/max(1,total)*100:.1f}%)")

    # ── Topics ──
    topics = Counter(r["topic"] for r in results)
    print(f"\n── TOPICS ({len(topics)} unique) ──")
    for t, c in topics.most_common(10):
        print(f"  {c:3d}x {t}")

    # ── Source URLs present ──
    has_url = sum(1 for r in results if r.get("url_reg"))
    print(f"\n── PROVENANCE ──")
    print(f"  With source URLs: {has_url}/{total} ({has_url/max(1,total)*100:.1f}%)")

    # ── Negative controls ──
    nc = load("negative_controls.json")
    if nc:
        print(f"\n── NEGATIVE CONTROLS ──")
        print(f"  Passed: {nc['passed']}/{nc['total']}")
        for c in nc["controls"]:
            status = "✅" if c["passed"] else "❌"
            print(f"  {status} {c['name']}")

    # ── Recommendations ──
    print(f"\n{'=' * 70}")
    print("PAPER-READY ASSESSMENT")
    if fired / max(1, total) >= 0.95 and has_url / max(1, total) >= 0.9:
        print("✅ Experiment is paper-ready:")
        print(f"   • {fired}/{total} corroboration fire rate")
        print(f"   • {has_url}/{total} claims have source URLs")
        print(f"   • {nc.get('passed', 0) if nc else 0}/{nc.get('total', 0) if nc else 0} negative controls pass")
        print(f"   • {len(topics)} unique topic pairs tested")
    else:
        print("⚠️  Issues to address:")
    print("=" * 70)


if __name__ == "__main__":
    main()
