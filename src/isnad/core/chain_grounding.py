"""Chain-scoped content grounding — the provenance-aware half of "is it grounded?" (#216).

The content critic answers "is this claim's information present in the retrieved
rows?" — but against ONE merged corpus for the whole claim. That merged pile has
lost track of *which link fetched which row*. In a multi-agent run
(router -> retrieval worker -> synthesis) a claim can look grounded because its
supporting row is *somewhere* in the pile, even when that row was fetched by a
different agent on a different branch that never fed this claim.

This module has two parts, deliberately separated (see #216 review):

- **The primitive** — ``chain_scoped_corpus(chain)`` — the rows that entered *on
  this claim's own chain*. Every link in a ``Chain`` is, by construction, an
  upstream hop on the claim's isnād (the chain is the ordered list of who handled
  the claim), so the union of every link's ``retrieved_rows`` is exactly "the
  evidence that traveled this claim's path". The scoping is CHAIN-level, not
  link-level: a synthesis link retrieves nothing itself and grounds in the
  *retrieval* link's rows by design — a link-local check would wrongly flag every
  legitimate synthesis. This is pure, deterministic chain topology.

- **A grounding POLICY** — ``GroundingPolicy`` (protocol) + ``ChainScopedGroundingPolicy``
  — decides what an on-chain/off-chain verdict *pair* means. This is a policy, not
  a primitive: the predicate "grounded off-chain only ⇒ flag" is a contested
  semantic choice (like ``ContentCritic`` or ``CorroborationPolicy``, it is a
  swap point, not a fact). It reports a **grounding gap** (``grounded_off_chain_only``),
  NOT proven contamination — the code cannot establish an adversary, only that the
  claim's support lies off its own chain. Naming it "pollution" would over-claim.

  ⚠️ The policy's flag is NOT yet measured against real critics. Offline critics
  run recall 0.12–0.76 and the LLM critic 39.1% false-consistent on §8 content
  corruption (#126); that error propagates into this flag. Per the "measure, don't
  assert" discipline (#215), an ``experiments/grounding_eval/`` harness should
  measure the flag's false-positive rate before it is wired into any decision.
  There is deliberately no route from this flag into the SERVE/REVIEW/QUARANTINE
  matrix yet — that mapping is a separate decision.

This module is pure and side-effect-free. Rows are opaque text; nothing here is
domain-specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from isnad.core.chain import Chain
from isnad.critics.base import ContentCritic
from isnad.types import ContentVerdict


def chain_scoped_corpus(chain: Chain) -> list[str]:
    """The rows retrieved by links *on this claim's own chain*, in chain order.

    Every link on a ``Chain`` is an upstream hop that fed the claim, so this is
    the evidence that legitimately grounds it. Deduplicated preserving first-seen
    order so a row retrieved by two links is not double-counted.
    Persistence limitation (#241): ``retrieved_rows`` is runtime-only (not in
    ``to_dict()``), so a chain reloaded from the database has empty
    ``retrieved_rows`` and this returns ``[]`` — persisted chains cannot be
    chain-scoped-graded until ``retrieved_rows`` is persisted.
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
class GroundingResult:
    """Outcome of a chain-scoped grounding check.

    ``grounded_off_chain_only`` is True for the flagged case: the claim is
    grounded in off-chain rows but NOT on its own chain — a **grounding gap**,
    not proven contamination. ``on_chain_verdict`` / ``off_chain_verdict`` are the
    raw critic verdicts against each corpus, kept so a caller can see *why* — never
    collapsed into a score.
    """

    grounded_off_chain_only: bool
    on_chain_verdict: ContentVerdict | None  # None = provenance unknown (not assessed)
    off_chain_verdict: ContentVerdict


class GroundingPolicy(Protocol):
    """Decides what an (on-chain, off-chain) verdict pair means — a swap point.

    Mirrors ``ContentCritic`` / ``CorroborationPolicy``: the framework ships a
    default, callers may substitute their own predicate. Kept out of the decision
    matrix by design — it produces evidence (a ``GroundingResult``), not an action.
    """

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        chain: Chain,
        off_chain_rows: list[str],
        critic: ContentCritic,
        domain: str = "general",
    ) -> GroundingResult: ...


class ChainScopedGroundingPolicy:
    """Default grounding policy: flag a claim grounded only off its own chain.

    ``grounded_off_chain_only`` is True iff the claim is CONSISTENT against the
    off-chain rows AND the chain-scoped verdict is UNVERIFIABLE — grounded off its
    own path, silent on it. Two cases are deliberately NOT flagged:

    - on-chain CONSISTENT — the claim rests on its own chain; an off-chain copy is
      irrelevant.
    - on-chain CONTRADICTION — a live contradiction is never papered over by an
      off-chain match; it dominates and surfaces through the normal critic path.
      Flagging a mere grounding gap here would understate a claim its own evidence
      refutes.

    A claim grounded nowhere (off-chain not CONSISTENT) is not flagged — that is
    the ordinary UNVERIFIABLE case, left to the content critic.

    Known edge cases (documented, not silently swallowed):

    - **Empty on-chain corpus** forces the on-chain verdict to UNVERIFIABLE, so a
      retrieval-less claim (e.g. common knowledge) that matches any off-chain row
      is flagged. That is intentional under this predicate — a claim with no
      on-chain evidence *is* grounded only off-chain — but at scale a caller that
      treats common-knowledge claims as legitimately unretrieved may want a
      stricter policy. This is exactly why the predicate is a swappable policy.
    - **The off_chain_rows split is caller-supplied and unverified.** Passing
      ``off_chain_rows=[]`` silently disables the flag; a spoofed split defeats it.
      This policy trusts its inputs — establishing the split honestly is the
      caller's (and a future retrieval-provenance spine's, #216) job.
    """

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        chain: Chain,
        off_chain_rows: list[str],
        critic: ContentCritic,
        domain: str = "general",
    ) -> GroundingResult:
        if not chain.retrieved_rows_known:
            # Provenance unknown (a DB-reloaded chain whose runtime-only rows were
            # stripped): never flag, and do not invoke the critic on an empty
            # on-chain corpus. See #241.
            off_verdict = (
                critic.evaluate(claim_text, normalized_claim, off_chain_rows, domain)
                if off_chain_rows
                else ContentVerdict.UNVERIFIABLE
            )
            return GroundingResult(
                grounded_off_chain_only=False,
                on_chain_verdict=None,
                off_chain_verdict=off_verdict,
            )

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
        flagged = (
            off_verdict is ContentVerdict.CONSISTENT and on_verdict is ContentVerdict.UNVERIFIABLE
        )
        return GroundingResult(
            grounded_off_chain_only=flagged,
            on_chain_verdict=on_verdict,
            off_chain_verdict=off_verdict,
        )


def evaluate_chain_grounding(
    claim_text: str,
    normalized_claim: str,
    chain: Chain,
    off_chain_rows: list[str],
    critic: ContentCritic,
    domain: str = "general",
    policy: GroundingPolicy | None = None,
) -> GroundingResult:
    """Convenience wrapper: run a ``GroundingPolicy`` (default if none given)."""
    policy = policy or ChainScopedGroundingPolicy()
    return policy.evaluate(claim_text, normalized_claim, chain, off_chain_rows, critic, domain)
