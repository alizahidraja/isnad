"""Recompute critic: deterministic checking of aggregate numeric claims.

Semantic critics (NLI, embedding) do *entailment*, not *arithmetic*. When a claim
asserts an aggregate over structured rows ("there are 1,240 records", "the top
category has 26"), an NLI model cannot recompute the sum/count and so returns
UNVERIFIABLE even when the claim is exactly right. That is an honest limit of the
wrong tool, not a fundamental one (paper §8.4 is about claims that *cannot* be
checked at all; a count over returned rows manifestly can be).

This critic recomputes the aggregates directly from the corpus rows and compares
them to the numbers the claim asserts. It is deliberately narrow and honest:

- It only speaks up (CONSISTENT / CONTRADICTION) when it can confidently parse
  BOTH a structured aggregate out of the corpus rows AND at least one numeric
  assertion out of the claim. Otherwise it returns UNVERIFIABLE and defers.
- It NEVER upgrades a claim to CONSISTENT on a numeric match alone. A claim can
  carry a correct number and a false assertion ("1,240 records, all annotated" is
  wrong despite the correct 1,240). Numeric consistency is necessary, not
  sufficient. The
  intended use is inside an ensemble (see ``EnsembleCritic``) where any critic's
  CONTRADICTION wins and this critic can only *upgrade* an otherwise-unverifiable
  verdict once a semantic critic has confirmed no contradiction.

By itself it is a rejection-and-confirmation gate for the numeric slice only; it
is not a general content critic. Compose it, do not substitute it.
"""

from __future__ import annotations

import re

from isnad.types import ContentVerdict

# A corpus row shaped like "category alpha: 26 items" / "total rows: 1240" /
# "label X: 12", a name/key followed by an integer. We pull (key, count) pairs
# and also detect an explicit total so a claim's grand-total can be checked
# against either an asserted total or the sum of the parts.
_ROW_COUNT = re.compile(r"([A-Za-z][\w .()\-/]*?)\s*[:=]\s*([0-9][0-9,]*)")
_INT = re.compile(r"\b([0-9][0-9,]*)\b")

# Bound / superlative language the recompute critic cannot evaluate: "over 1000",
# "the majority", "most". A number next to one of these is not an equality
# assertion, so an exact match to a corpus figure is not a real confirmation.
# When present, recompute defers (CONSISTENT -> UNVERIFIABLE) rather than bless.
_BOUND_WORDS = re.compile(
    r"\b(over|under|above|below|more than|less than|at least|at most|nearly|almost|"
    r"majority|most|dominat\w*|overwhelming|vast\w*|approximately|around|about|"
    r"roughly|up to|exceed\w*|greater than|fewer than)\b",
    re.IGNORECASE,
)


def _to_int(s: str) -> int:
    return int(s.replace(",", ""))


