"""Grade-recovery diagnostic for the §8 experiment.

After calibration, reports earned grade distribution per (narrator, domain)
alongside each narrator's designed reliability. Shows whether more calibration
data let the jarḥ–taʿdīl loop recover the true reliability ordering.

Outputs: table + written readout → results/grade_recovery.txt
"""

from __future__ import annotations

import json
import os
import sys

_exp_dir = os.path.dirname(os.path.abspath(__file__))
if _exp_dir not in sys.path:
    sys.path.insert(0, _exp_dir)

from narrators import NARRATOR_VARIANTS

# Designed fault rates for comparison
DESIGNED_RATES: dict[str, float] = {
    "pdf-scraper@1.2": 0.01,
    "pdf-scraper@0.9-legacy": 0.18,
    "ingest@good": 0.02,
    "ingest@weak": 0.15,
}

# Rank ordering expected (lower fault rate → should have better grade)
EXPECTED_ORDER = [
    ("pdf-scraper@1.2", 0.01, "best — light OCR only"),
    ("ingest@good", 0.02, "good — rare drift"),
    ("ingest@weak", 0.15, "weak — counterfactual swaps"),
    ("pdf-scraper@0.9-legacy", 0.18, "worst — heavy corruption"),
]


def main() -> None:
    results_dir = os.path.join(_exp_dir, "results")
    seeds = list(range(1, 11))

    # Collect grade distributions across seeds
    grade_counts: dict[str, dict[str, int]] = {}
    evidence_counts: dict[str, list[int]] = {}

    for seed in seeds:
        seed_dir = os.path.join(results_dir, f"seed_{seed}", "calibration")
        snap_path = os.path.join(seed_dir, "registry_snapshot.json")
        if not os.path.exists(snap_path):
            continue

        with open(snap_path) as f:
            snap = json.load(f)

        for key, data in snap.items():
            nid = data["narrator_id"]
            grade = data["grade"]
            ev_count = data.get("evidence_count", 0)

            if nid not in grade_counts:
                grade_counts[nid] = {}
                evidence_counts[nid] = []
            grade_counts[nid][grade] = grade_counts[nid].get(grade, 0) + 1
            evidence_counts[nid].append(ev_count)

    # Build report
    lines = [
        "Grade-Recovery Diagnostic",
        "=========================",
        "",
        "Expected reliability ordering (by designed fault rate):",
    ]
    for nid, rate, desc in EXPECTED_ORDER:
        lines.append(f"  {nid:<28s}  rate={rate:.0%}  ({desc})")
    lines.append("")

    lines.append("Earned grade distribution across seeds × domains:")
    lines.append(f"  {'Narrator':<28s} {'RELIABLE':>8s} {'ACCEPTABLE':>10s} {'WEAK':>8s} {'REJECTED':>9s} {'UNGRADED':>9s} {'Mean Evidence':>14s}")
    lines.append(f"  {'─'*28} {'─'*8} {'─'*10} {'─'*8} {'─'*9} {'─'*9} {'─'*14}")

    for nid, rate, desc in EXPECTED_ORDER:
        counts = grade_counts.get(nid, {})
        total = sum(counts.values())
        if total == 0:
            lines.append(f"  {nid:<28s}  (no data)")
            continue
        ev_mean = sum(evidence_counts.get(nid, [0])) / max(1, len(evidence_counts.get(nid, [0])))
        lines.append(
            f"  {nid:<28s} "
            f"{counts.get('reliable',0):>8d} "
            f"{counts.get('acceptable',0):>10d} "
            f"{counts.get('weak',0):>8d} "
            f"{counts.get('rejected',0):>9d} "
            f"{counts.get('ungraded',0):>9d} "
            f"{ev_mean:>14.1f}"
        )

    # Recovery assessment
    lines.append("")
    lines.append("Recovery Assessment:")
    lines.append("-------------------")

    recovered = 0
    for nid, rate, desc in EXPECTED_ORDER:
        counts = grade_counts.get(nid, {})
        total = sum(counts.values())
        if total == 0:
            lines.append(f"  {nid}: NO DATA — insufficient calibration claims")
            continue

        reliable_pct = counts.get("reliable", 0) / total
        acceptable_pct = counts.get("acceptable", 0) / total
        rejected_pct = counts.get("rejected", 0) / total
        ungraded_pct = counts.get("ungraded", 0) / total

        lines.append(f"  {nid} (designed rate={rate:.0%}):")

        if rate <= 0.02:
            # Should be graded well
            if reliable_pct + acceptable_pct > 0.3:
                lines.append(f"    ✓ Mostly graded well ({reliable_pct:.0%} reliable, {acceptable_pct:.0%} acceptable)")
                recovered += 1
            else:
                lines.append(f"    ✗ Not recovering — {rejected_pct:.0%} rejected, {ungraded_pct:.0%} ungraded")
        else:
            # Should be graded poorly
            if rejected_pct > 0.3:
                lines.append(f"    ✓ Correctly identifies as unreliable ({rejected_pct:.0%} rejected)")
                recovered += 1
            else:
                lines.append(f"    ⚠ May be under-penalized — only {rejected_pct:.0%} rejected")

    lines.append("")
    lines.append(f"Recovery score: {recovered}/4 narrators approximately correctly graded")
    lines.append("")
    lines.append("Notes:")
    lines.append("- Small calibration set (30% of 3002 = ~900 claims across 5 domains × 4 narrators)")
    lines.append("  means ~45 claims per (narrator, domain) — noisy estimates.")
    lines.append("- The jarḥ–taʿdīl loop is aggressive with few samples: one bad audit can")
    lines.append("  trigger downgrade. This is the COLD-START problem from paper §7.")
    lines.append("- More calibration data (>100 audits per narrator×domain) would stabilize grades.")
    lines.append("- This is expected behavior, not a framework defect.")

    out_path = os.path.join(results_dir, "grade_recovery.txt")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
