"""Tests for chain-scoped content grounding / context-pollution detection (#216).

Uses a tiny deterministic stub critic: the critic's own accuracy is not under
test here, the CHAIN-SCOPING logic is. The stub says CONSISTENT iff the claim
text appears verbatim in the corpus, CONTRADICTION on an explicit "NOT <claim>"
marker, else UNVERIFIABLE — enough to drive every branch deterministically.
"""

from __future__ import annotations

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.chain_grounding import (
    chain_scoped_corpus,
    detect_context_pollution,
)
from isnad.types import ContentVerdict, TransformType


class StubCritic:
    """CONSISTENT iff claim is a verbatim row; CONTRADICTION on 'NOT <claim>'."""

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        if any(f"NOT {claim_text}" == row for row in corpus_claims):
            return ContentVerdict.CONTRADICTION
        if claim_text in corpus_claims:
            return ContentVerdict.CONSISTENT
        return ContentVerdict.UNVERIFIABLE


def _link(step: int, *, rows: list[str] | None = None, generative: bool = False) -> ChainLinkSpec:
    return ChainLinkSpec(
        narrator_id=f"agent{step}",
        step=step,
        transform_type=TransformType.GENERATIVE if generative else TransformType.PASS_THROUGH,
        retrieved_rows=rows,
    )


# --- chain_scoped_corpus ---------------------------------------------------


def test_corpus_is_union_of_link_rows_in_order():
    chain = Chain([_link(0, rows=["r1", "r2"]), _link(1, rows=["r3"], generative=True)])
    assert chain_scoped_corpus(chain) == ["r1", "r2", "r3"]


def test_corpus_dedupes_preserving_order():
    chain = Chain([_link(0, rows=["r1", "r2"]), _link(1, rows=["r2", "r1", "r4"])])
    assert chain_scoped_corpus(chain) == ["r1", "r2", "r4"]


def test_corpus_empty_when_no_link_retrieved_anything():
    chain = Chain([_link(0), _link(1, generative=True)])
    assert chain_scoped_corpus(chain) == []


# --- detect_context_pollution ----------------------------------------------


def test_legitimate_synthesis_grounded_upstream_is_not_polluted():
    """router -> retrieval(fetched R) -> synthesis(claim uses R). The synthesis
    link retrieves nothing; the claim is grounded by the UPSTREAM retrieval link
    on the same chain. This MUST NOT be flagged — the core false-positive a
    link-local check would make."""
    claim = "R"
    chain = Chain([
        _link(0),  # router, no retrieval
        _link(1, rows=["R"]),  # retrieval worker fetched R
        _link(2, generative=True),  # synthesis, fetched nothing, asserts R
    ])
    res = detect_context_pollution(claim, claim, chain, off_chain_rows=[], critic=StubCritic())
    assert res.on_chain_verdict is ContentVerdict.CONSISTENT
    assert res.polluted is False


def test_claim_grounded_only_off_chain_is_polluted():
    """The claim is grounded ONLY in a sibling branch's rows, never on its own
    chain — the context-pollution signature."""
    claim = "R"
    chain = Chain([_link(0), _link(1, generative=True)])  # nothing on-chain grounds R
    res = detect_context_pollution(claim, claim, chain, off_chain_rows=["R"], critic=StubCritic())
    assert res.on_chain_verdict is not ContentVerdict.CONSISTENT
    assert res.off_chain_verdict is ContentVerdict.CONSISTENT
    assert res.polluted is True


def test_grounded_both_on_and_off_chain_is_not_polluted():
    """If the row is legitimately on-chain, an off-chain copy is irrelevant —
    the claim rests on its own path."""
    claim = "R"
    chain = Chain([_link(0, rows=["R"]), _link(1, generative=True)])
    res = detect_context_pollution(claim, claim, chain, off_chain_rows=["R"], critic=StubCritic())
    assert res.on_chain_verdict is ContentVerdict.CONSISTENT
    assert res.polluted is False


def test_grounded_nowhere_is_not_pollution_just_unverifiable():
    """A claim no corpus supports is the ordinary UNVERIFIABLE case, not
    pollution — pollution requires positive off-chain grounding."""
    claim = "R"
    chain = Chain([_link(0), _link(1, generative=True)])
    res = detect_context_pollution(
        claim, claim, chain, off_chain_rows=["something else"], critic=StubCritic()
    )
    assert res.on_chain_verdict is ContentVerdict.UNVERIFIABLE
    assert res.off_chain_verdict is ContentVerdict.UNVERIFIABLE
    assert res.polluted is False


def test_on_chain_contradiction_is_not_masked_as_pollution():
    """If the chain's own rows CONTRADICT the claim, that is not pollution — the
    off-chain grounding does not paper over a live on-chain contradiction. The
    result stays not-polluted; the contradiction surfaces via the normal critic
    path (the caller sees on_chain_verdict=CONTRADICTION)."""
    claim = "R"
    chain = Chain([_link(0, rows=["NOT R"]), _link(1, generative=True)])
    res = detect_context_pollution(claim, claim, chain, off_chain_rows=["R"], critic=StubCritic())
    assert res.on_chain_verdict is ContentVerdict.CONTRADICTION
    assert res.polluted is False


# --- serialization round-trip ----------------------------------------------


def test_retrieved_rows_serialize_in_to_dict():
    link = _link(0, rows=["r1", "r2"])
    assert link.to_dict()["retrieved_rows"] == ["r1", "r2"]


def test_retrieved_rows_default_empty():
    assert _link(0).to_dict()["retrieved_rows"] == []
