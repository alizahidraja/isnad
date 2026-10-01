# ISNAD universal connector — strategy (draft for the repo docs)

Goal: one documented seam that captures **WHO** transmitted a claim, across every
orchestrator ISNAD integrates with — so an enterprise dev adds provenance with a single
line (`callbacks=[IsnadTracer(registry)]`, `tracer_provider=IsnadTracer()`, etc.).

## What ISNAD already ships (formalize these, don't build new ones)
| Integration | Capture seam | Status |
|---|---|---|
| LangChain / LangGraph | `IsnadTracer` / `IsnadCallbackHandler` (tree from run_id→parent_run_id) | shipped |
| LlamaIndex | adapter appends provenance to retrieved nodes | shipped |
| CrewAI | adapter | shipped |
| OpenTelemetry | `isnad ingest --otlp` grades an existing GenAI trace | shipped |
| MCP | `MCPToolObserver` records tool calls as TOOL narrator links | shipped |

## The principle (the one rule every connector must obey)
**Capture the transmission seam, never the content truth.** A connector records *who*
produced a chunk, in *what order*, with *what transform* (retriever → synthesis → critic →
summarizer). It must NOT:
- grade the *output* for correctness (that's the critic's job — WHO vs WHETHER),
- treat a vector store as a narrator (Pinecone/Milvus/Qdrant hold embeddings, not
  transmission lineage — the *retriever* is the narrator),
- auto-grade from call volume (GIGO — the MCP server already refuses this).

## The "single line" contract (best practice)
Every connector exposes the same three-move pattern:
1. `seed_registry({narrator_id: grade})` — warm-start the rijāl.
2. attach the tracer/callback to the pipeline.
3. read `trace.chain_grade` / `decide()` — one action: serve / caveat / review / quarantine.

## Defer until a named customer demands it
- Native Pinecone/Milvus/Qdrant plugins (vector stores are not narrators; the retriever seam is).
- AutoGen deep integration.
- AWS/Azure/GCP marketplace templates (three marketplaces are a heavy solo lift with zero revenue).

## The litmus test
A connector is correct iff it answers *"who vouches for this claim, and how much?"* and
never *"is this claim true?"* — the latter is the critic's lane, and the critic composes in.
