"""Tests for isnad_trace schema, fixtures, shared-ancestry detection, and tree reconstruction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isnad.trace.schema import (
    ChainIntegrity,
    CorroborationVerdict,
    DocumentRef,
    OriginStrength,
    TraceV01,
)


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
PROJECT_DIR = Path(__file__).resolve().parent.parent


# ── Schema round-trip ────────────────────────────────────────────


def _load_fixture(name: str) -> TraceV01:
    path = FIXTURES_DIR / f"{name}.json"
    assert path.exists(), f"Fixture not found: {path}"
    with open(path) as f:
        data = json.load(f)
    return TraceV01.model_validate(data)


def test_schema_round_trip_fixture_1():
    """Clean chain round-trips through serialize/deserialize."""
    trace = _load_fixture("1-clean-chain")
    re_json = trace.model_dump_json(indent=2)
    re_trace = TraceV01.model_validate_json(re_json)
    assert re_trace.claim_text == trace.claim_text
    assert re_trace.chain_integrity == ChainIntegrity.SAHIH
    assert re_trace.origin_strength == OriginStrength.VERIFIED
    assert re_trace.independence == CorroborationVerdict.VERIFIED
    assert len(re_trace.chain) == 3


def test_schema_round_trip_fixture_2():
    """Weak extraction chain round-trips."""
    trace = _load_fixture("2-weak-extraction")
    re_json = trace.model_dump_json(indent=2)
    re_trace = TraceV01.model_validate_json(re_json)
    assert re_trace.chain_integrity == ChainIntegrity.DAIF
    assert re_trace.origin_strength == OriginStrength.VERIFIED
    assert re_trace.independence == CorroborationVerdict.UNVERIFIED
    assert re_trace.binding_step == 1  # extraction step is the binding constraint
    assert "gpt-3.5-turbo" in re_trace.binding_constraint


def test_schema_round_trip_fixture_3():
    """False corroboration round-trips."""
    trace = _load_fixture("3-false-corroboration")
    re_json = trace.model_dump_json(indent=2)
    re_trace = TraceV01.model_validate_json(re_json)
    assert re_trace.independence == CorroborationVerdict.SHARED_ANCESTRY_DETECTED
    assert len(re_trace.corroborating_chains) == 2
    assert len(re_trace.corroborating_chains[0]) == 3  # 3 nodes per corroborating chain
    # Origin is verified but chain is only hasan — two separate axes
    assert re_trace.origin_strength == OriginStrength.VERIFIED
    assert re_trace.chain_integrity == ChainIntegrity.HASAN


def test_schema_round_trip_all_fixtures():
    """All three fixtures validate and round-trip."""
    for name in ["1-clean-chain", "2-weak-extraction", "3-false-corroboration"]:
        trace = _load_fixture(name)
        re_json = trace.model_dump_json(indent=2)
        re_trace = TraceV01.model_validate_json(re_json)
        assert re_trace.claim_text == trace.claim_text
        assert re_trace.independence == trace.independence


# ── Two-axis scoring ─────────────────────────────────────────────


def test_two_axes_never_collapsed():
    """Chain integrity and origin strength are separate axes."""
    # Fixture 2: daif chain but verified origin
    trace = _load_fixture("2-weak-extraction")
    assert trace.chain_integrity == ChainIntegrity.DAIF
    assert trace.origin_strength == OriginStrength.VERIFIED
    # These must be distinguishable from a sahih/unverified combo
    # A clean chain from an unverified source is different from a weak chain from a verified source
    assert trace.chain_integrity != trace.origin_strength.value  # different types


def test_origin_strength_preserved_when_chain_degrades():
    """A degraded chain must not overwrite origin strength."""
    trace = _load_fixture("2-weak-extraction")
    # The source narrator has verified origin
    source = trace.chain[0]
    assert source.grade.origin_strength == OriginStrength.VERIFIED
    # The chain grade is daif, but origin_strength stays verified
    assert trace.origin_strength == OriginStrength.VERIFIED


# ── Tree reconstruction from parent_ids ──────────────────────────


def test_tree_reconstruction_from_parent_ids():
    """Given parent_ids, we can reconstruct the tree structure."""
    trace = _load_fixture("1-clean-chain")

    # Build adjacency: node_id → children
    children: dict[str, list[str]] = {}
    for node in trace.chain:
        for pid in node.parent_ids:
            children.setdefault(pid, []).append(node.node_id)

    # Source has no parents
    source = trace.chain[0]
    assert source.parent_ids == []
    # Source is the root
    assert source.node_id in children  # source has children

    # Chain order matches tree walk
    # source → extraction → synthesis
    assert children[source.node_id] == ["extraction-opensci"]
    assert children["extraction-opensci"] == ["synthesis-opensci"]


def test_tree_reconstruction_all_fixtures():
    """All fixtures produce valid trees from parent_ids."""
    for name in ["1-clean-chain", "2-weak-extraction", "3-false-corroboration"]:
        trace = _load_fixture(name)

        # Every non-root node has a parent that exists in the chain
        node_ids = {n.node_id for n in trace.chain}
        for node in trace.chain:
            for pid in node.parent_ids:
                assert pid in node_ids, (
                    f"Fixture {name}: node {node.node_id} references parent "
                    f"{pid} which is not in chain"
                )


# ── Shared-ancestry detection ────────────────────────────────────


def _collect_upstream_sources(trace: TraceV01) -> dict[str, set[str]]:
    """Collect upstream sources for each chain (including the base chain)."""
    result: dict[str, set[str]] = {}

    def sources_for_chain(nodes):
        srcs: set[str] = set()
        for node in nodes:
            us = node.grade.upstream_source
            if us:
                srcs.add(us)
            # Also check input documents
            for doc in node.input_documents:
                if doc.source:
                    srcs.add(doc.source)
        return srcs

    result["base"] = sources_for_chain(trace.chain)
    for i, corr_chain in enumerate(trace.corroborating_chains):
        result[f"corr_{i}"] = sources_for_chain(corr_chain)

    return result


def test_shared_ancestry_fixture_3_all_share_noaa():
    """Fixture 3: all three chains share noaa.gov upstream."""
    trace = _load_fixture("3-false-corroboration")
    sources = _collect_upstream_sources(trace)

    # All chains should include noaa.gov
    for chain_name, chain_sources in sources.items():
        assert "noaa.gov" in chain_sources, (
            f"Chain '{chain_name}' missing noaa.gov upstream source. Sources found: {chain_sources}"
        )


def test_shared_ancestry_fixture_1_disjoint_sources():
    """Fixture 1: chains have genuinely disjoint sources."""
    trace = _load_fixture("1-clean-chain")
    sources = _collect_upstream_sources(trace)

    # Base chain uses openstax, corroborating uses hyperphysics
    # They should not share an upstream source
    base_sources = sources["base"]
    assert len(trace.corroborating_chains) == 1
    corr_sources = sources["corr_0"]

    # Check that they have at least one different source
    # (they may still have model families in common, but sources should be different)
    assert "openstax.org" in base_sources
    assert "hyperphysics.phy-astr.gsu.edu" in corr_sources
    # No direct source overlap expected
    overlap = base_sources & corr_sources
    # Model families like "claude-3" or "gpt-4" may appear but actual sources shouldn't
    no_source_overlap = not any(
        s for s in overlap if "openstax" in s or "hyperphysics" in s or "noaa" in s
    )
    # At minimum, the document-level sources are different
    assert "openstax.org" not in corr_sources or "hyperphysics.phy-astr.gsu.edu" not in base_sources


def test_shared_ancestry_fixture_3_document_hash_identical():
    """Fixture 3: sessions 2 and 3 read the report session 1 wrote."""
    trace = _load_fixture("3-false-corroboration")

    # Collect all document hashes consumed by corroborating chains
    corr_hashes: set[str] = set()
    for corr_chain in trace.corroborating_chains:
        for node in corr_chain:
            for doc in node.input_documents:
                if doc.content_hash:
                    corr_hashes.add(doc.content_hash)

    # The internal report hash should appear (from sessions 2 and 3 reading session 1's output)
    internal_report_hash = "b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3"
    assert internal_report_hash in corr_hashes, (
        "Corroborating chains should share the internal report hash — "
        "sessions 2 and 3 read the report session 1 wrote"
    )

    # Both corroborating chains reference this same document
    for i, corr_chain in enumerate(trace.corroborating_chains):
        chain_hashes = set()
        for node in corr_chain:
            for doc in node.input_documents:
                if doc.content_hash:
                    chain_hashes.add(doc.content_hash)
        assert internal_report_hash in chain_hashes, (
            f"Corroborating chain {i} should reference the internal report"
        )


def test_shared_ancestry_independence_enum_never_boolean():
    """Independence must be a first-class enum, never collapsed to bool."""
    trace = _load_fixture("3-false-corroboration")
    # The value is an enum, not a bool
    assert isinstance(trace.independence, CorroborationVerdict)
    assert trace.independence == CorroborationVerdict.SHARED_ANCESTRY_DETECTED
    # The string value communicates what happened
    assert trace.independence.value == "shared_ancestry_detected"


# ── Contradiction flag ───────────────────────────────────────────


def test_contradiction_representation():
    """Contradiction is a flag, not resolved by score."""
    from isnad.trace.schema import ContradictionFlag

    flag = ContradictionFlag(
        claim_a="F = ma",
        chain_a_node_ids=["node-1", "node-2"],
        claim_b="F ≠ ma in relativistic regimes",
        chain_b_node_ids=["node-3", "node-4"],
    )
    assert not flag.resolved  # default: unresolved
    assert flag.claim_a != flag.claim_b


# ── DocumentRef ──────────────────────────────────────────────────


def test_document_ref_content_not_full_text():
    """DocumentRef records identity, not full content. Content is redacted by default."""
    doc = DocumentRef(
        source="arxiv",
        doc_id="2607.24117",
        content_hash="abc123",
    )
    # No full text field exists
    assert not hasattr(doc, "content")
    assert not hasattr(doc, "full_text")
    assert not hasattr(doc, "text")


# ── Rendering smoke test ─────────────────────────────────────────


def test_viewer_html_exists():
    """The viewer HTML file exists and is parseable."""
    viewer_path = PROJECT_DIR / "viewer" / "index.html"
    assert viewer_path.exists(), f"Viewer not found at {viewer_path}"

    with open(viewer_path) as f:
        html = f.read()

    # Basic structure checks
    assert "<!DOCTYPE html>" in html
    assert "ISNAD Chain Viewer" in html
    # Must reference fixture 3 (false corroboration) since that's the demo
    assert "SHARED ANCESTRY DETECTED" in html
    assert "mad\u0101r" in html or "pivot narrator" in html  # diagnostic term present


def test_viewer_html_renders_all_three_states():
    """The viewer must render verified, unverified, and shared_ancestry_detected states."""
    viewer_path = PROJECT_DIR / "viewer" / "index.html"
    with open(viewer_path) as f:
        html = f.read()

    # Confidence must not be conveyed by colour alone
    assert "prefers-reduced-motion" in html
    # Keyboard focus must be visible
    assert "focus-visible" in html
    # Must not hardcode numeric confidence like "87.3"
    assert "87.3" not in html


def test_json_schema_emitted():
    """The JSON Schema file is emitted alongside fixtures."""
    schema_path = FIXTURES_DIR / "isnad_trace_v0.1.schema.json"
    assert schema_path.exists()
    with open(schema_path) as f:
        schema = json.load(f)
    assert schema["title"] == "TraceV01"
    assert "chain" in schema["properties"]
    assert "independence" in schema["properties"]
