"""Chain-scoped content grounding — the provenance-aware half of "is it grounded?" (#216).

The content critic answers "is this claim's information present in the retrieved
rows?" — but against ONE merged corpus for the whole claim. That merged pile has
lost track of *which link fetched which row*. In a multi-agent run
(router -> retrieval worker -> synthesis) a claim can look grounded because its
supporting row is *somewhere* in the pile, even when that row was fetched by a
different agent on a different branch that never fed this claim. That is context
pollution, and a chain-blind grounding check cannot see it.

This module adds the missing, provenance-aware notion:

- ``chain_scoped_corpus(chain)`` — the rows that entered *on this claim's own
  chain*. Every link in a ``Chain`` is, by construction, an upstream hop on the
  claim's isnād (the chain is the ordered list of who handled the claim), so the
  union of every link's ``retrieved_rows`` is exactly "the evidence that traveled
  this claim's path". The check is CHAIN-scoped, not link-scoped: a synthesis
  link retrieves nothing itself and grounds in the *retrieval* link's rows by
  design — a link-local check would wrongly flag every legitimate synthesis.

- ``detect_context_pollution(...)`` — flags the case the feature exists for: the
  claim is grounded ONLY in off-chain rows (rows that never entered on its chain).
  It is CONSISTENT against the off-chain corpus but NOT against the chain-scoped
  corpus. That gap is the pollution signature. A claim already grounded on its own
  chain is never flagged, and a claim grounded nowhere is left to the ordinary
  content critic (UNVERIFIABLE), not called pollution.

This module is pure and side-effect-free. Rows are opaque text; nothing here is
domain-specific.
"""

from __future__ import annotations

from dataclasses import dataclass

from isnad.core.chain import Chain
from isnad.critics.base import ContentCritic
from isnad.types import ContentVerdict


def chain_scoped_corpus(chain: Chain) -> list[str]:
    """The rows retrieved by links *on this claim's own chain*, in chain order.

    Every link on a ``Chain`` is an upstream hop that fed the claim, so this is
    the evidence that legitimately grounds it. Deduplicated preserving first-seen
    order so a row retrieved by two links is not double-counted.
    """
    seen: set[str] = set()
    out: list[str] = []
    for link in chain.links:
        for row in link.retrieved_rows:
            if row not in seen:
                seen.add(row)
                out.append(row)
    return out


@dataclass(frozen=True)
class PollutionResult:
    """Outcome of a chain-scoped grounding check.

    ``polluted`` is True only for the specific, dangerous case: the claim is
    grounded off-chain but not on-chain. ``on_chain_verdict`` /
    ``off_chain_verdict`` are the raw critic verdicts against each corpus, kept
    so a caller can see *why* — never collapsed into a score.
    """

    polluted: bool
    on_chain_verdict: ContentVerdict
    off_chain_verdict: ContentVerdict


def detect_context_pollution(
    claim_text: str,
    normalized_claim: str,
    chain: Chain,
    off_chain_rows: list[str],
    critic: ContentCritic,
    domain: str = "",
) -> PollutionResult:
    """Flag a claim grounded only in rows that never entered on its own chain.

    Args:
        claim_text / normalized_claim: the claim under test.
        chain: the claim's transmission chain; its links carry ``retrieved_rows``.
        off_chain_rows: rows present in the wider run but NOT on this claim's
            chain (e.g. what sibling agents/branches retrieved). The caller owns
            the split — this module does not guess which rows are off-chain.
        critic: any ContentCritic; grounding == a CONSISTENT verdict.
        domain: passed through to the critic.

    Returns a ``PollutionResult``. ``polluted`` is True iff the claim is
    CONSISTENT against the off-chain rows AND the chain-scoped verdict is
    UNVERIFIABLE — grounded off its own path, silent on it. Two cases are
    deliberately NOT pollution:

    - on-chain CONSISTENT — the claim rests on its own chain; an off-chain copy
      is irrelevant.
    - on-chain CONTRADICTION — a live contradiction is never papered over by an
      off-chain match; it dominates and surfaces through the normal critic path.
      Reporting "polluted" here would understate a claim its own evidence
      refutes.

    A claim grounded nowhere (off-chain not CONSISTENT) is not pollution, just
    unverifiable.
    """
    on_chain = chain_scoped_corpus(chain)
    on_verdict = (
        critic.evaluate(claim_text, normalized_claim, on_chain, domain)
        if on_chain
        else ContentVerdict.UNVERIFIABLE
    )
    off_verdict = (
        critic.evaluate(claim_text, normalized_claim, off_chain_rows, domain)
        if off_chain_rows
        else ContentVerdict.UNVERIFIABLE
    )

    polluted = (
        off_verdict is ContentVerdict.CONSISTENT and on_verdict is ContentVerdict.UNVERIFIABLE
    )
    return PollutionResult(
        polluted=polluted,
        on_chain_verdict=on_verdict,
        off_chain_verdict=off_verdict,
    )
