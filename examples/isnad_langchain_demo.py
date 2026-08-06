"""Runnable ISNAD example — a mock RAG pipeline with callback handler attached.

This runs WITHOUT API keys.  It uses fake components:
- A FakeRetriever that returns hardcoded documents
- A FakeLLM that returns a canned response
- An IsnadCallbackHandler that captures the full trace

Run:
    python examples/isnad_langchain_demo.py

Output: a TraceV01 JSON document printed to stdout.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from isnad.core.registry import Registry
from isnad.integrations.langchain.callback import IsnadCallbackHandler
from isnad.integrations.langchain.helpers import seed_registry
from isnad.types import AdalahGrade, DabtGrade, NarratorGrade, NarratorType


# ── Fake components (no API keys needed) ────────────────────────

class FakeDocument:
    """Minimal Document stand-in — matches LangChain's Document interface."""
    def __init__(self, page_content: str, metadata: dict[str, Any] | None = None):
        self.page_content = page_content
        self.metadata = metadata or {}


class FakeRetriever:
    """Returns hardcoded physics documents."""
    def __init__(self):
        self._docs = [
            FakeDocument(
                "The momentum of a photon is given by p = h/λ, "
                "where h is Planck's constant (6.626 × 10⁻³⁴ J·s) "
                "and λ is the wavelength.",
                {"source": "openstax.org", "id": "physics-vol3-ch6",
                 "title": "Photons and Matter Waves"},
            ),
            FakeDocument(
                "Photons have zero rest mass but carry momentum p = E/c = h/λ. "
                "This was experimentally confirmed by Compton scattering in 1923.",
                {"source": "hyperphysics.phy-astr.gsu.edu", "id": "photon-momentum",
                 "title": "Photon Momentum"},
            ),
        ]

    def invoke(self, query: str, config: dict | None = None, **kwargs) -> list[FakeDocument]:
        return self._docs


class FakeLLM:
    """Returns a canned response — no API call."""
    def invoke(self, prompt: str, config: dict | None = None, **kwargs) -> str:
        return (
            "The momentum of a photon is given by p = h/λ, "
            "where h is Planck's constant and λ is the wavelength. "
            "This relationship, confirmed by Compton scattering, shows that "
            "massless photons carry momentum inversely proportional to their wavelength."
        )


# ── The pipeline ────────────────────────────────────────────────

def run_demo() -> None:
    """Run the demo: build a registry, run a mock RAG pipeline, print the trace."""

    # 1. Seed the registry with known narrator grades
    reg = seed_registry(
        {
            "source:openstax-university-physics-vol3": "reliable",
            "source:hyperphysics-photon": "reliable",
            "model:gpt-4o": "acceptable",
            "model:gpt-3.5-turbo": "weak",
        },
        domain="physics",
    )

    # 2. Create the callback handler
    handler = IsnadCallbackHandler(
        registry=reg,
        domain="physics",
        trace_id=f"demo-{uuid.uuid4().hex[:8]}",
    )

    # 3. Build components
    retriever = FakeRetriever()
    llm = FakeLLM()

    # 4. Simulate a LangChain run by manually firing callbacks
    #    (In a real pipeline, pass handler to chain.invoke(config={"callbacks": [handler]}))
    run_id_root = "root-" + uuid.uuid4().hex[:8]
    run_id_retriever = "retriever-" + uuid.uuid4().hex[:8]
    run_id_llm = "llm-" + uuid.uuid4().hex[:8]

    # Simulate: chain start
    handler.on_chain_start(
        serialized={"name": "physics-rag-chain", "id": "rag"},
        inputs={"query": "What is photon momentum?"},
        run_id=run_id_root,
    )

    # Simulate: retriever runs
    handler.on_chain_start(
        serialized={"name": "retriever", "id": "retriever"},
        inputs={},
        run_id=run_id_retriever,
        parent_run_id=run_id_root,
    )
    docs = retriever.invoke("photon momentum")
    handler.on_retriever_end(
        documents=docs,
        run_id=run_id_retriever,
        parent_run_id=run_id_root,
    )

    # Simulate: LLM runs
    handler.on_llm_start(
        serialized={"name": "gpt-4o", "id": "gpt-4o"},
        prompts=["Based on the retrieved documents, what is the momentum of a photon?"],
        run_id=run_id_llm,
        parent_run_id=run_id_root,
        metadata={"ls_model_name": "gpt-4o-2024-08-06"},
    )
    response = llm.invoke("photon momentum")
    handler.on_llm_end(
        response=FakeLLMResponse(response),
        run_id=run_id_llm,
    )

    # Simulate: chain ends
    handler.on_chain_end(
        outputs={"output": response},
        run_id=run_id_root,
    )

    # 5. Produce the trace
    trace = handler.to_trace()
    if trace is None:
        print("No trace captured.")
        return

    print("=" * 60)
    print("ISNAD Trace — mock RAG pipeline")
    print("=" * 60)
    print()
    print(json.dumps(json.loads(trace.model_dump_json()), indent=2))


class FakeLLMResponse:
    """Minimal stand-in for an LLM response object."""
    def __init__(self, text: str):
        self.content = text


# ── Main ────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_demo()
