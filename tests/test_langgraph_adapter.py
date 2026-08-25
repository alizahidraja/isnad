"""Real LangGraph test — an actual compiled graph, no LLM key needed.

LangGraph propagates LangChain callbacks, so the existing IsnadCallbackHandler
should capture a graph run's nodes as the isnād. This pins that.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph")

from typing import TypedDict

from langgraph.graph import END, StateGraph

from isnad.integrations.langchain import seed_registry
from isnad.integrations.langgraph import IsnadCallbackHandler


class _State(TypedDict):
    text: str


def _build_graph():
    def node_a(state: _State) -> dict:
        return {"text": state["text"] + " -> a"}

    def node_b(state: _State) -> dict:
        return {"text": state["text"] + " -> b"}

    graph = StateGraph(_State)
    graph.add_node("node_a", node_a)
    graph.add_node("node_b", node_b)
    graph.set_entry_point("node_a")
    graph.add_edge("node_a", "node_b")
    graph.add_edge("node_b", END)
    return graph.compile()


def test_langgraph_run_captures_trace():
    handler = IsnadCallbackHandler(
        registry=seed_registry({"node_a": "reliable", "node_b": "acceptable"}),
        domain="general",
    )
    result = _build_graph().invoke({"text": "start"}, config={"callbacks": [handler]})
    assert result["text"] == "start -> a -> b"

    trace = handler.to_trace()
    # The trace must have captured the run (a chain with transmitter nodes).
    assert trace.chain_integrity is not None
    assert len(trace.chain) >= 2
    names = [n.narrator_id for n in trace.chain]
    assert "node_a" in names and "node_b" in names


def test_langgraph_run_gracefully_degrades_without_handler():
    # The graph itself runs fine even with no ISNAD handler attached.
    result = _build_graph().invoke({"text": "start"})
    assert result["text"] == "start -> a -> b"
