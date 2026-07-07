"""Analysis — compute metrics and generate figures for the §8 experiment.

Reads all_results.json, computes:
- Primary: served-error rate at B=10% (ISNAD-gated vs. confidence-gated)
- Secondary: error rates across all conditions/budgets, review precision,
  coverage, corroboration effect.
- Mean ± 95% CI over seeds.
- Risk–coverage data for plotting.
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict

_exp_dir = os.path.dirname(os.path.abspath(__file__))


def load_results() -> dict:
    path = os.path.join(_exp_dir, "results", "all_results.json")
    if not os.path.exists(path):
        print("No results found. Run run.py first.")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def summarize(results: dict) -> dict:
    """Compute summary statistics per (condition, budget) across seeds."""
    grouped: dict[tuple[str, float], list[dict]] = defaultdict(list)
    for key, entry in results.items():
        cond = entry["condition"]
        budget = entry["budget"]
        grouped[(cond, budget)].append(entry)

    summary = {}
    for (cond, budget), entries in sorted(grouped.items()):
        n = len(entries)
        metrics = ["coverage", "served_error_rate", "review_precision"]
        stats: dict[str, float] = {}
        for m in metrics:
            vals = [e[m] for e in entries]
            mean = sum(vals) / n
            std = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
            ci = 1.96 * std / math.sqrt(n)  # 95% CI
            stats[f"{m}_mean"] = mean
            stats[f"{m}_ci95"] = ci

        summary[f"{cond}_b{int(budget*100):02d}"] = {
            "condition": cond,
            "budget": budget,
            "n_seeds": n,
            **stats,
        }
    return summary


def primary_comparison(results: dict) -> dict:
    """Primary preregistered comparison at B=10%."""
    isnad_entries = [
        e for e in results.values()
        if e["condition"] == "isnad" and e["budget"] == 0.10
    ]
    conf_entries = [
        e for e in results.values()
        if e["condition"] == "confidence" and e["budget"] == 0.10
    ]

    isnad_errors = [e["served_error_rate"] for e in isnad_entries]
    conf_errors = [e["served_error_rate"] for e in conf_entries]

    n = len(isnad_errors)
    if n == 0:
        return {"error": "No ISNAD results at B=10%"}

    diffs = [i - c for i, c in zip(isnad_errors, conf_errors)]
    mean_diff = sum(diffs) / n
    std_diff = math.sqrt(sum((d - mean_diff) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0
    ci_diff = 1.96 * std_diff / math.sqrt(n)

    isnad_mean = sum(isnad_errors) / n
    conf_mean = sum(conf_errors) / n

    significant = (mean_diff + ci_diff < 0)  # CI entirely below zero
    direction = "ISNAD lower" if mean_diff < 0 else "confidence lower"

    return {
        "isnad_mean_error_rate": isnad_mean,
        "confidence_mean_error_rate": conf_mean,
        "mean_difference": mean_diff,
        "ci95_difference": ci_diff,
        "significant": significant,
        "direction": direction,
        "n_seeds": n,
    }


def generate_report(results: dict) -> str:
    """Generate RESULTS.md content."""
    summary = summarize(results)
    primary = primary_comparison(results)

    lines = [
        "# §8 Validation Experiment — Results",
        "",
        f"**Date:** 2026-07-06",
        f"**Analysis Plan:** ANALYSIS_PLAN.md (preregistered before results)",
        "",
        "## Primary Result: ISNAD-gated vs. Confidence-gated at B=10%",
        "",
    ]

    if "error" in primary:
        lines.append(f"⚠ {primary['error']}")
    else:
        isnad_err = primary["isnad_mean_error_rate"]
        conf_err = primary["confidence_mean_error_rate"]
        diff = primary["mean_difference"]
        ci = primary["ci95_difference"]
        sig = "✓ Significant" if primary["significant"] else "✗ Not significant"

        lines.append(f"| Condition | Served-Error Rate (mean ± 95% CI) |")
        lines.append(f"|---|---|")
        lines.append(f"| ISNAD-gated | {isnad_err:.4f} |")
        lines.append(f"| Confidence-gated | {conf_err:.4f} |")
        lines.append(f"| Difference (ISNAD − confidence) | {diff:+.4f} ± {ci:.4f} |")
        lines.append(f"| Significant? | {sig} |")
        lines.append("")

        if primary["significant"] and diff < 0:
            lines.append(
                f"**Conclusion:** ISNAD-gated serving reduced the served-error rate "
                f"by {abs(diff):.2%} (95% CI [{diff-ci:.4f}, {diff+ci:.4f}]) "
                f"relative to confidence-gated serving at B=10% on this corpus. "
                f"The §8 hypothesis is **supported** on this corpus."
            )
        elif primary["significant"] and diff > 0:
            lines.append(
                f"**Conclusion:** ISNAD-gated serving INCREASED the served-error rate "
                f"at B=10%. The §8 hypothesis is **refuted** on this corpus."
            )
        else:
            lines.append(
                f"**Conclusion:** The difference was not statistically significant. "
                f"The §8 hypothesis is **inconclusive** on this corpus — a larger "
                f"corpus or more seeds may be needed."
            )

    lines.extend([
        "",
        "## All Conditions — Served-Error Rate vs. Budget",
        "",
        "| Condition | B=2% | B=5% | B=10% | B=20% |",
        "|---|---|---|---|---|",
    ])

    for cond in ["ungated", "confidence", "isnad", "isnad_no_corroboration"]:
        row = f"| {cond} |"
        for b in [0.02, 0.05, 0.10, 0.20]:
            key = f"{cond}_b{int(b*100):02d}"
            if key in summary:
                row += f" {summary[key]['served_error_rate_mean']:.4f} |"
            else:
                row += " — |"
        lines.append(row)

    lines.extend([
        "",
        "## Review-Queue Precision",
        "",
        "| Condition | B=10% Precision |",
        "|---|---|",
    ])
    for cond in ["ungated", "confidence", "isnad"]:
        key = f"{cond}_b10"
        if key in summary:
            p = summary[key]["review_precision_mean"]
            lines.append(f"| {cond} | {p:.3f} |")

    lines.extend([
        "",
        "## Coverage (Fraction of Claims Served)",
        "",
        "| Condition | B=10% Coverage |",
        "|---|---|",
    ])
    for cond in ["ungated", "confidence", "isnad", "isnad_no_corroboration"]:
        key = f"{cond}_b10"
        if key in summary:
            cov = summary[key]["coverage_mean"]
            lines.append(f"| {cond} | {cov:.3f} |")

    lines.extend([
        "",
        "## Corroboration Effect (Ablation)",
        "",
        "Coverage difference between ISNAD-gated with and without corroboration "
        "at B=10% isolates the mutābaʿāt rule's effect on trust recovery.",
    ])

    lines.extend([
        "",
        "## Limitations",
        "",
        "- Simulated-perfect human reviewer → review-precision is realistic-cost metric.",
        "- Synthetic rule-based faults → real fault distributions may differ.",
        "- Single corpus domain (undergraduate physics) → limited external validity.",
        "- Single extraction model → different extractors may shift claim distributions.",
        "- Pre-generated corpus chunks (not live PDF extraction) for reproducibility.",
        "- Corpus size was below the ≥3000 claim target (see extract output).",
    ])

    return "\n".join(lines)


def main() -> None:
    results = load_results()
    summary = summarize(results)
    primary = primary_comparison(results)

    print("=== Primary Result ===")
    for k, v in primary.items():
        print(f"  {k}: {v}")

    print("\n=== Summary Table ===")
    for key, s in sorted(summary.items()):
        print(f"  {key}: coverage={s['coverage_mean']:.3f}  "
              f"error={s['served_error_rate_mean']:.4f}±{s['served_error_rate_ci95']:.4f}  "
              f"prec={s['review_precision_mean']:.3f}")

    report = generate_report(results)
    report_path = os.path.join(_exp_dir, "results", "RESULTS.md")
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
