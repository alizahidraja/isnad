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

No proprietary data, no network, no model beyond the offline NLI weights the
existing HybridCritic already downloads. Deterministic (fixed seed).

Run:  python examples/numeric_critic_reproducer.py
"""

from __future__ import annotations

import random

from isnad.critics import EnsembleCritic, RecomputeCritic, best_available_critic


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

    nli = best_available_critic()  # HybridCritic (offline NLI) when available
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
            f"There are {total} items, and every one maps to a named category "
            f"with no blanks.",
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
        "- A2: recompute says CONSISTENT, and that is correct behavior: it\n"
        "  certifies the number (the total is right), not the claim. It is blind\n"
        "  to the false 'no blanks' qualifier, which is a non-numeric assertion.\n"
        "  The ensemble holds A2 only because a semantic critic contradicts it.\n"
        "  This is why recompute alone must never serve, and why the ensemble is\n"
        "  contradiction-priority.\n"
        "- A3: the superlative wrapper ('over N', 'dominates') is not an equality\n"
        "  assertion, so recompute defers rather than bless a coincidental match.\n"
        "- A4: recompute catches an inflated total (arithmetic contradiction) on\n"
        "  its own, no semantic critic needed.\n"
        "\n"
        "At this scale NLI contradicts everything, true or false, so its verdict\n"
        "carries no signal here. The safe ensemble preserves safety but cannot\n"
        "rescue A1 through a critic that contradicts everything.\n"
        "\n"
        "The fix is claim-type routing, with one caveat this demo makes concrete:\n"
        "routing CANNOT be 'numeric -> recompute only'. A2 proves it. Send A2 to\n"
        "recompute alone and it returns CONSISTENT -> serve, serving a false claim.\n"
        "Routing must still run a semantic critic on the non-numeric parts."
    )


if __name__ == "__main__":
    main()
