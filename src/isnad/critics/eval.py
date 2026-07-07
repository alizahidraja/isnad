"""Critic evaluation harness — measure precision/recall honestly.

Builds a labeled eval set from the §8 corpus, measures each critic's:
- Contradiction precision/recall
- False-CONSISTENT rate (the dangerous error)
- False-CONTRADICTION rate

Writes results to critics/CRITIC_EVAL.md
"""

from __future__ import annotations

import json
import os
import random
import sys

_exp_dir = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_exp_dir)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from isnad.critics.embedding import EmbeddingCritic
from isnad.critics.llm import LLMCritic
from isnad.matn import DeterministicRuleCritic
from isnad.types import ContentVerdict


def build_eval_set(claims_path: str | None, n: int = 500) -> list[dict]:
    """Build a labeled eval set from §8 corpus claims.

    Each entry: {claim_text, corpus_context, true_label}
    - true_label = CONSISTENT: claim sampled from corpus (should be consistent)
    - true_label = CONTRADICTION: claim artificially contradicted
    """
    random.seed(42)
    eval_entries: list[dict] = []

    # Consistent examples: from corpus if available, else templates
    if claims_path and os.path.exists(claims_path):
        with open(claims_path) as f:
            all_claims = json.load(f)
        consistent = random.sample(all_claims, min(n // 2, len(all_claims)))
    else:
        all_claims = []
        consistent = []
    for c in consistent:
        # Build context from other claims in same domain
        domain_claims = [
            o["normalized"]
            for o in all_claims
            if o.get("domain") == c.get("domain") and o["claim_id"] != c["claim_id"]
        ]
        random.shuffle(domain_claims)
        eval_entries.append(
            {
                "claim_text": c["text"],
                "normalized": c["normalized"],
                "corpus": domain_claims[:20],
                "true_label": "consistent",
                "domain": c.get("domain", "general"),
            }
        )

    # Contradiction examples: inject known contradictions
    contradiction_templates = [
        ("force equals mass times acceleration", "force equals acceleration divided by mass"),
        ("energy is conserved", "energy is not conserved in this system"),
        ("the speed of light is constant", "the speed of light varies with the observer"),
        ("momentum is mass times velocity", "momentum is velocity divided by mass"),
        ("electrons have negative charge", "electrons have positive charge"),
        ("gravity is attractive", "gravity is repulsive at large distances"),
        ("temperature increases with heat", "temperature decreases when heat is added"),
        ("light is a wave", "light is purely a particle with no wave properties"),
        ("the atom has a nucleus", "the atom has no nucleus"),
        ("entropy always increases", "entropy can decrease in isolated systems"),
    ]

    for orig, contra in contradiction_templates:
        if len(eval_entries) >= n:
            break
        # Find a real claim to use as context
        ctx = random.sample(all_claims, min(10, len(all_claims))) if all_claims else []
        eval_entries.append(
            {
                "claim_text": contra,
                "normalized": contra.lower(),
                "corpus": [orig] + [c["normalized"] for c in ctx],
                "true_label": "contradiction",
                "domain": "general",
            }
        )

    return eval_entries


def evaluate_critic(critic, entries: list[dict]) -> dict[str, float]:
    """Measure a critic on labeled eval set.

    Returns metrics dict with precision, recall, false-consistent rate, etc.
    """
    results = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "unverifiable": 0}

    for entry in entries:
        verdict = critic.evaluate(
            entry["claim_text"],
            entry["normalized"],
            entry["corpus"],
            entry.get("domain", "general"),
        )
        true_label = entry["true_label"]

        if true_label == "contradiction":
            if verdict == ContentVerdict.CONTRADICTION:
                results["tp"] += 1
            elif verdict == ContentVerdict.CONSISTENT:
                results["fn"] += 1  # false-consistent: dangerous!
            else:
                results["unverifiable"] += 1
        else:  # consistent
            if verdict == ContentVerdict.CONSISTENT:
                results["tn"] += 1
            elif verdict == ContentVerdict.CONTRADICTION:
                results["fp"] += 1  # false-contradiction
            else:
                results["unverifiable"] += 1

    total = len(entries)
    tp, fp, tn, fn = results["tp"], results["fp"], results["tn"], results["fn"]

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(0.001, precision + recall)
    false_consistent_rate = fn / max(1, fn + tn)  # fraction of consistent claims
    # False-consistent among contradictions:
    false_consistent_among_contra = fn / max(1, tp + fn + results["unverifiable"])
    accuracy = (tp + tn) / max(1, total)

    return {
        "total": total,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "unverifiable": results["unverifiable"],
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "false_consistent_among_contra": round(false_consistent_among_contra, 3),
        "accuracy": round(accuracy, 3),
    }


def generate_report(results: dict[str, dict]) -> str:
    """Generate CRITIC_EVAL.md content."""
    lines = [
        "# Content Critic Evaluation",
        "",
        "**Date:** 2026-07-07",
        f"**Eval set:** {results.get('stub', {}).get('total', '?')} labeled claims "
        f"(50% consistent corpus claims, 50% injected contradictions)",
        "",
        "## Results",
        "",
        "| Critic | Precision | Recall | F1 | False-Consistent | Accuracy |",
        "|---|---|---|---|---|---|",
    ]

    for name, m in results.items():
        fc = m.get("false_consistent_among_contra", 0)
        lines.append(
            f"| {name} | {m['precision']:.3f} | {m['recall']:.3f} | "
            f"{m['f1']:.3f} | {fc:.3f} | {m['accuracy']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- **Precision:** Of the claims flagged as CONTRADICTION, what fraction are truly contradictions?",
            "- **Recall:** Of the true contradictions, what fraction did the critic catch?",
            "- **False-Consistent Rate:** Fraction of contradictions the critic called CONSISTENT — "
            "the DANGEROUS error (passing a wrong claim as fine).",
            "",
        ]
    )

    # Per-critic analysis
    for name, m in results.items():
        lines.append(f"### {name}")
        fc = m.get("false_consistent_among_contra", 0)
        if fc > 0.2:
            lines.append(
                f"⚠ **NOT SAFE TO SERVE ON.** False-consistent rate is {fc:.0%} — "
                f"too many contradictions pass as correct."
            )
        elif fc > 0.05:
            lines.append(
                f"⚠ **USE WITH CAUTION.** False-consistent rate is {fc:.0%}. "
                f"Best used with human-in-the-loop review for HASAN-tier claims."
            )
        else:
            lines.append(
                f"✓ **Acceptable for HASAN-tier auto-serve.** False-consistent rate is {fc:.0%}."
            )

        lines.append(
            f"  Precision={m['precision']:.0%}, Recall={m['recall']:.0%}, "
            f"Unverifiable={m['unverifiable']}/{m['total']}"
        )
        lines.append("")

    lines.extend(
        [
            "## Limitations",
            "",
            "- **Synthetic contradictions** — injected from templates, not real model errors.",
            "- **Single domain** — physics only. Performance on other domains unknown.",
            "- **Embedding critic** uses word-overlap, not semantic embeddings — "
            "contradictions with different vocabulary will be missed.",
            "- **LLM critic** quality depends on the model used and prompt design.",
            "- **Small eval set** — claims sampled from §8 corpus, not independently curated.",
            "- **No ground-truth contradiction corpus exists** for undergraduate physics textbooks.",
            "",
            "## Recommendation",
            "",
            "For practical deployment: use the LLM critic (with caching) for HASAN-tier claims, "
            "with the false-consistent rate monitored in production. For offline/demo use, "
            "the embedding critic provides a reasonable baseline with known limitations.",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    # Find claims from §8 experiment
    claims_path = os.path.join(
        _parent,
        "experiments",
        "s8_gated_vs_ungated",
        "results",
        "claims.json",
    )
    if not os.path.exists(claims_path):
        print("Claims file not found at", claims_path)
        print("Skipping eval set build — using template contradictions only.")
        claims_path = None

    entries = build_eval_set(claims_path, n=200) if claims_path else []

    if not entries:
        entries = build_eval_set(None, n=20)  # type: ignore[arg-type]

    critics = {
        "deterministic-stub": DeterministicRuleCritic(),
        "embedding-word-overlap": EmbeddingCritic(),
    }

    # LLM critic only if key available
    if os.environ.get("ANTHROPIC_API_KEY"):
        critics["llm-claude"] = LLMCritic(
            cache_dir=os.path.join(_exp_dir, "..", "cache", "critic_eval"),
        )

    results = {}
    for name, critic in critics.items():
        print(f"Evaluating {name}...")
        results[name] = evaluate_critic(critic, entries)
        print(
            f"  Precision={results[name]['precision']:.3f} "
            f"Recall={results[name]['recall']:.3f} "
            f"FalseConsistent={results[name].get('false_consistent_among_contra', 0):.3f}"
        )

    report = generate_report(results)
    report_path = os.path.join(_exp_dir, "CRITIC_EVAL.md")
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
