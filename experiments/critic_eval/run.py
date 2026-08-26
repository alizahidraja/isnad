"""Run every content critic against the curated eval set (issue #96).

Usage:
    DEEPSEEK_API_KEY=sk-... python experiments/critic_eval/run.py

Runs, in order of semantic strength:
- EmbeddingCritic   (TF-IDF, offline)
- LocalNLICritic    (DeBERTa cross-encoder, offline, ~500MB model)
- HybridCritic      (MiniLM retrieval -> NLI, offline)
- LLMCritic         (DeepSeek, needs DEEPSEEK_API_KEY)

Writes ``RESULTS.md`` and ``results.json`` into this directory. The primary
metric is contradiction detection (recall/precision/F1); the false-consistent
rate (a contradiction mislabeled CONSISTENT) is reported separately as the
dangerous error.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from isnad.critics import ContentCritic, EmbeddingCritic, HybridCritic, LLMCritic, LocalNLICritic
from isnad.types import ContentVerdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_set import CONSISTENT_CASES, CONTRADICTION_CASES, CORPUS, UNRELATED_CASES, all_cases  # noqa: E402

_HERE = Path(__file__).resolve().parent


def evaluate_critic(
    critic: ContentCritic,
    cases: list[tuple[str, str, str]],
    corpus: list[str],
    *,
    domain: str = "physics",
) -> list[tuple[str, str, str]]:
    """Return (label, expected_verdict, actual_verdict) per case."""
    out: list[tuple[str, str, str]] = []
    for claim, label, expected in cases:
        v = critic.evaluate(claim, claim.lower(), corpus, domain)
        out.append((label, expected, v.value))
    return out


def compute_metrics(results: list[tuple[str, str, str]]) -> dict[str, object]:
    """Metrics over (label, expected_verdict, actual_verdict) triples."""
    n = len(results)
    contra = [r for r in results if r[0] == "contradiction"]
    consis = [r for r in results if r[0] == "consistent"]
    unrel = [r for r in results if r[0] == "unrelated"]

    tp = sum(1 for r in contra if r[2] == ContentVerdict.CONTRADICTION.value)  # caught
    false_consistent = sum(1 for r in contra if r[2] == ContentVerdict.CONSISTENT.value)
    false_contradiction = sum(1 for r in consis if r[2] == ContentVerdict.CONTRADICTION.value)
    # a CONTRADICTION verdict against anything that isn't a contradiction = false positive
    fp = sum(
        1 for r in results if r[0] != "contradiction" and r[2] == ContentVerdict.CONTRADICTION.value
    )

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / len(contra) if contra else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    # unrelated handled correctly = UNVERIFIABLE
    unrel_correct = sum(1 for r in unrel if r[2] == ContentVerdict.UNVERIFIABLE.value)
    # overall 3-way accuracy
    correct = sum(1 for r in results if r[2] == r[1])

    return {
        "n": n,
        "contradiction_recall": round(recall, 3),
        "contradiction_precision": round(precision, 3),
        "contradiction_f1": round(f1, 3),
        "false_consistent_rate": round(false_consistent / len(contra), 3) if contra else 0.0,
        "false_contradiction_rate": round(false_contradiction / len(consis), 3) if consis else 0.0,
        "unrelated_unverifiable_rate": round(unrel_correct / len(unrel), 3) if unrel else 0.0,
        "three_way_accuracy": round(correct / n, 3) if n else 0.0,
        "tp": tp,
        "fp": fp,
        "false_consistent": false_consistent,
        "false_contradiction": false_contradiction,
    }


def build_report(rows: list[tuple[str, dict[str, object]]]) -> str:
    lines = [
        "# Content Critic Evaluation — committed results (issue #96)",
        "",
        f"**Corpus:** {len(CORPUS)} physics facts · **Cases:** "
        f"{sum(len(x) for x in (CONSISTENT_CASES, CONTRADICTION_CASES, UNRELATED_CASES))} "
        f"({len(CONSISTENT_CASES)} consistent, {len(CONTRADICTION_CASES)} contradiction, "
        f"{len(UNRELATED_CASES)} unrelated)",
        "",
        "| Critic | Contra. recall | Contra. precision | Contra. F1 | False-consistent (danger) | False-contradiction | 3-way acc |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, m in rows:
        lines.append(
            f"| {name} | {m['contradiction_recall']:.3f} | {m['contradiction_precision']:.3f} "
            f"| {m['contradiction_f1']:.3f} | {m['false_consistent_rate']:.3f} "
            f"| {m['false_contradiction_rate']:.3f} | {m['three_way_accuracy']:.3f} |"
        )
    lines += [
        "",
        "## Reading the numbers",
        "",
        "- **Contradiction recall** — of the genuine contradictions, how many were flagged.",
        '  This is the headline "semantic recall" the docs quote.',
        "- **False-consistent rate** — contradictions *mislabeled* CONSISTENT. This is the",
        "  dangerous error: a wrong claim served as if correct.",
        "- **False-contradiction rate** — consistent claims flagged as contradictions",
        "  (wasted review, not a safety failure).",
        "- **3-way accuracy** — exact match across consistent/contradiction/unrelated.",
        "",
        "The offline critics (Embedding / LocalNLI / Hybrid) are deterministic; the",
        "LLM critic was run once with `temperature=0`. Results are committed so the",
        "numbers in `docs/critics.md` are measured, not estimated.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    cases = all_cases()
    critics: list[tuple[str, ContentCritic]] = [
        ("EmbeddingCritic (TF-IDF)", EmbeddingCritic()),
        ("LocalNLICritic (DeBERTa NLI)", LocalNLICritic()),
        ("HybridCritic (MiniLM → NLI)", HybridCritic()),
        (
            "LLMCritic (DeepSeek)",
            LLMCritic(provider="deepseek", cache_dir=str(_HERE / ".llm_cache")),
        ),
    ]

    rows: list[tuple[str, dict[str, object]]] = []
    for name, critic in critics:
        t0 = time.time()
        results = evaluate_critic(critic, cases, CORPUS)
        m = compute_metrics(results)
        m["elapsed_s"] = round(time.time() - t0, 1)
        rows.append((name, m))
        print(
            f"{name:32s} recall={m['contradiction_recall']:.3f} "
            f"falseConsistent={m['false_consistent_rate']:.3f} "
            f"({m['elapsed_s']}s)"
        )

    # Persist raw verdicts for auditability.
    raw = {name: evaluate_critic(c, cases, CORPUS) for name, c in critics}
    with open(_HERE / "results.json", "w") as f:
        json.dump(
            {"corpus": CORPUS, "cases": cases, "metrics": dict(rows), "raw": raw}, f, indent=2
        )

    (_HERE / "RESULTS.md").write_text(build_report(rows))
    print(f"\nWrote {_HERE / 'RESULTS.md'} and results.json")


if __name__ == "__main__":
    main()
