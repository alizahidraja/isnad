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

## Tenuo (task-scoped authorization) — showcase bridge (3.2.0 candidate)

Tenuo authorizes *what* an agent may call; it never checks whether the *data*
behind an allowed argument is true. The `isnad[tenuo]` extra closes that gap
with a Tier-1 Tenuo constraint that verifies a signed ISNAD grade attestation
on a high-risk argument before the tool runs.

- **Seam**: `IsnadGradeConstraint(min_grade, trusted_public_key).satisfies(value)` —
  the constrained field's value is an ISNAD-attested envelope `{"value", "attestation"}`;
  the guard verifies it, the tool unwraps it.
- **Trust model**: the issuer key IS the ISNAD grading authority (PKI); the
  `isnad_digest` is signed but not ledger-resolved in this showcase.
- **Not a Tenuo-core PR** — this lives in ISNAD's repo; the Tenuo-core path is
  issue-first per their CONTRIBUTING.md, after engagement.
- **Demo**: `examples/tenuo_invoice_demo.py` — a steelmanned warrant passes a
  legitimate payment, a poisoned "update vendor details" payload clears Tenuo
  alone, and with ISNAD the swapped IBAN is denied with its own trace.
