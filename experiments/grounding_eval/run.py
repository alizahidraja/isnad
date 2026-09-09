"""Measure the chain-grounding policy's FP rate against a real critic (#239).

`ChainScopedGroundingPolicy` flags `grounded_off_chain_only` when a claim is
CONSISTENT off-chain but UNVERIFIABLE on-chain. The default `EmbeddingCritic` is
contradiction-only (never returns CONSISTENT), so a harness on it reports FP=0 by
construction — the oracle-tautology #215 eliminated for content-madār. This harness
drives the policy with `LocalNLICritic(gate_affirmation=False)` so it can actually
affirm CONSISTENT, and reports the flag's recall and false-positive rate honestly.

Two tautology traps are bypassed and documented:
1. `EmbeddingCritic` — contradiction-only (FP=0 by construction). Shown only as the
   baseline to contrast, never as the measurement.
2. `affirmation_gate` — default-ON, downgrades CONSISTENT->UNVERIFIABLE for
   nli/llm/hybrid critics unless a license record exists. `gate_affirmation=False`
   bypasses it so CONSISTENT can be emitted.

Usage (requires the nli extra):
    uv sync --extra nli && uv run python experiments/grounding_eval/run.py

Writes RESULTS.md and results.json into this directory.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.chain_grounding import ChainScopedGroundingPolicy
from isnad.types import ContentVerdict
from isnad.critics.base import ContentCritic

sys.path.insert(0, str(Path(__file__).resolve().parent))

from grounding_eval_set import all_cases  # noqa: E402

_HERE = Path(__file__).resolve().parent


def _eval_set_sha256(cases: list[tuple[str, str, list[str], list[str]]]) -> str:
    payload = json.dumps(cases, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _chain_for(on_chain_rows: list[str]) -> Chain:
    if on_chain_rows:
        link = ChainLinkSpec(narrator_id="src", step=0, retrieved_rows=list(on_chain_rows))
    else:
        link = ChainLinkSpec(narrator_id="src", step=0)
    return Chain([link])


def _run(critic: ContentCritic) -> list[tuple[str, bool, ContentVerdict, ContentVerdict | None]]:
    policy = ChainScopedGroundingPolicy()
    rows = []
    for label, claim, on_chain, off_chain in all_cases():
        chain = _chain_for(on_chain)
        res = policy.evaluate(claim, claim, chain, list(off_chain), critic)
        rows.append((label, res.grounded_off_chain_only, res.off_chain_verdict, res.on_chain_verdict))
    return rows


def _metrics(rows: list[tuple[str, bool, ContentVerdict, ContentVerdict | None]]) -> dict[str, object]:
    pos = [r for r in rows if r[0] == "grounded_off_chain_only"]
    neg_on_chain = [r for r in rows if r[0] == "grounded_on_chain"]
    neg_nowhere = [r for r in rows if r[0] == "grounded_nowhere"]
    neg_contra = [r for r in rows if r[0] == "on_chain_contradiction"]
    negatives = neg_on_chain + neg_nowhere + neg_contra

    tp = sum(1 for r in pos if r[1])
    fn = len(pos) - tp
    fp = sum(1 for r in negatives if r[1])
    tn = len(negatives) - fp

    recall = tp / len(pos) if pos else 0.0
    fp_rate = fp / len(negatives) if negatives else 0.0
    return {
        "n": len(rows),
        "n_positive": len(pos),
        "n_grounded_on_chain": len(neg_on_chain),
        "n_grounded_nowhere": len(neg_nowhere),
        "n_on_chain_contradiction": len(neg_contra),
        "recall": round(recall, 3),
        "false_positive_rate": round(fp_rate, 3),
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
    }


def main() -> None:
    cases = all_cases()
    sha = _eval_set_sha256(cases)

    try:
        from isnad.critics.nli import LocalNLICritic

        nli_critic = LocalNLICritic(gate_affirmation=False)
    except Exception as exc:  # noqa: BLE001 — the abort message is the point
        print(f"ABORT: could not construct LocalNLICritic — install the `nli` extra. ({exc})")
        sys.exit(1)

    nli_rows = _run(nli_critic)

    # Degeneracy guard: a contradiction-only / failed critic emits zero CONSISTENT
    # and would report FP=0 by construction. Abort instead of writing that.
    positives = [r for r in nli_rows if r[0] == "grounded_off_chain_only"]
    n_consistent_off = sum(1 for r in positives if r[2] is ContentVerdict.CONSISTENT)
    if n_consistent_off == 0:
        print("ABORT: LocalNLICritic emitted zero CONSISTENT verdicts on positive cases — "
              "model failed to load or sentence-transformers absent. Install the `nli` extra.")
        sys.exit(1)

    # Baseline: EmbeddingCritic is contradiction-only -> 0 flags by construction.
    try:
        from isnad.critics.embedding import EmbeddingCritic

        emb_rows = _run(EmbeddingCritic())
        emb_metrics = _metrics(emb_rows)
        emb_flags = sum(1 for r in emb_rows if r[1])
    except Exception:  # noqa: BLE001
        emb_metrics = None
        emb_flags = None

    nli_metrics = _metrics(nli_rows)

    record = {
        "schema_version": 1,
        "component": "chain_grounding",
        "eval_set_sha256": sha,
        "critic": "LocalNLICritic(gate_affirmation=False)",
        "metrics": nli_metrics,
        "embedding_baseline_flags": emb_flags,
        "per_case": [
            {
                "label": label,
                "flagged": flagged,
                "off_chain_verdict": off.value,
                "on_chain_verdict": on.value if on is not None else None,
            }
            for label, flagged, off, on in nli_rows
        ],
        "cases": cases,
    }
    (_HERE / "results.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")

    lines = [
        "# Chain-grounding policy — measured FP (#239)",
        "",
        f"**Eval set:** {nli_metrics['n']} cases "
        f"({nli_metrics['n_positive']} grounded-off-chain-only positive, "
        f"{nli_metrics['n_grounded_on_chain']} grounded-on-chain, "
        f"{nli_metrics['n_grounded_nowhere']} grounded-nowhere, "
        f"{nli_metrics['n_on_chain_contradiction']} on-chain-contradiction) · "
        f"`eval_set_sha256={sha[:16]}…`",
        "",
        f"**Critic:** `LocalNLICritic(gate_affirmation=False)` — the affirmation gate is "
        "bypassed so CONSISTENT can actually be emitted (default gate would downgrade it "
        "to UNVERIFIABLE, reproducing the FP=0-by-construction trap).",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| recall (grounded-off-chain-only flagged) | {nli_metrics['recall']:.3f} |",
        f"| **false-positive rate** (negatives flagged) | **{nli_metrics['false_positive_rate']:.3f}** |",
        f"| true positives / false negatives | {nli_metrics['tp']} / {nli_metrics['fn']} |",
        f"| false positives / true negatives | {nli_metrics['fp']} / {nli_metrics['tn']} |",
        "",
        f"**EmbeddingCritic baseline:** {emb_flags if emb_flags is not None else 'n/a'} flags — "
        "contradiction-only, so FP=0 is *by construction*, not a measurement. The NLI row "
        "above is the measured signal.",
        "",
        "## Honest limits",
        "",
        "Small pilot set (10 hand-labeled cases). The measured FP is a direction, not a tight "
        "estimate; a real critic's semantic errors propagate into the flag unmeasured here. "
        "The policy's predicate and the decision matrix are unchanged — this only measures.",
    ]
    (_HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")

    print(f"nli    recall={nli_metrics['recall']:.3f} FP={nli_metrics['false_positive_rate']:.3f}")
    print(f"       (embedding baseline flags={emb_flags})")
    print(f"\nWrote {_HERE / 'RESULTS.md'} and results.json")


if __name__ == "__main__":
    main()
