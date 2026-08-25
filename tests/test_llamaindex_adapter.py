"""Real LlamaIndex test — actual NodeWithScore/TextNode objects, no LLM key."""

from __future__ import annotations

import pytest

pytest.importorskip("llama_index.core")

from llama_index.core.schema import NodeWithScore, TextNode

from isnad.core.registry import Registry
from isnad.integrations.llamaindex import IsnadNodePostprocessor
from isnad.types import NarratorGrade


class TestIsnadNodePostprocessor:
    def test_appends_lineage_to_real_nodes(self):
        reg = Registry()
        reg.register("source:pubmed", "medicine", grade=NarratorGrade.RELIABLE)
        pp = IsnadNodePostprocessor(reg, domain="medicine")

        nodes = [
            NodeWithScore(
                node=TextNode(text="aspirin reduces clotting", metadata={"source_id": "pubmed"})
            ),
            NodeWithScore(node=TextNode(text="something unknown", metadata={})),
        ]
        result = pp.postprocess_nodes(nodes)

        assert len(result) == 2
        assert result[0].node.metadata["isnad_narrator"] == "source:pubmed"
        assert result[0].node.metadata["isnad_grade"] == "reliable"
        # unknown source → ungraded
        assert result[1].node.metadata["isnad_narrator"] == "source:unknown"
        assert result[1].node.metadata["isnad_grade"] == "ungraded"

    def test_nodes_unchanged_otherwise(self):
        reg = Registry()
        pp = IsnadNodePostprocessor(reg)
        node = NodeWithScore(node=TextNode(text="keep me", metadata={"k": "v"}))
        pp.postprocess_nodes([node])
        assert node.node.text == "keep me"
        assert node.node.metadata["k"] == "v"  # original metadata preserved
