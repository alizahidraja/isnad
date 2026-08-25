"""LlamaIndex adapter — append narrator lineage to retrieved nodes (issue #70).

A duck-typed node postprocessor: LlamaIndex accepts any object exposing
``postprocess_nodes(nodes, query_bundle)``, so no ``llama-index-core`` import is
required. It appends a structured narrator-lineage profile (grade + narrator id)
to each ``NodeWithScore`` node's metadata before the response is returned.

Honest limit: this grades the *sources* of retrieved nodes, not the nodes'
content. Live verification needs ``llama-index-core`` installed.
"""

from __future__ import annotations

from isnad.core.registry import Registry


class IsnadNodePostprocessor:
    """Append ``isnad_grade`` + ``isnad_narrator`` to each retrieved node."""

    def __init__(self, registry: Registry, domain: str = "general") -> None:
        self.registry = registry
        self.domain = domain

    def postprocess_nodes(self, nodes: list, query_bundle: object = None) -> list:
        """Duck-typed LlamaIndex postprocessor over ``NodeWithScore`` objects."""
        for node_with_score in nodes:
            node = node_with_score.node
            metadata = getattr(node, "metadata", None)
            if metadata is None:
                metadata = {}
                node.metadata = metadata
            source = metadata.get("source_id") or metadata.get("source", "unknown")
            narrator_id = f"source:{source}"
            metadata["isnad_narrator"] = narrator_id
            metadata["isnad_grade"] = self.registry.get_grade(narrator_id, self.domain).value
        return nodes
