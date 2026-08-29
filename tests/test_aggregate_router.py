"""Acceptance battery for AggregateRouter, written before the router (test-first).

The router's job: when a claim is an aggregate ("how many rows, counts by
category") over a corpus of many "label: count" rows, the semantic critic goes
out of distribution and collapses to contradiction (issue #170). The router
gives the semantic critic a small summary slice instead of the raw hundreds of
rows, then runs the normal ensemble.

The one property that MUST hold, tested with REAL critics (not stubs, that is the
lesson from the PR #168 review): no false claim reaches a serve-class verdict
(CONSISTENT). A false claim may be held (UNVERIFIABLE) or caught (CONTRADICTION),
but never served.

These tests need sentence-transformers (real NLI). They are skipped if it is not
installed, so CI without the dep does not fail; run them locally to verify safety.
"""

import pytest

from isnad.critics.nli import _ensure_sentence_transformers
from isnad.types import ContentVerdict

pytestmark = pytest.mark.skipif(
    not _ensure_sentence_transformers(),
    reason="needs sentence-transformers for the real NLI critic",
)

CONSISTENT = ContentVerdict.CONSISTENT
CONTRADICTION = ContentVerdict.CONTRADICTION
UNVERIFIABLE = ContentVerdict.UNVERIFIABLE


def _big_numeric_corpus(n=300, blank=470):
    """The shape that makes NLI collapse: hundreds of 'label: count' rows."""
    import random

    rng = random.Random(7)
    counts = {f"category_{i:03d}": rng.randint(1, 25) for i in range(n)}
    total = sum(counts.values()) + blank
    rows = [f"{k}: {v} items" for k, v in counts.items()]
    rows.append(f"rows with no category label: {blank}")
    return rows, total, blank


def _router():
    from isnad.critics import AggregateRouter, EnsembleCritic, HybridCritic, RecomputeCritic

    ensemble = EnsembleCritic(semantic=HybridCritic(), deterministic=RecomputeCritic())
    return AggregateRouter(inner=ensemble)


# --- The safety battery: false claims must NEVER be served -------------------

FALSE_CLAIMS = [
    # correct number, false qualifier the summary refutes (470 ARE blank)
    "There are {total} rows and none of them are blank.",
    "There are {total} rows in total, and none are blank.",
    "There are {total} rows, all fully annotated.",
    "There are {total} rows with no missing values.",
    # correct number, false qualifier the summary is SILENT about (orthogonal):
    # nothing can refute these, so safety rests on the semantic critic not
    # returning CONSISTENT. This is the decisive set.
    "There are {total} rows in total, all fully validated.",
    "There are {total} rows in total, sorted ascending and deduplicated.",
    "There are {total} rows, every one reviewed by a human.",
    # a wrong number entirely
    "There are 999999 rows in total.",
]


@pytest.mark.parametrize("template", FALSE_CLAIMS)
def test_false_claim_never_served(template):
    rows, total, blank = _big_numeric_corpus()
    claim = template.format(total=total)
    verdict = _router().evaluate(claim, claim, rows)
    assert verdict != CONSISTENT, f"false claim reached serve: {claim!r} -> {verdict}"


def test_wrong_number_is_contradiction():
    rows, total, blank = _big_numeric_corpus()
    claim = "There are 999999 rows in total."
    assert _router().evaluate(claim, claim, rows) == CONTRADICTION


# --- The benefit: verdicts are meaningful, not NLI noise ---------------------


def test_router_removes_nli_noise_vs_raw_corpus():
    """On the raw 300-row corpus the ensemble returns CONTRADICTION for a true
    aggregate (NLI collapse). The router, by scoping the semantic critic to a
    summary, must NOT return that spurious CONTRADICTION for a true claim."""
    from isnad.critics import EnsembleCritic, HybridCritic, RecomputeCritic

    rows, total, blank = _big_numeric_corpus()
    true_claim = f"There are {total} rows in total; {blank} have no category label."

    raw = EnsembleCritic(semantic=HybridCritic(), deterministic=RecomputeCritic())
    raw_verdict = raw.evaluate(true_claim, true_claim, rows)
    routed_verdict = _router().evaluate(true_claim, true_claim, rows)

    # the raw path collapses to contradiction; the routed path must not repeat it
    assert raw_verdict == CONTRADICTION  # documents the #170 collapse
    assert routed_verdict != CONTRADICTION  # router removed the spurious contradiction


# --- Pass-through: non-aggregate claims are untouched ------------------------


def test_non_aggregate_claim_passes_through_unchanged():
    """A claim over a non-numeric corpus is not an aggregate; the router must
    delegate to the inner critic without altering the corpus."""
    from isnad.critics import AggregateRouter, HybridCritic

    inner = HybridCritic()
    router = AggregateRouter(inner=inner)
    claim = "force equals mass times acceleration"
    corpus = ["force equals mass times acceleration"]
    assert router.evaluate(claim, claim, corpus) == inner.evaluate(claim, claim, corpus)
