# isnad_trace v0.1 — Schema Specification

Versioned, serializable schema for ISNAD transmission chain capture and
rendering.  This is the contract between capture (LangChain callbacks, manual
construction, PROV-AGENT ingestion) and rendering (the viewer component).

## PROV / PROV-AGENT Mapping

The schema aligns with W3C PROV-DM / PROV-O and the PROV-AGENT extension
(arXiv 2508.02866).  A PROV-AGENT graph can be ingested as an ISNAD trace
through a mechanical mapping:

| W3C PROV class       | isnad_trace v0.1          | Notes |
|----------------------|---------------------------|-------|
| `prov:Entity`        | `DocumentRef`             | Input provenance: documents/prior outputs consumed |
| `prov:Activity`      | `TransmitterNode`         | A transformation step in the chain |
| `prov:Agent`         | `(narrator_id, role)`     | The transmitter's identity + role |
| `wasGeneratedBy`     | `TransmitterNode.output_claim` | The claim produced at this step |
| `used`               | `TransmitterNode.input_documents` | What was consumed before producing |
| `wasDerivedFrom`     | `TransmitterNode.parent_ids` | Chain edges (parent → child) |
| `wasAttributedTo`    | `TransmitterNode.narrator_id` | Who/what performed the step |
| `wasAssociatedWith`  | `TransmitterNode.role + narrator_id` | Role-specific association |
| `wasInformedBy`      | Shared ancestry via `input_documents` overlap | Structural independence detection |
| `prov:Collection`    | `TraceV01.corroborating_chains` | Multiple chains for the same claim |

| PROV-AGENT class     | isnad_trace v0.1          | Notes |
|----------------------|---------------------------|-------|
| `AIAgent`            | `TransmitterNode` (any role) | An AI agent in the pipeline |
| `AIModelInvocation`  | `TransmitterNode` (role=synthesis, model_version set) | Model invocation with version |
| `Prompt`             | `DocumentRef` (captured as input) | The prompt is input provenance |
| `ResponseData`       | `output_claim`            | The model's response |
| `AgentTool`          | `TransmitterNode` (role=tool) | External tool execution |

## Relationship to PROV-AGENT

PROV-AGENT captures **what happened** — a complete, queryable agent graph with
`AIModelInvocation`, `Prompt`, `ResponseData`, and `AgentTool` executions.  It
supports root-cause analysis by human query over the full provenance graph.

ISNAD is the **evaluative layer** that sits on top: given the graph, how much
weight can this claim carry?  The trace schema adds what PROV-AGENT does not:

- Per-transmitter grades on two axes (chain integrity, origin strength)
- Weakest-link binding with transform-type refinement
- Independence detection (verified / unverified / shared_ancestry_detected)
- Corroboration with correlation discount
- Contradiction routing to content criticism
- A binding constraint diagnosis

A PROV-AGENT graph is ingested by mapping `AIModelInvocation` → `TransmitterNode`,
`Prompt` → `DocumentRef`, and `ResponseData` → `output_claim`.  The grade fields
are then populated from the ISNAD registry.

## Two Scoring Axes

Chain integrity and origin strength are carried **separately**, never collapsed
through a single `min()`:

| Axis | What it measures | Enum values |
|------|-----------------|-------------|
| `chain_integrity` | How soundly was the claim transmitted? | `sahih`, `hasan`, `daif`, `mawdu`, `ungraded` |
| `origin_strength` | How trustworthy is the SOURCE? | `verified`, `attested`, `reputable`, `unknown`, `suspect`, `compromised` |

A degraded chain from a sound origin (ḍaʿīf + verified source) is
distinguishable from a pristine chain from an unattested origin (ṣaḥīḥ +
unknown origin).  The output *must* make these states distinguishable, not
merely rank them.

## Independence

First-class enum, never a silent boolean:

| Value | Meaning |
|-------|---------|
| `verified` | Independence structurally confirmed (disjoint narrator sets, different model families, different upstream sources) |
| `unverified` | Default.  Not yet checked.  Absence of evidence of sharing is not evidence of independence. |
| `shared_ancestry_detected` | Correlated chains found — shared narrator IDs, shared model family, or shared upstream source.  Corroboration is discounted. |

## Contradiction

Where two chains reach contradictory claims, the trace carries the
`contradictions` list rather than resolving by score.  The classical system
rejected a narration by a reliable transmitter that contradicted a stronger one
on the *contradiction* (shādhdh), not on any chain defect — contradiction
routes to content criticism (matn) rather than being settled by chain quality
(isnād).

## Version

`isnad_trace` v0.1.  Bump on breaking changes to the schema structure.
