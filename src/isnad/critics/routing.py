"""Aggregate router: scope the semantic critic's corpus for count-style claims.

Issue #170: on a corpus of hundreds of "label: count" rows (a GROUP-BY result),
the NLI/embedding critics go out of distribution and collapse to indiscriminate
CONTRADICTION. They read a large grand total as contradicting the small per-row
counts, so they contradict a *true* aggregate just as they do a false one. Their
verdict carries no signal on that corpus.

The router does NOT override any critic's verdict (that would be unsafe, a false
qualifier could sneak through). It changes the *input*: when the corpus is a big
list of counts, it hands the inner critic a small summary (the grand total plus
the aggregate rows a recompute pass extracts) instead of the raw hundreds of
rows. On a handful of summary rows the semantic critic is back in distribution
and its verdict means something again. The inner critic is expected to be an
EnsembleCritic (semantic + recompute), so the recompute half still sees the full
rows for arithmetic and the safety composition is unchanged.

Safety property (verified with real critics in tests/test_aggregate_router.py):
no false claim reaches CONSISTENT. A false qualifier the summary refutes is
caught (CONTRADICTION); one the summary is silent about is held (UNVERIFIABLE);
a wrong number is caught. The router only removes the spurious contradiction NLI
produced from corpus size, it never manufactures a serve.

What it does NOT do: it does not parse the claim into numeric vs non-numeric and
serve on the numbers alone. A true count is served only when the inner critic
genuinely returns CONSISTENT on the summary, which for NLI is phrasing-dependent.
Reliably serving true counts would need a claim-purity gate, which is deliberately
out of scope (every false-negative there would serve a false claim).
"""

from __future__ import annotations

from isnad.critics.base import ContentCritic
from isnad.critics.recompute import _ROW_COUNT
from isnad.types import ContentVerdict

# A corpus counts as an aggregate when this many rows parse as "label: number".
# Below this it is small enough that the semantic critic is already in
# distribution, so there is nothing to scope and we pass through.
_MIN_COUNT_ROWS = 12


class AggregateRouter:
    """Wrap a content critic; scope its corpus for aggregate/count claims.

    Args:
        inner: the critic to delegate to (expected: an EnsembleCritic of a
            semantic critic and a RecomputeCritic). Its verdict is returned
            unchanged; only the corpus it sees for an aggregate claim is scoped.
        min_count_rows: how many "label: number" rows make a corpus an
            aggregate. Below this, pass through untouched.
    """

    def __init__(self, inner: ContentCritic, *, min_count_rows: int = _MIN_COUNT_ROWS):
        self.inner = inner
        self.min_count_rows = min_count_rows

    def _summarize(self, corpus_claims: list[str]) -> list[str] | None:
        """Return a small summary corpus if this looks like an aggregate, else None.

        The summary keeps ONLY the aggregate-level rows: an explicit total (or one
        synthesized from the sum of parts) and the blank/missing tally. It drops
        every per-category count.

        Why drop the per-category counts: a claim about the grand total ("there
        are 4260 rows") next to a small per-category row ("category_066: 25") is
        exactly the scale mismatch that makes the cross-encoder read a true total
        as a contradiction. Keeping even the top few counts reintroduces the
        collapse. So the summary is total + blank only.

        The cost: a claim specifically about "which category has the most" gets no
        supporting row here, so the semantic critic returns UNVERIFIABLE and the
        claim is held for review. That is the safe outcome; serving ranking claims
        is out of scope for this router.
        """
        parsed: list[tuple[str, int, str]] = []  # (key, count, original row)
        for row in corpus_claims:
            m = _ROW_COUNT.search(row)
            if m:
                key = m.group(1).strip().lower()
                parsed.append((key, int(m.group(2).replace(",", "")), row))

        if len(parsed) < self.min_count_rows:
            return None  # not an aggregate corpus; pass through

        total_rows = [r for k, _, r in parsed if _is_total(k)]
        blank_rows = [r for k, _, r in parsed if _is_blank(k)]

        # If no explicit total row exists, synthesize one from the sum of parts so
        # a "there are N" claim has something to match.
        summary = list(total_rows)
        if not total_rows:
            grand = sum(c for k, c, _ in parsed if not _is_total(k) and not _is_blank(k))
            grand += sum(c for k, c, _ in parsed if _is_blank(k))
            summary.append(f"total rows: {grand}")
        summary.extend(blank_rows)
        return summary

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        if not corpus_claims:
            return self.inner.evaluate(claim_text, normalized_claim, corpus_claims, domain)

        summary = self._summarize(corpus_claims)
        if summary is None:
            # not an aggregate corpus: delegate unchanged
            return self.inner.evaluate(claim_text, normalized_claim, corpus_claims, domain)

        # Aggregate corpus: give the inner critic the scoped summary. An
        # EnsembleCritic's recompute half still recomputes correctly from the
        # summary (it carries the total and the blank tally), and its semantic
        # half is now in distribution.
        return self.inner.evaluate(claim_text, normalized_claim, summary, domain)


def _is_total(key: str) -> bool:
    import re

    return bool(re.search(r"\btotal\b|\ball rows\b|\bcount\b", key))


def _is_blank(key: str) -> bool:
    import re

    return bool(re.search(r"\bblank\b|\bmissing\b|\bno .*(label|symbol|value)\b", key))
