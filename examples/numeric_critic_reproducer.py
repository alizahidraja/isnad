"""Why NLI is the wrong critic for numeric aggregates, and RecomputeCritic fixes it.

This is a self-contained, deterministic reproducer. It builds a synthetic
GROUP-BY result (a few hundred "category: count" rows plus a blank tally, the
shape a real aggregation query returns) and grades three answers about it with
three critics: the offline NLI critic, the new RecomputeCritic, and the
contradiction-priority EnsembleCritic of the two.

It shows two things:

1. RecomputeCritic verifies a correct aggregate that NLI cannot. Summing a few
   hundred rows is arithmetic, not entailment, so the NLI cross-encoder returns
   UNVERIFIABLE (or worse, see below) even when the answer is exactly right.
   A count over returned rows is checkable, so this is NOT the section 8.4
   boundary. It is the wrong tool for a decidable claim.

2. At this scale the NLI critic degrades to indiscriminate CONTRADICTION. On a
   corpus of hundreds of small per-row counts it reads a large grand total as
   contradicting the small numbers, and returns CONTRADICTION for a true
   aggregate just as it does for a false one. Its verdict carries no signal here.
   The EnsembleCritic is contradiction-priority for safety (a correct number can
   sit inside a false claim), so it cannot rescue the true answer through a
   critic that contradicts everything. The fix is claim-type routing, but with a
   caveat this demo makes concrete (see answer A2): routing cannot be "numeric ->
   recompute only", because a claim with a correct number and a false non-numeric
   qualifier would then be served. Routing must still run a semantic critic on
   the non-numeric parts.

It also demonstrates the safety rule a PR #168 review surfaced: when a claim
pairs a correct number with a false non-numeric qualifier ("510 rows, none
blank"), a semantic critic that cannot see the falsehood returns UNVERIFIABLE,
and the ensemble must still refuse to serve. An upgrade to CONSISTENT requires
the semantic critic to actively confirm, not merely stay silent.

Requires sentence-transformers (for the NLI critic). It is pinned on purpose: the
demo is about NLI behavior, so it fails loudly if the dependency is missing
rather than silently falling back to a different critic. No proprietary data, no
network beyond the one-time model download. Deterministic (fixed seed).

Run:  python examples/numeric_critic_reproducer.py
"""

from __future__ import annotations

import random
import sys

from isnad.critics import EnsembleCritic, HybridCritic, RecomputeCritic


def build_corpus(n_categories: int = 300, blank: int = 470) -> tuple[list[str], int, int]:
    """A synthetic GROUP-BY result: one row per category, plus a blank tally.

    Long-tailed small counts and a large blank bucket, the shape a real
    'count records, group by category' query returns. Fixed seed -> reproducible.
    """
    rng = random.Random(7)
    counts = {f"category_{i:03d}": rng.randint(1, 25) for i in range(n_categories)}
    total = sum(counts.values()) + blank
    rows = [f"{name}: {c} items" for name, c in counts.items()]
    rows.append(f"rows with no category label: {blank}")
    return rows, total, blank


