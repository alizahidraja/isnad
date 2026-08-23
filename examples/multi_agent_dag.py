"""Four agents, a branching DAG, and two honest findings.

A real agent system is a DAG, not a list: two sources feed a retriever, which
feeds a synthesis model.  This demo builds that DAG as an AuditRecord with
explicit ``upstream_ids`` and shows:

1. ``weakest_link`` correctly names the degraded node; and
2. a case where it does **not** — the sleeper's first lie — because
   weakest-link grading keys on *narrator grades*, not *per-claim* behaviour.

Honesty is the brand: the second case is as much the point as the first.

Run:  python examples/multi_agent_dag.py
"""

from __future__ import annotations

from isnad.audit import (
    ChainNodeAudit,
    GradingStrategy,
    SourceDocument,
    WeakestLink,
    build_audit_record_from_nodes,
)


def _show(title: str, nodes: list[ChainNodeAudit], weakest: WeakestLink, final_grade: str) -> None:
    rec = build_audit_record_from_nodes(
        claim_id="claim-1",
        claim_text="water freezes at zero degrees celsius",
        final_grade=final_grade,
        grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
        nodes=nodes,
        weakest_link=weakest,
        source_documents=[SourceDocument("https://openstax.org/physics", licence="CC-BY-4.0")],
    )
    print(f"\n{title}")
    print("  DAG edges:")
    for n in rec.chain:
        ups = ", ".join(n.upstream_ids) or "(root)"
        print(f"    {n.narrator_id:16} grade={n.grade:12} upstream=[{ups}]")
    print(f"  final_grade={rec.final_grade}  weakest_link={rec.weakest_link.narrator_id}")
    print(f"  record_hash={rec.integrity.record_hash[:16]}…")


def main() -> None:
    print("=" * 70)
    print("Multi-agent DAG — and where weakest_link is honest about its limits")
    print("=" * 70)

    # Case 1: the degraded source is correctly identified.
    _show(
        "Case 1 — a degraded synthesis model is named",
        [
            ChainNodeAudit("source:a", "dataset", "reliable", "clean source"),
            ChainNodeAudit("source:b", "dataset", "reliable", "clean source"),
            ChainNodeAudit(
                "retriever",
                "retriever",
                "acceptable",
                "merged sources",
                upstream_ids=["source:a", "source:b"],
            ),
            ChainNodeAudit(
                "model:synth",
                "model",
                "weak",
                "over-reaches in synthesis",
                upstream_ids=["retriever"],
            ),
        ],
        WeakestLink("model:synth", "weak", "lowest narrator grade in the chain"),
        final_grade="daif",
    )

    # Case 2: the honest miss.  A RELIABLE narrator degrades on ONE claim (the
    # sleeper's first lie).  Its grade is still RELIABLE, so weakest_link does
    # not flag it — per-claim degradation is invisible to per-narrator grading.
    _show(
        "Case 2 — the sleeper's first lie (NOT caught by weakest_link)",
        [
            ChainNodeAudit("source:a", "dataset", "reliable", "clean source"),
            ChainNodeAudit(
                "model:trusted", "model", "reliable", "long clean record", upstream_ids=["source:a"]
            ),
        ],
        WeakestLink("model:trusted", "reliable", "no degraded link — and yet the claim is wrong"),
        final_grade="sahih",
    )
    print("\n  ^ This chain grades SAHIH and weakest_link reports 'reliable',")
    print("    yet model:trusted just lied for the first time.  Per-narrator")
    print("    grades cannot see a single-claim betrayal — that is what matn")
    print("    criticism, post-hoc audit, and period-sliced grades are for.")

    print("\n" + "=" * 70)
    print("Done.")
    print("=" * 70)


if __name__ == "__main__":
    main()
