"""ISNAD × LangChain Integration.

Honest, early-stage integration of ISNAD claim-level provenance
into LangChain/LangGraph agent pipelines.

Key components:
- IsnadTracer:  BaseCallbackHandler that records transmission chains
- isnad_track:  Decorator for simple functions
- seed_registry: Helper to bootstrap narrator grades
- CriticAdapter: Interface for plugging in a real ContentCritic

IMPORTANT LIMITATIONS (read before using):
- The bundled deterministic ContentCritic is a non-functional reference stub
  on real text. For practical coverage, supply an LLM- or embedding-backed
  critic via the CriticAdapter or implement the ContentCritic protocol.
- Corroboration (mutābaʿāt) is experimentally untested on real corpora.
- Seed-grade your known-reliable narrators (sources, models) for practical
  coverage. Cold-start grades produce near-zero coverage.
- See experiments/s8_gated_vs_ungated/results/RESULTS.md for details.

Usage (5 lines):
    from isnad.integrations.langchain import IsnadTracer, seed_registry
    reg = seed_registry({"source:my-docs": "reliable", "model:gpt-4": "acceptable"})
    tracer = IsnadTracer(registry=reg)
    chain.invoke(input, config={"callbacks": [tracer]})
    print(tracer.report())
"""

from isnad.integrations.langchain.decorator import isnad_track
from isnad.integrations.langchain.helpers import CriticAdapter, seed_registry
from isnad.integrations.langchain.tracer import IsnadTracer

__all__ = ["IsnadTracer", "isnad_track", "seed_registry", "CriticAdapter"]