def main() -> None:
    rows, total, blank = build_corpus()

    # Pin the NLI critic explicitly. This demo is about NLI's behavior on numeric
    # corpora, so it must run the actual NLI critic, not whatever
    # best_available_critic() falls back to. Without sentence-transformers the
    # HybridCritic silently degrades to UNVERIFIABLE, which is NOT the
    # CONTRADICTION this demo (and issue #170) is about. Check the dependency up
    # front and fail loudly, so nobody sees the wrong result and mistrusts #170.
    from isnad.critics.nli import _ensure_sentence_transformers

    if not _ensure_sentence_transformers():
        print(
            "This demo needs the NLI critic (HybridCritic), which requires "
            "sentence-transformers.\n"
            "Install it with:  pip install sentence-transformers\n"
            "(Without it, HybridCritic returns UNVERIFIABLE instead of the "
            "CONTRADICTION this demo is about, so the demo would be misleading.)",
            file=sys.stderr,
        )
        raise SystemExit(1)

    nli = HybridCritic()
    recompute = RecomputeCritic()
    ensemble = EnsembleCritic(semantic=nli, deterministic=recompute)

    print(f"semantic critic : {type(nli).__name__}")
    print(f"corpus          : {len(rows) - 1} category rows + 1 blank tally")
    print(f"true total      : {total}   (blank rows: {blank})\n")

    # Four answers about the same corpus.
    answers = [
        (
            "A1 true aggregate",
            f"There are {total} items in total; {blank} have no category label.",
        ),
        (
            "A2 correct number, false qualifier",
            f"There are {total} items, and every one maps to a named category with no blanks.",
        ),
        (
            "A3 superlative wrapper",
            f"One category dominates with over {total} items overwhelming the set.",
        ),
        (
            "A4 inflated total",
            f"There are {total + 5000} items in total.",
        ),
    ]

    header = f"{'answer':<38}{'NLI':<15}{'RECOMPUTE':<15}{'ENSEMBLE':<15}"
    print(header)
    print("-" * len(header))
    for tag, ans in answers:
        v_nli = nli.evaluate(ans, ans, rows).value
        v_rec = recompute.evaluate(ans, ans, rows).value
        v_ens = ensemble.evaluate(ans, ans, rows).value
        print(f"{tag:<38}{v_nli:<15}{v_rec:<15}{v_ens:<15}")

    print(
        "\nRead:\n"
        "- A1: RecomputeCritic confirms the true aggregate that NLI cannot.\n"
        "- A3: the superlative wrapper ('over N', 'dominates') is not an equality\n"
        "  assertion, so recompute defers rather than bless a coincidental match.\n"
        "- A4: recompute catches an inflated total (arithmetic contradiction) on\n"
        "  its own, no semantic critic needed.\n"
        "\n"
        "At this scale NLI contradicts everything, true or false (see the NLI\n"
        "column). Its verdict carries no signal on a numeric corpus, which is the\n"
        "point of issue #170. So in THIS run the ensemble is contradiction on\n"
        "every row: rule 1 (any contradiction wins) fires on NLI's noise.\n"
        "\n"
        "The confirm-to-upgrade safety rule is not visible above, because it only\n"
        "matters when the semantic critic stays SILENT (unverifiable) rather than\n"
        "contradicting. The next block shows it with a critic that does stay\n"
        "silent."
    )

    # Second demonstration: the safety rule that a PR #168 review surfaced.
    # A claim can pair a correct number with a false NON-numeric qualifier. A
    # semantic critic that cannot see the falsehood returns UNVERIFIABLE (silent),
    # not CONTRADICTION. The ensemble must still NOT serve it. We use a real
    # EmbeddingCritic (TF-IDF) here precisely because it returns UNVERIFIABLE on
    # the false qualifier, so the confirm-to-upgrade rule is what keeps it safe.
    from isnad.critics import EmbeddingCritic

    small_rows = [
        "category alpha: 26 items",
        "category beta: 14 items",
        "rows with no category label: 470",
        "total rows: 510",
    ]
    false_claim = "There are 510 rows total, and none of them are blank."
    emb = EmbeddingCritic()
    emb_ens = EnsembleCritic(semantic=emb, deterministic=recompute)

    print("\nSafety rule (correct number, false non-numeric qualifier):")
    print(f"  claim           : {false_claim!r}")
    print("  truth           : 470 of the 510 rows ARE blank, so the claim is false")
    print(
        f"  EmbeddingCritic : {emb.evaluate(false_claim, false_claim, small_rows).value}"
        "   (cannot see the falsehood, stays silent)"
    )
    print(
        f"  RecomputeCritic : {recompute.evaluate(false_claim, false_claim, small_rows).value}"
        "      (the number 510 is right)"
    )
    print(
        f"  ENSEMBLE        : {emb_ens.evaluate(false_claim, false_claim, small_rows).value}"
        "   (NOT consistent, so NOT served)"
    )
    print(
        "\n  The number matches, but the ensemble refuses to bless the claim on the\n"
        "  number alone: an upgrade to CONSISTENT requires the semantic critic to\n"
        "  actively confirm, not merely stay silent. This is the fix from the PR\n"
        "  review. Without it, this false claim would be served.\n"
        "\n"
        "The fix for the NLI collapse itself is claim-type routing, with one\n"
        "caveat this same example makes concrete: routing CANNOT be 'numeric ->\n"
        "recompute only', because recompute alone returns CONSISTENT here and would\n"
        "serve the false claim. Routing must still run a semantic critic on the\n"
        "non-numeric parts."
    )


if __name__ == "__main__":
    main()
