"""Leaderboard renderer (#71): turn results.json into RESULTS.md (Markdown)."""

from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_RESULTS = _HERE / "results"


def render() -> str:
    record = json.loads((_RESULTS / "results.json").read_text())
    rows = record["rows"]
    depths = record["depths"]

    lines = [
        "# Model-drift leaderboard — committed results (#71)",
        "",
        f"**Generated:** {record['generated_date']} · **seed:** {record['seed']} · "
        f"**corruption_probability:** {record['corruption_probability']} · "
        f"**dataset_sha256:** `{record['dataset_sha256'][:16]}…`",
        "",
        "The **hallucination rate** (ground-truth oracle) grows with chain depth. The",
        "**served-error rate** is how often the pipeline still SERVEs a hallucinated claim.",
        "",
        "| Depth | hallucination_rate | served_error_rate (perfect critic) | served_error_rate (empty critic) |",
        "|---|---|---|---|",
    ]
    for depth in depths:
        perfect = next(r for r in rows if r["depth"] == depth and r["critic_mode"] == "perfect")
        empty = next(r for r in rows if r["depth"] == depth and r["critic_mode"] == "empty")
        lines.append(
            f"| {depth} | {perfect['hallucination_rate']:.3f} | {perfect['served_error_rate']:.3f} | {empty['served_error_rate']:.3f} |"
        )
    lines += [
        "",
        "## Reading the numbers",
        "",
        "- **hallucination_rate** is the ground truth (oracle), independent of the critic.",
        "- **served_error_rate (perfect critic)** is the pipeline's ceiling: the decision",
        "  matrix catches 100% by construction — this row verifies the harness plumbing,",
        "  not critic quality.",
        "- **served_error_rate (empty critic)** is the negative control: a useless critic",
        "  (always UNVERIFIABLE) serves every hallucinated claim with caveat.",
        f"- **No-gating baseline:** {record['no_gating_baseline']['served_error_rate']:.1f} "
        "(serve-everything serves every hallucinated claim by construction).",
        "",
        "## Honest limits",
        "",
        "- **Offline mode only.** Live multi-family numbers require paid API keys and incur",
        "  cost; they are a separate keyed phase. Cells that were not actually run are",
        '  rendered "not run", never fabricated.',
        "- Single seed dataset (12 facts). The `offline-drift` injector is a deterministic",
        "  stand-in for a real model, preregistered at corruption_probability = "
        f"{record['corruption_probability']}.",
        "- The metric does **not** claim general hallucination-detection superiority.",
        "",
        "Reproduce: `uv run python -m experiments.model_drift.run --seed 0`.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    out = _RESULTS / "RESULTS.md"
    out.write_text(render())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
