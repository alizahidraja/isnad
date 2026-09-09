"""Tests for chain-scoped content grounding (#216).

Uses a tiny deterministic stub critic: the critic's own accuracy is not under
test here, the CHAIN-SCOPING logic and the default grounding policy are. The stub
says CONSISTENT iff the claim text appears verbatim in the corpus, CONTRADICTION
on an explicit "NOT <claim>" marker, else UNVERIFIABLE — enough to drive every
branch deterministically.
"""

from __future__ import annotations

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.chain_grounding import (
    DefaultGroundingPolicy,
    chain_scoped_corpus,
    check_chain_grounding,
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


def _check(claim, chain, off_chain_rows):
    return check_chain_grounding(claim, claim, chain, off_chain_rows, StubCritic())


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


# --- default grounding policy ----------------------------------------------


def test_legitimate_synthesis_grounded_upstream_is_not_flagged():
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
    res = _check(claim, chain, off_chain_rows=[])
    assert res.on_chain_verdict is ContentVerdict.CONSISTENT
    assert res.grounded_off_chain_only is False


def test_claim_grounded_only_off_chain_is_flagged():
    """The claim is grounded ONLY in a sibling branch's rows, never on its own
    chain — the grounding-gap signature."""
    claim = "R"
    chain = Chain([_link(0), _link(1, generative=True)])  # nothing on-chain grounds R
    res = _check(claim, chain, off_chain_rows=["R"])
    assert res.on_chain_verdict is not ContentVerdict.CONSISTENT
    assert res.off_chain_verdict is ContentVerdict.CONSISTENT
    assert res.grounded_off_chain_only is True


def test_grounded_both_on_and_off_chain_is_not_flagged():
    """If the row is legitimately on-chain, an off-chain copy is irrelevant —
    the claim rests on its own path."""
    claim = "R"
    chain = Chain([_link(0, rows=["R"]), _link(1, generative=True)])
    res = _check(claim, chain, off_chain_rows=["R"])
    assert res.on_chain_verdict is ContentVerdict.CONSISTENT
    assert res.grounded_off_chain_only is False


def test_grounded_nowhere_is_not_flagged_just_unverifiable():
    """A claim no corpus supports is the ordinary UNVERIFIABLE case, not a
    grounding gap — flagging requires positive off-chain grounding."""
    claim = "R"
    chain = Chain([_link(0), _link(1, generative=True)])
    res = _check(claim, chain, off_chain_rows=["something else"])
    assert res.on_chain_verdict is ContentVerdict.UNVERIFIABLE
    assert res.off_chain_verdict is ContentVerdict.UNVERIFIABLE
    assert res.grounded_off_chain_only is False


def test_on_chain_contradiction_is_not_masked_as_grounding_gap():
    """If the chain's own rows CONTRADICT the claim, that is not a grounding gap —
    the off-chain grounding does not paper over a live on-chain contradiction. The
    flag stays False; the contradiction surfaces via the normal critic path (the
    caller sees on_chain_verdict=CONTRADICTION)."""
    claim = "R"
    chain = Chain([_link(0, rows=["NOT R"]), _link(1, generative=True)])
    res = _check(claim, chain, off_chain_rows=["R"])
    assert res.on_chain_verdict is ContentVerdict.CONTRADICTION
    assert res.grounded_off_chain_only is False


def test_empty_off_chain_disables_the_flag():
    """off_chain_rows=[] means there is nothing to be grounded-off-chain in —
    the flag can never fire. Documented as a caller responsibility."""
    claim = "R"
    chain = Chain([_link(0), _link(1, generative=True)])
    res = _check(claim, chain, off_chain_rows=[])
    assert res.grounded_off_chain_only is False


def test_policy_is_swappable():
    """A caller can substitute its own GroundingPolicy; the default is used when
    none is given (both paths reach the same result here)."""
    claim = "R"
    chain = Chain([_link(0), _link(1, generative=True)])
    explicit = check_chain_grounding(
        claim, claim, chain, ["R"], StubCritic(), policy=DefaultGroundingPolicy()
    )
    implicit = _check(claim, chain, off_chain_rows=["R"])
    assert explicit == implicit


# --- serialization: retrieved_rows is runtime-only -------------------------


def test_retrieved_rows_is_a_runtime_field():
    link = _link(0, rows=["r1", "r2"])
    assert link.retrieved_rows == ["r1", "r2"]


def test_retrieved_rows_not_in_signed_serialization():
    """retrieved_rows must NOT appear in to_dict() — it is a runtime-only field.
    Emitting it would change the RFC 8785 canonical form of every signed audit
    record and pull raw row content into the signed/redact surface (#216 review)."""
    assert "retrieved_rows" not in _link(0, rows=["r1"]).to_dict()


def test_retrieved_rows_is_copied_not_aliased():
    """A later mutation of the caller's list must not change the link's rows —
    a live reference would make the audit hash nondeterministic."""
    src = ["r1"]
    link = _link(0, rows=src)
    src.append("r2")
    assert link.retrieved_rows == ["r1"]
