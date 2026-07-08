"""Tests for chain.py — chain construction and completeness enforcement.

Verifies paper §4.1 commitments:
- Every claim carries its full chain.
- Completeness (ittiṣāl) is enforced.
- Each link carries all required metadata.
"""

from isnad.core.chain import Chain, ChainLinkSpec, make_claim_id, normalize_claim_text
from isnad.types import ChainStatus, TransformType


class TestChainConstruction:
    def test_empty_chain_is_incomplete(self) -> None:
        chain = Chain()
        assert not chain.is_complete
        assert chain.chain_status == ChainStatus.MUNQATI

    def test_consecutive_chain_is_complete(self) -> None:
        chain = Chain(
            [
                ChainLinkSpec("source-A", step=0),
                ChainLinkSpec("scraper-v1", step=1),
                ChainLinkSpec("ingest-model", step=2),
            ]
        )
        assert chain.is_complete
        assert chain.chain_status == ChainStatus.COMPLETE

    def test_gap_makes_chain_munqati(self) -> None:
        """An incomplete chain (gap) is munqaṭiʿ — ittiṣāl failure."""
        chain = Chain(
            [
                ChainLinkSpec("source-A", step=0),
                ChainLinkSpec("ingest-model", step=2),  # gap at step 1
            ]
        )
        assert not chain.is_complete
        assert chain.chain_status == ChainStatus.MUNQATI

    def test_narrator_ids_are_ordered(self) -> None:
        chain = Chain(
            [
                ChainLinkSpec("source-B", step=0),
                ChainLinkSpec("scraper", step=1),
            ]
        )
        assert chain.narrator_ids == ["source-B", "scraper"]

    def test_links_carry_transform_type(self) -> None:
        chain = Chain(
            [
                ChainLinkSpec(
                    "scraper-v1",
                    step=0,
                    transform_type=TransformType.DESTRUCTIVE,
                ),
                ChainLinkSpec(
                    "ingest-model",
                    step=1,
                    transform_type=TransformType.GENERATIVE,
                ),
            ]
        )
        assert chain.links[0].transform_type == TransformType.DESTRUCTIVE
        assert chain.links[1].transform_type == TransformType.GENERATIVE

    def test_jsonb_serialization(self) -> None:
        chain = Chain(
            [
                ChainLinkSpec("src", step=0, version="1.0", trace_id="abc123"),
            ]
        )
        jsonb = chain.to_jsonb()
        assert len(jsonb) == 1
        assert jsonb[0]["narrator_id"] == "src"
        assert jsonb[0]["version"] == "1.0"
        assert jsonb[0]["trace_id"] == "abc123"


class TestClaimNormalization:
    def test_normalize_lowercases_and_strips(self) -> None:
        result = normalize_claim_text("  The Momentum of a Photon is p = h/λ  ")
        assert result == "the momentum of a photon is p = h/λ"

    def test_normalize_collapses_whitespace(self) -> None:
        result = normalize_claim_text("p  =   m   *   v")
        assert result == "p = m * v"

    def test_make_claim_id_is_deterministic(self) -> None:
        id1 = make_claim_id("p = mv")
        id2 = make_claim_id("p = mv")
        assert id1 == id2

    def test_different_claims_have_different_ids(self) -> None:
        id1 = make_claim_id("p = mv")
        id2 = make_claim_id("p = h/λ")
        assert id1 != id2