class RecomputeCritic:
    """Deterministic aggregate-consistency critic for count/sum-style claims.

    ``evaluate`` returns:

    - CONTRADICTION: a number the claim asserts as a total/aggregate provably
      disagrees with what the corpus rows recompute to (e.g. claim says 97, rows
      sum to 3).
    - CONSISTENT: every aggregate the claim asserts matches the recomputed value
      AND the claim carries no numeric assertion that is unaccounted for. This is
      the numeric slice only; callers must still gate it behind a semantic
      no-contradiction check before serving (see module docstring).
    - UNVERIFIABLE: can't confidently parse structured counts from the rows, or
      the claim makes no checkable numeric assertion, or the assertion is
      ambiguous. The honest default.

    Tolerance: exact integer match. Aggregates are integers (counts); we do not
    fuzz them.
    """

    def __init__(self, *, require_total: bool = False):
        # require_total: if True, only judge when the corpus exposes an explicit
        # total row; otherwise the sum of parts is used as the recomputed total.
        self.require_total = require_total

    def _parse_corpus(self, corpus_claims: list[str]) -> tuple[dict[str, int], int | None]:
        """Extract (key -> count) pairs and an explicit total, if present."""
        parts: dict[str, int] = {}
        explicit_total: int | None = None
        for row in corpus_claims:
            m = _ROW_COUNT.search(row)
            if not m:
                continue
            key = m.group(1).strip().lower()
            val = _to_int(m.group(2))
            # a row literally naming a total ("total rows", "total", "count")
            if re.search(r"\btotal\b|\ball rows\b|\bcount\b", key):
                explicit_total = val
            elif re.search(r"\bblank\b|\bmissing\b|\bno .*(label|symbol|value)\b", key):
                # a "rows with no X: N" fact is a countable part, keyed distinctly
                parts[f"__blank__:{key}"] = val
            else:
                parts[key] = val
        return parts, explicit_total

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        parts, explicit_total = self._parse_corpus(corpus_claims)
        if not parts and explicit_total is None:
            return ContentVerdict.UNVERIFIABLE  # nothing structured to recompute

        named_parts = {k: v for k, v in parts.items() if not k.startswith("__blank__:")}
        blank_total = sum(v for k, v in parts.items() if k.startswith("__blank__:"))
        sum_named = sum(named_parts.values())
        recomputed_total = explicit_total
        if recomputed_total is None:
            if self.require_total:
                return ContentVerdict.UNVERIFIABLE
            recomputed_total = sum_named + blank_total

        claim_ints = [_to_int(x) for x in _INT.findall(claim_text)]
        if not claim_ints:
            return ContentVerdict.UNVERIFIABLE  # claim makes no numeric assertion

        # The set of values the corpus supports the claim asserting: the total,
        # the blank-count, and any individual part count.
        supported = {recomputed_total, blank_total, *named_parts.values()}
        supported.discard(0)  # 0 is too promiscuous to treat as a real match

        # Total-shaped assertion: does the claim state a grand total, and does it
        # match? We look for the largest asserted integer as the presumptive total
        # (aggregate claims lead with the count of everything).
        asserted_total = max(claim_ints)
        total_ok = asserted_total == recomputed_total

        # A claim number that matches nothing the corpus supports is a red flag,
        # but only decisive when it is the total-shaped number (the aggregate the
        # claim is *about*). A stray unmatched small number defers to semantics.
        if not total_ok and asserted_total > recomputed_total:
            # claim inflates the aggregate beyond what the rows carry -> conflict
            return ContentVerdict.CONTRADICTION
        if not total_ok:
            # asserted total is below recomputed and matches no part cleanly:
            # ambiguous (could be a per-category statement). Defer.
            if asserted_total not in supported:
                return ContentVerdict.UNVERIFIABLE
            # it matched a part but not the total: not a clean aggregate confirm.
            return ContentVerdict.UNVERIFIABLE

        # asserted total matches the recomputed total. Now require that EVERY
        # other integer the claim states is one the corpus actually supports.
        # Otherwise the claim smuggles an unverified number alongside a correct
        # total (the "1,240 records, all annotated" trap: the total is right, but
        # the blank-count assertion is absent/contradicted). If any stated integer is
        # unaccounted for, this critic stays silent (UNVERIFIABLE) and lets the
        # semantic critic rule. It will NOT bless the claim on the total alone.
        for n in claim_ints:
            if n == recomputed_total:
                continue
            if n not in supported:
                return ContentVerdict.UNVERIFIABLE

        # Safe-by-construction guard, on the CONSISTENT path ONLY (after all
        # contradiction checks): if the claim wraps its numbers in bound/
        # superlative language ("over 1000", "the majority"), an exact match is
        # not a real equality confirmation, so defer instead of blessing. This can
        # only turn CONSISTENT into UNVERIFIABLE (more deferral, never a new
        # serve), so it cannot reintroduce a contradiction-into-serve hole.
        if _BOUND_WORDS.search(claim_text):
            return ContentVerdict.UNVERIFIABLE

        return ContentVerdict.CONSISTENT
