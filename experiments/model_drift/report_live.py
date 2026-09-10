"""Render `results/live_results.json` into `results/LIVE_RESULTS.md` (live leaderboard)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_RESULTS = _HERE / "results"


def _tier_rows(record: dict[str, Any], tier: str) -> str:
    rows = [r for r in record["rows"] if r["tier"] == tier]
    depths = sorted({int(r["depth"]) for r in rows})
    lines = [
        f"### {tier.capitalize()} facts",
        "",
        "| Depth | hallucination_rate | served_error_rate | n |",
        "|---|---|---|---|",
    ]
    for d in depths:
        dr = [r for r in rows if r["depth"] == d]
        hall = [r for r in dr if r["ground_truth"] == "hallucinated"]
        served = [r for r in hall if r["served"]]
        hr = len(hall) / len(dr) if dr else 0.0
        ser = len(served) / len(hall) if hall else None
        ser_str = f"{ser:.3f}" if ser is not None else "n/a"
        lines.append(f"| {d} | {hr:.3f} | {ser_str} | {len(dr)} |")
    return "\n".join(lines)


def render(record: dict[str, Any]) -> str:
    pd = record["per_depth"]
    lines = [
        "# Model-drift leaderboard — LIVE results (#71)",
        "",
        f"**Model:** `{record['model']}` · **temperature:** {record['temperature']} · "
        f"**date:** {record['generated_date']}",
        f"**Calls:** {record['calls']} · **tokens:** {record['prompt_tokens']} in / "
        f"{record['completion_tokens']} out · **cost:** ${record['cost_usd']:.5f} "
        f"(cap ${record['cap_usd']:.2f})",
        f"**dataset_sha256:** `{record['dataset_sha256'][:16]}…`",
        "",
        "## Aggregate (all facts)",
        "",
        "| Depth | hallucination_rate (oracle) | served_error_rate (real critic) |",
        "|---|---|---|",
    ]
    for depth in sorted(pd, key=int):
        d = pd[depth]
        ser = d["served_error_rate"]
        ser_str = f"{ser:.3f}" if ser is not None else "n/a"
        lines.append(f"| {depth} | {d['hallucination_rate']:.3f} | {ser_str} |")
    lines += ["", "## By difficulty tier", ""]
    for tier in ("easy", "medium", "hard", "postcutoff"):
        lines.append(_tier_rows(record, tier))
        lines.append("")

    if "audit" in record:
        a = record["audit"]
        lines += [
            "## Oracle cross-check (independent LLM audit)",
            "",
            f"agreement rate: **{a['agreement_rate']:.3f}** ({a['n_agree']}/{a['n_checked']}) — "
            f"{a['note']}.",
            "",
        ]
    lines += [
        "## Honest limits",
        "",
        "- **Self-critique:** the narrator and critic are the SAME model (`deepseek-flash`);",
        "  a model is often lenient on its own output, so served_error_rate is optimistic.",
        "- **Single provider / single model.** No cross-family comparison yet.",
        "- **temperature = 0.0**: drift is deterministic knowledge error, not sampling noise.",
        "- **Oracle definition:** any numeric deviation at the canonical value's precision",
        "  (rounding, unit change) counts as drift; a more-precise correct answer is faithful.",
        "- **Cost** is derived from the API's token counts × the disclosed V4-Flash rate card",
        "  ($0.14/M in, $0.28/M out); the raw token totals are the ground truth.",
        "",
        f"Reproduce: `DEEPSEEK_API_KEY=… uv run python -m experiments.model_drift.live --audit`.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    record = json.loads((_RESULTS / "live_results.json").read_text())
    out = _RESULTS / "LIVE_RESULTS.md"
    out.write_text(render(record))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
