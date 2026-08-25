"""isnad_trace v0.1 — JSON schema for ISNAD transmission chains.

PROV / PROV-AGENT mapping:

    W3C PROV              isnad_trace v0.1
    ──────────────────    ──────────────────────────
    Entity                DocumentRef (input provenance)
    Activity              TransmitterNode (transformation step)
    Agent                 (narrator_id, role) pair
    wasGeneratedBy        TransmitterNode.output_claim
    used                  TransmitterNode.input_documents
    wasDerivedFrom        TransmitterNode.parent_ids
    wasAttributedTo       TransmitterNode.narrator_id
    wasAssociatedWith     TransmitterNode.role + narrator_id
    wasInformedBy         shared ancestry via input_documents overlap

    PROV-AGENT extension:
    AIModelInvocation     TransmitterNode (role=synthesis, model_version set)
    Prompt                (captured in input_documents as DocumentRef)
    ResponseData          output_claim
    AgentTool             TransmitterNode (role=tool)

Two scoring axes (never collapsed):

    chain_integrity   — How soundly was the claim transmitted?
                        Weakest-link over the chain, refined by transform type.
                        Does NOT attest to origin quality.
    origin_strength   — How trustworthy is the SOURCE of this claim?
                        Separate axis. A degraded chain from a sound origin
                        must be distinguishable from a clean chain from an
                        unverified source.

Independence: first-class enum, never a silent boolean.
    verified                — Independence structurally confirmed.
    unverified              — Default. Not yet checked.
    shared_ancestry_detected — Correlated chains detected; corroboration discounted.

Contradiction: where two chains reach contradictory claims, the trace carries
the contradiction rather than resolving it by score.  Resolved by content
criticism (matn), not chain quality (isnād).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from isnad.types import Role as Role


class ChainIntegrity(StrEnum):
    """How soundly was this claim transmitted through the chain?"""

    SAHIH = "sahih"  # sound — complete chain, all narrators reliable
    HASAN = "hasan"  # good — mostly reliable, ≥1 ungraded or mid-tier
    DAIF = "daif"  # weak — weak narrator, or incomplete chain
    MAWDU = "mawdu"  # rejected — fabricated/poisoned source, quarantined
    UNGRADED = "ungraded"  # chain not yet assessed


class OriginStrength(StrEnum):
    """How trustworthy is the SOURCE this claim originated from?

    Separated from chain integrity.  A pristine chain from an unverified
    source must be visibly different from a degraded chain from a sound one.
    """

    VERIFIED = "verified"  # cryptographically or structurally attested
    ATTESTED = "attested"  # domain-bound, issuer-attested (e.g. Live Verify seal)
    REPUTABLE = "reputable"  # strong track record, no known integrity failures
    UNKNOWN = "unknown"  # provenance not assessed
    SUSPECT = "suspect"  # potential manipulation vector
    COMPROMISED = "compromised"  # known injection/poisoning source


class CorroborationVerdict(StrEnum):
    """Independence status — first-class, never a silent boolean.

    The honest three-way split (issue #54):
    - SHARED_ANCESTRY_DETECTED — dependence *proven* (shared lineage found).
    - ASSUMED — no shared lineage found, but independence is *assumed from
      topology*, not proven; correlated blind spots are undetectable.
    - UNVERIFIED — not yet checked.
    """

    VERIFIED = "verified"  # legacy: kept for serialization compatibility
    ASSUMED = "assumed"  # no shared ancestry, but independence is assumed, not proven
    UNVERIFIED = "unverified"  # default: not yet checked
    SHARED_ANCESTRY_DETECTED = "shared_ancestry_detected"  # correlated chains found


class Grade(BaseModel):
    """A transmitter's grade for a specific (narrator, role, domain) triplet.

    Ordinal first, numeric only where calibration data exists.
    The schema keeps adalah (integrity) and dabt (precision) as distinct axes.
    """

    narrator_id: str = Field(description="Stable identifier, e.g. 'model:gpt-4o'")
    role: Role = Field(description="What the transmitter did at this step")
    domain: str = Field(default="general", description="Domain tag for per-domain grading")

    # Ordinal grades — these are the primary trust signals
    chain_integrity: ChainIntegrity = Field(
        default=ChainIntegrity.UNGRADED,
        description="Transmission quality: how soundly does this narrator relay claims?",
    )
    adalah: str = Field(
        default="unassessed",
        description="ʿAdālah — integrity / manipulation-resistance axis",
    )
    dabt: str = Field(
        default="unassessed",
        description="Ḍabṭ — precision / error-rate axis",
    )

    # Origin strength — separate from chain integrity
    origin_strength: OriginStrength = Field(
        default=OriginStrength.UNKNOWN,
        description="How trustworthy is the source this narrator originated from?",
    )

    # Metadata — optional, numeric only where calibrated
    model_version: str | None = Field(
        default=None,
        description="Resolved model version, not alias. Required when role=synthesis.",
    )
    model_family: str | None = Field(default=None, description="For correlation (madār) detection")
    upstream_source: str | None = Field(
        default=None, description="Upstream origin for shared-ancestry detection"
    )
    known_error_rate: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Calibrated error rate; NULL = uncalibrated"
    )
    evidence_count: int = Field(
        default=0, description="Number of evidence log entries for this narrator"
    )


class DocumentRef(BaseModel):
    """Input provenance: what a transmitter consumed before it spoke.

    Records document identity (source, id, hash), not full content.
    Content is redacted by default — full capture is opt-in.
    """

    source: str = Field(description="Source identifier, e.g. 'arxiv', 'wikipedia'")
    doc_id: str | None = Field(default=None, description="Document identifier within source")
    content_hash: str | None = Field(
        default=None, description="SHA-256 of document content for integrity"
    )
    title: str | None = Field(default=None, description="Human-readable title")
    retrieved_at_step: int | None = Field(
        default=None, description="Which chain step retrieved this document"
    )


class ReasoningCapture(BaseModel):
    """A model's hidden chain-of-thought, captured from a reasoning-model response.

    Reasoning models (OpenAI o-series, DeepSeek-R1, Anthropic extended
    thinking, Gemini thinking) emit hidden reasoning before their final
    answer.  This reasoning is a *load-bearing transmission step* — it is
    often where a model over-commits, drops evidence, or reasons from a
    flawed premise — and it is currently invisible in most provenance traces.

    Capture is **hash-by-default**: the raw reasoning text is NOT stored;
    only its SHA-256 and a short preview.  Reasoning is unfiltered and is
    where secrets/PII leak, so full-text capture is opt-in (consistent with
    ``capture_full_content`` on the callback handler).

    Provider fidelity is uneven, so this is a tri-state:
    - ``content_hash`` set → reasoning captured (raw text seen).
    - ``redacted == True`` → the provider withheld/redacted the reasoning
      (e.g. Anthropic's ``redacted_thinking``); nothing usable was seen.
    - both absent → the model/provider exposed no reasoning at all.
    """

    content_hash: str | None = Field(
        default=None,
        description="SHA-256 of the raw reasoning text (when seen). NULL if absent/redacted.",
    )
    preview: str | None = Field(
        default=None,
        description="Short, truncated preview of the reasoning (first ~120 chars). "
        "Always present when content_hash is set, even if full capture is off.",
    )
    source: str | None = Field(
        default=None,
        description="Which provider/field exposed it: 'deepseek', 'anthropic', "
        "'openai', 'content_blocks', or 'unknown'.",
    )
    redacted: bool = Field(
        default=False,
        description="True when the provider explicitly withheld the reasoning "
        "(e.g. a 'redacted_thinking' block). Distinct from absent.",
    )


class TransmitterNode(BaseModel):
    """One step in a transmission chain — what produced the claim at this step.

    This is the core provenance record.  Each node records:
    - what it is (narrator_id, role, model_version)
    - what it consumed (input_documents, parent_ids)
    - what it produced (output_claim)
    - how reliable it is (grade)
    """

    node_id: str = Field(description="Stable node identifier, e.g. run_id from LangChain")
    parent_ids: list[str] = Field(default_factory=list, description="Parent node IDs — chain edges")
    role: Role = Field(description="retrieval, extraction, synthesis, tool, human, source")
    narrator_id: str = Field(description="Stable narrator identifier")
    model_version: str | None = Field(
        default=None,
        description=(
            "Resolved model version. NULL = unknown (record this fact, don't fall back silently)."
        ),
    )
    step: int = Field(ge=0, description="Zero-indexed position in chain")

    # What was consumed
    input_documents: list[DocumentRef] = Field(
        default_factory=list,
        description="Documents/prior outputs consumed before producing the claim. "
        "This is the primary source of input provenance — without it, "
        "independence cannot be checked.",
    )

    # What was produced
    output_claim: str | None = Field(
        default=None,
        description="The claim text produced at this step. NULL for retrieval/tool steps.",
    )

    # Hidden reasoning (reasoning models only) — optional, hash-by-default
    reasoning: ReasoningCapture | None = Field(
        default=None,
        description="A model's chain-of-thought, captured where the provider exposes it. "
        "Hash + preview only by default (raw reasoning is unfiltered and may contain "
        "secrets/PII). None when the model is not a reasoning model or exposed no reasoning.",
    )

    # Grade — separate axes
    grade: Grade = Field(description="Per (narrator, role, domain) grade")

    # Metadata
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 timestamp of this transformation",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata (temperature, token counts, etc.)",
    )


class ContradictionFlag(BaseModel):
    """Where two chains reach contradictory claims, carry the contradiction.

    The classical system rejected a narration by a reliable transmitter that
    contradicted a stronger one on the *contradiction* (shādhdh), not on any
    chain defect — contradiction routed to content criticism (matn) rather
    than being settled by chain quality (isnād).
    """

    claim_a: str = Field(description="First contradictory claim text")
    chain_a_node_ids: list[str] = Field(description="Node IDs for chain A")
    claim_b: str = Field(description="Second contradictory claim text")
    chain_b_node_ids: list[str] = Field(description="Node IDs for chain B")
    resolved: bool = Field(default=False, description="Has a human reviewer adjudicated?")
    resolution: str | None = Field(default=None, description="Adjudication result if resolved")


class TraceV01(BaseModel):
    """isnad_trace v0.1 — the serializable chain capture.

    Versioned, self-describing, with an explicit PROV mapping.
    This is the contract between capture and rendering.
    """

    schema_version: str = Field(
        default="0.1", description="Schema version — bump on breaking changes"
    )
    trace_id: str = Field(description="Unique trace identifier")
    claim_text: str = Field(description="The final claim text being evaluated")
    claim_domain: str = Field(default="general", description="Domain tag for the claim")

    # The transmission chain — ordered list of transmitter nodes
    chain: list[TransmitterNode] = Field(
        description="Ordered transmission chain (source → ... → synthesis)"
    )

    # Corroborating chains (if any)
    corroborating_chains: list[list[TransmitterNode]] = Field(
        default_factory=list,
        description="Independent chains asserting the same claim",
    )

    # Aggregate scores — kept on separate axes, never collapsed
    chain_integrity: ChainIntegrity = Field(
        description="Chain grade: weakest-link, refined by transform type"
    )
    origin_strength: OriginStrength = Field(
        description="Origin strength: best source grade across all chains"
    )

    # Independence verdict
    independence: CorroborationVerdict = Field(
        default=CorroborationVerdict.UNVERIFIED,
        description="Independence status of corroborating chains",
    )
    independence_detail: str = Field(
        default="",
        description="Human-readable explanation of the independence verdict",
    )

    # Contradictions (if any)
    contradictions: list[ContradictionFlag] = Field(
        default_factory=list,
        description="Contradictory claims from other chains — routed to content criticism",
    )

    # Binding constraint — what limits this claim's trust?
    binding_constraint: str = Field(description="Which link is the binding constraint, and why?")
    binding_step: int | None = Field(
        default=None, description="Zero-indexed step of the binding constraint link"
    )

    # Created / provenance metadata
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 timestamp of trace creation",
    )
    capture_source: str = Field(
        default="manual",
        description="How was this trace captured? 'langchain', 'manual', 'prov-agent'",
    )
