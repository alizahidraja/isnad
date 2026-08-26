"""IsnadCallbackHandler — LangChain callback handler capturing ISNAD trace v0.1.

Tree-structured from run_id/parent_run_id (LangChain already provides the
tree).  Captures to the TraceV01 schema: transmitter nodes with input
provenance, two-axis grading, independence detection.

Key differences from the older IsnadTracer:
- Builds a tree from run_id → parent_run_id, not a flat list.
- Captures input provenance (retrieved Document objects).
- Records resolved model version from LLM response metadata.
- Detects shared ancestry structurally (overlapping retrieval sets).
- Redacts content by default; full capture is opt-in.
- Never lets a callback exception break the user's pipeline.
- Outputs TraceV01, the schema the viewer consumes.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from isnad.core.corroboration import SharedLineageDetector
from isnad.core.registry import Registry
from isnad.trace.schema import (
    ChainIntegrity,
    CorroborationVerdict,
    DocumentRef,
    Grade,
    OriginStrength,
    ReasoningCapture,
    Role,
    TraceV01,
    TransmitterNode,
)

logger = logging.getLogger(__name__)

# ── LangChain availability guard ────────────────────────────────

_LANGCHAIN_AVAILABLE = False
try:
    from langchain_core.callbacks import (  # type: ignore[import-not-found]
        AsyncCallbackHandler,
        BaseCallbackHandler,
    )

    _LANGCHAIN_AVAILABLE = True
except ImportError:
    BaseCallbackHandler = object  # type: ignore[misc,assignment]
    AsyncCallbackHandler = object  # type: ignore[misc,assignment]


# ── Helpers ─────────────────────────────────────────────────────


def _hash_content(text: str) -> str:
    """SHA-256 of content — identity, not disclosure."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _doc_to_ref(doc: Any) -> dict[str, str | None]:
    """Extract document identity (source, id, hash) without capturing full content."""
    if not _LANGCHAIN_AVAILABLE:
        return {"source": "unknown", "doc_id": None, "content_hash": None}
    metadata = getattr(doc, "metadata", {}) or {}
    page_content = getattr(doc, "page_content", "") or ""
    return {
        "source": str(metadata.get("source", "unknown")),
        "doc_id": str(metadata.get("id", metadata.get("doc_id", None))),
        "content_hash": _hash_content(page_content) if page_content else None,
    }


def _model_version_from_metadata(kwargs: dict[str, Any]) -> str | None:
    """Extract resolved model version from LLM response metadata.

    Checks in order: kwargs['metadata']['ls_model_name'],
    invocation_params['model'], serialized['kwargs']['model'].
    Returns None if no version found — the caller records this fact explicitly.
    """
    # LangChain often passes model info in metadata
    meta = kwargs.get("metadata", {}) or {}
    if isinstance(meta, dict):
        model = meta.get("ls_model_name")
        if model:
            return str(model)

    # Check invocation params (passed by some providers)
    inv = kwargs.get("invocation_params", {}) or {}
    if isinstance(inv, dict):
        model = inv.get("model") or inv.get("model_name")
        if model:
            return str(model)

    # Check serialized kwargs (name from model config)
    serialized = kwargs.get("serialized", {}) or {}
    if isinstance(serialized, dict):
        skw = serialized.get("kwargs", {}) or {}
        if isinstance(skw, dict):
            model = skw.get("model") or skw.get("model_name")
            if model:
                return str(model)

    return None


def _narrator_grade_to_chain_integrity(grade_value: str) -> ChainIntegrity:
    """Map NarratorGrade string to ChainIntegrity enum."""
    mapping = {
        "reliable": ChainIntegrity.SAHIH,
        "acceptable": ChainIntegrity.HASAN,
        "weak": ChainIntegrity.DAIF,
        "rejected": ChainIntegrity.MAWDU,
    }
    return mapping.get(grade_value, ChainIntegrity.UNGRADED)


def _adalah_to_origin_strength(adalah: str, origin_strength: str | None) -> OriginStrength:
    """Determine origin strength from adalah grade and explicit origin_strength."""
    if origin_strength:
        try:
            return OriginStrength(origin_strength)
        except ValueError:
            pass
    mapping = {
        "high": OriginStrength.REPUTABLE,
        "acceptable": OriginStrength.UNKNOWN,
        "suspect": OriginStrength.SUSPECT,
        "compromised": OriginStrength.COMPROMISED,
    }
    return mapping.get(adalah, OriginStrength.UNKNOWN)


def _detect_shared_ancestry(
    chains: list[list[TransmitterNode]],
) -> tuple[CorroborationVerdict, str]:
    """Detect shared ancestry across multiple chains.

    Delegates the correlation decision to the core ``SharedLineageDetector``
    (issue #125 step 3 — single source of truth; the callback no longer keeps
    its own duplicate 4-signal logic). Each pair of chains is reduced to the
    detector's inputs (narrator IDs, narrator metadata, retrieved-document
    hashes) and its structured assessment is mapped back to the trace verdict:
    any shared signal → SHARED_ANCESTRY_DETECTED; none → ASSUMED.

    Signals checked (see SharedLineageDetector.detect):
    1. Shared narrator IDs (hard correlation)
    2. Overlapping retrieval document hashes (the madār case)
    3. Same upstream source
    4. Same model family
    """
    if len(chains) < 2:
        return CorroborationVerdict.UNVERIFIED, "Single chain — independence not applicable."

    detector = SharedLineageDetector()

    def _metadata(chain: list[TransmitterNode]) -> dict[str, dict[str, object]]:
        return {
            n.narrator_id: {
                "model_family": n.grade.model_family,
                "upstream_source": n.grade.upstream_source,
            }
            for n in chain
        }

    def _doc_hashes(chain: list[TransmitterNode]) -> set[str]:
        return {d.content_hash for n in chain for d in n.input_documents if d.content_hash}

    for i, chain_a in enumerate(chains):
        for j, chain_b in enumerate(chains):
            if i >= j:
                continue

            assessment = detector.detect(
                [n.narrator_id for n in chain_a],
                [n.narrator_id for n in chain_b],
                {**_metadata(chain_a), **_metadata(chain_b)},
                chain_a_document_hashes=_doc_hashes(chain_a),
                chain_b_document_hashes=_doc_hashes(chain_b),
            )
            if assessment.shared_signals:
                detail = f"Chains {i} and {j} — " + "; ".join(assessment.shared_signals)
                return CorroborationVerdict.SHARED_ANCESTRY_DETECTED, detail

    return CorroborationVerdict.ASSUMED, (
        "No shared ancestry detected — independence is assumed from topology, "
        "not proven (correlated blind spots are undetectable)."
    )


# ── Sync callback handler ───────────────────────────────────────


class IsnadCallbackHandler(BaseCallbackHandler):  # type: ignore[misc,valid-type]
    """LangChain callback handler capturing ISNAD traces in TraceV01 format.

    Builds a tree from run_id/parent_run_id.  LangChain already passes these
    to every lifecycle method — the isnād structure is available for free.

    Usage:
        from isnad.integrations.langchain import IsnadCallbackHandler, seed_registry
        reg = seed_registry({"source:my-docs": "reliable", "model:gpt-4o": "acceptable"})
        handler = IsnadCallbackHandler(registry=reg, domain="physics")
        chain.invoke("What is F=ma?", config={"callbacks": [handler]})
        trace = handler.to_trace()
        print(trace.model_dump_json(indent=2))
    """

    def __init__(
        self,
        registry: Registry,
        *,
        domain: str = "general",
        capture_full_content: bool = False,
        trace_id: str | None = None,
    ):
        if not _LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is required for IsnadCallbackHandler. "
                "Install with: pip install isnad[langchain]"
            )
        super().__init__()
        self.registry = registry
        self.domain = domain
        self.capture_full_content = capture_full_content
        self.trace_id = trace_id or str(uuid.uuid4())

        # Per-run state
        self._nodes: dict[str, TransmitterNode] = {}  # run_id → node
        self._edges: dict[str, str] = {}  # run_id → parent_run_id
        self._step = 0
        self._final_claim: str | None = None

    # ── Callback hooks ──────────────────────────────────────────

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: Any,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._safe(lambda: self._on_chain_start(serialized, inputs, run_id, parent_run_id, kwargs))

    def on_retriever_end(
        self,
        documents: list[Any],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._safe(lambda: self._on_retriever_end(documents, run_id, parent_run_id, kwargs))

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._safe(
            lambda: self._on_tool_start(serialized, input_str, run_id, parent_run_id, kwargs)
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[Any],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._safe(lambda: self._on_llm_start(serialized, prompts, run_id, parent_run_id, kwargs))

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._safe(
            lambda: self._on_chat_model_start(serialized, messages, run_id, parent_run_id, kwargs)
        )

    def on_llm_end(self, response: Any, *, run_id: str, **kwargs: Any) -> None:
        self._safe(lambda: self._on_llm_end(response, run_id, kwargs))

    def on_chain_end(self, outputs: Any, *, run_id: str, **kwargs: Any) -> None:
        self._safe(lambda: self._on_chain_end(outputs, run_id, kwargs))

    def on_tool_end(self, output: Any, *, run_id: str, **kwargs: Any) -> None:
        self._safe(lambda: self._on_tool_end(output, run_id, kwargs))

    def on_retriever_error(self, error: BaseException, *, run_id: str, **kwargs: Any) -> None:
        logger.warning("Retriever error in run %s: %s", run_id, error)

    def on_llm_error(self, error: BaseException, *, run_id: str, **kwargs: Any) -> None:
        logger.warning("LLM error in run %s: %s", run_id, error)

    def on_tool_error(self, error: BaseException, *, run_id: str, **kwargs: Any) -> None:
        logger.warning("Tool error in run %s: %s", run_id, error)

    def on_chain_error(self, error: BaseException, *, run_id: str, **kwargs: Any) -> None:
        logger.warning("Chain error in run %s: %s", run_id, error)

    # ── Internal handlers ───────────────────────────────────────

    def _on_chain_start(
        self,
        serialized: dict | None,
        inputs: Any,
        run_id: str,
        parent_run_id: str | None,
        kwargs: dict,
    ) -> None:
        # LangGraph passes serialized=None and the node name via kwargs.
        name = "chain"
        if isinstance(serialized, dict):
            name = serialized.get("name", serialized.get("id", "chain"))
        if name == "chain":
            name = str(kwargs.get("name") or "chain")
        self._add_node(
            run_id=run_id,
            parent_run_id=parent_run_id,
            narrator_id=str(name),
            role=Role.SOURCE,
        )

    def _on_retriever_end(
        self, documents: list, run_id: str, parent_run_id: str | None, kwargs: dict
    ) -> None:
        # Build the node
        self._add_node(
            run_id=run_id,
            parent_run_id=parent_run_id,
            narrator_id="retriever",
            role=Role.RETRIEVAL,
        )
        node = self._nodes.get(run_id)
        if node and documents:
            for doc in documents:
                ref = _doc_to_ref(doc)
                node.input_documents.append(
                    DocumentRef(
                        source=ref["source"] or "unknown",
                        doc_id=ref["doc_id"],
                        content_hash=ref["content_hash"],
                    )
                )
            # Also record on parent node (the retriever's caller consumed these docs)
            if parent_run_id and parent_run_id in self._nodes:
                parent = self._nodes[parent_run_id]
                for doc in documents:
                    ref = _doc_to_ref(doc)
                    parent.input_documents.append(
                        DocumentRef(
                            source=ref["source"] or "unknown",
                            doc_id=ref["doc_id"],
                            content_hash=ref["content_hash"],
                        )
                    )

    def _on_tool_start(
        self, serialized: dict, input_str: str, run_id: str, parent_run_id: str | None, kwargs: dict
    ) -> None:
        name = serialized.get("name", "tool")
        self._add_node(
            run_id=run_id,
            parent_run_id=parent_run_id,
            narrator_id=f"tool:{name}",
            role=Role.TOOL,
        )

    def _on_llm_start(
        self, serialized: dict, prompts: list, run_id: str, parent_run_id: str | None, kwargs: dict
    ) -> None:
        model = serialized.get("name", serialized.get("id", "llm"))
        model_version = _model_version_from_metadata(kwargs)
        self._add_node(
            run_id=run_id,
            parent_run_id=parent_run_id,
            narrator_id=f"model:{model}",
            role=Role.SYNTHESIS,
            model_version=model_version,
        )
        # Record prompts as input documents (hashed by default)
        node = self._nodes.get(run_id)
        if node and prompts:
            for i, p in enumerate(prompts):
                if isinstance(p, str):
                    content = p if self.capture_full_content else None
                    content_hash = _hash_content(p)
                    node.input_documents.append(
                        DocumentRef(
                            source="prompt",
                            doc_id=f"prompt-{i}",
                            content_hash=content_hash,
                            title=content[:80] if content else None,
                        )
                    )

    def _on_chat_model_start(
        self, serialized: dict, messages: list, run_id: str, parent_run_id: str | None, kwargs: dict
    ) -> None:
        # Same as on_llm_start — chat models are a subclass
        model = serialized.get("name", serialized.get("id", "llm"))
        model_version = _model_version_from_metadata(kwargs)
        self._add_node(
            run_id=run_id,
            parent_run_id=parent_run_id,
            narrator_id=f"model:{model}",
            role=Role.SYNTHESIS,
            model_version=model_version,
        )

    def _on_llm_end(self, response: Any, run_id: str, kwargs: dict) -> None:
        node = self._nodes.get(run_id)
        if not node:
            return

        # Extract output claim from LLM response
        output_text = self._extract_llm_output(response)
        if output_text:
            node.output_claim = output_text
            if not self._final_claim:
                self._final_claim = output_text

        # Capture hidden reasoning (reasoning models only).
        reasoning = self._extract_reasoning(response)
        if reasoning is not None:
            node.reasoning = reasoning

    def _on_tool_end(self, output: Any, run_id: str, kwargs: dict) -> None:
        node = self._nodes.get(run_id)
        if not node:
            return
        output_text = str(output) if output else None
        if output_text:
            node.output_claim = output_text[:500]

    def _on_chain_end(self, outputs: Any, run_id: str, kwargs: dict) -> None:
        # Extract the final claim from chain output
        claim = self._extract_claim(outputs)
        if claim:
            self._final_claim = claim
        # Mark the root chain node's output
        node = self._nodes.get(run_id)
        if node and claim:
            node.output_claim = claim

    # ── Node management ─────────────────────────────────────────

    def _add_node(
        self,
        run_id: str,
        parent_run_id: str | None,
        narrator_id: str,
        role: Role,
        model_version: str | None = None,
    ) -> None:
        """Create a transmitter node and record the edge."""
        if run_id in self._nodes:
            return  # already seen this run_id

        if parent_run_id:
            self._edges[run_id] = parent_run_id

        # Look up grade from registry — role-scoped precision, integrity from
        # the default (person) record (issue #3).
        narrator = self.registry.get(narrator_id, self.domain, role=role) or self.registry.get(
            narrator_id, self.domain
        )
        identity = self.registry.get(narrator_id, self.domain)  # integrity + identity
        if narrator:
            # chain_integrity uses the effective (integrity-floored) grade so a
            # quarantined narrator reports REJECTED even in a role whose own
            # precision record is untainted.
            effective = self.registry.get_grade(narrator_id, self.domain, role=role)
            grade = Grade(
                narrator_id=narrator_id,
                role=role,
                domain=self.domain,
                chain_integrity=_narrator_grade_to_chain_integrity(effective.value),
                adalah=(identity.adalah_grade.value if identity else "unassessed"),
                dabt=narrator.dabt_grade.value,
                origin_strength=_adalah_to_origin_strength(
                    identity.adalah_grade.value if identity else None, None
                ),
                model_version=model_version or (identity.model_version if identity else None),
                model_family=identity.model_family if identity else None,
                upstream_source=identity.upstream_source if identity else None,
                known_error_rate=narrator.known_error_rate,
                evidence_count=len(narrator.evidence_log),
            )
        else:
            grade = Grade(
                narrator_id=narrator_id,
                role=role,
                domain=self.domain,
                chain_integrity=ChainIntegrity.UNGRADED,
                model_version=model_version,
            )

        node = TransmitterNode(
            node_id=str(run_id),
            parent_ids=[str(parent_run_id)] if parent_run_id else [],
            role=role,
            narrator_id=narrator_id,
            model_version=model_version,
            step=self._step,
            grade=grade,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._nodes[str(run_id)] = node
        self._step += 1

    def _build_chain(self) -> list[TransmitterNode]:
        """Reconstruct the ordered transmission chain from the tree.

        Walks from root (node with no parent) to leaves using the edge map.
        Returns nodes in transmission order.
        """
        if not self._nodes:
            return []

        # Find roots (nodes with no parent in our edges)
        roots = [
            nid
            for nid in self._nodes
            if nid not in self._edges or self._edges[nid] not in self._nodes
        ]

        ordered: list[TransmitterNode] = []

        def walk(node_id: str, depth: int):
            node = self._nodes[node_id]
            node.step = depth  # reassign step in transmission order
            ordered.append(node)
            children = [nid for nid, pid in self._edges.items() if pid == node_id]
            for child_id in sorted(children):
                walk(child_id, depth + 1)

        for root_id in roots:
            walk(root_id, 0)

        return ordered

    # ── Output extraction ───────────────────────────────────────

    @staticmethod
    def _extract_llm_output(response: Any) -> str | None:
        """Extract text from an LLM response object."""
        if not _LANGCHAIN_AVAILABLE:
            return str(response) if response else None
        try:
            # AIMessage / ChatResult
            if hasattr(response, "content"):
                return str(response.content)
            if hasattr(response, "generations"):
                gens = response.generations
                if gens and len(gens) > 0:
                    g0 = gens[0]
                    if hasattr(g0, "message"):
                        return str(g0.message.content)
                    if hasattr(g0, "text"):
                        return str(g0.text)
            return str(response) if response else None
        except Exception:
            return None

    @staticmethod
    def _extract_reasoning(response: Any) -> ReasoningCapture | None:
        """Extract hidden reasoning from a reasoning-model response.

        Best-effort, provider-agnostic, hash-by-default.  Returns a
        ReasoningCapture (hash + preview + source), or None when the
        response exposes no reasoning at all.

        Sources tried, in order (matching how LangChain surfaces it):

        1. LangChain canonical ``content_blocks`` — blocks with
           ``type == "reasoning"`` carry a ``reasoning`` string (either the
           thought summary or raw CoT).  Also detects Anthropic's
           ``redacted_thinking`` and ``thinking`` blocks.
        2. ``additional_kwargs["reasoning_content"]`` — DeepSeek-R1 and
           OpenAI o-series put raw/summary reasoning here.
        3. ``message.additional_kwargs["reasoning_content"]`` on a
           generation's message (DeepSeek via LangChain).

        A ``redacted_thinking`` block yields a ReasoningCapture with
        ``redacted=True`` and no hash — the provider withheld the text, which
        is a distinct state from "no reasoning exposed".

        Honest limit: providers expose reasoning inconsistently (OpenAI
        o-series exposes only an opt-in summary, not raw tokens).  This
        captures what is there and marks what is not — it does not pretend
        the raw chain-of-thought is available when the vendor withheld it.
        """
        if not _LANGCHAIN_AVAILABLE:
            return None
        try:
            reasoning_text: str | None = None
            source: str | None = None
            redacted = False

            # 1. LangChain canonical content_blocks.
            blocks = getattr(response, "content_blocks", None)
            if blocks:
                for block in blocks:
                    btype = block.get("type") if isinstance(block, dict) else None
                    if btype == "reasoning":
                        reasoning_text = block.get("reasoning")
                        source = "content_blocks"
                        if reasoning_text:
                            break
                    elif btype == "redacted_thinking":
                        redacted = True
                        source = "anthropic"
                    elif btype == "thinking":
                        reasoning_text = block.get("thinking")
                        source = "anthropic"
                        if reasoning_text:
                            break

            # 2/3. additional_kwargs on the response or its message.
            if not reasoning_text and not redacted:
                add_kwargs = getattr(response, "additional_kwargs", None)
                if add_kwargs and isinstance(add_kwargs, dict):
                    rc = add_kwargs.get("reasoning_content")
                    if rc:
                        reasoning_text = str(rc)
                        source = "additional_kwargs"
            if not reasoning_text and not redacted:
                gens = getattr(response, "generations", None)
                if gens and len(gens) > 0:
                    msg = getattr(gens[0], "message", None)
                    add_kwargs = getattr(msg, "additional_kwargs", None) or {}
                    rc = add_kwargs.get("reasoning_content")
                    if rc:
                        reasoning_text = str(rc)
                        source = "additional_kwargs"

            if redacted and not reasoning_text:
                return ReasoningCapture(redacted=True, source=source)
            if not reasoning_text:
                return None

            return ReasoningCapture(
                content_hash=_hash_content(reasoning_text),
                preview=reasoning_text[:120],
                source=source,
                redacted=False,
            )
        except Exception:
            return None

    @staticmethod
    def _extract_claim(outputs: Any) -> str | None:
        """Extract a claim string from chain output."""
        if isinstance(outputs, str):
            return outputs
        if isinstance(outputs, dict):
            for key in ("output", "answer", "text", "result", "response"):
                if key in outputs:
                    val = outputs[key]
                    if isinstance(val, str):
                        return val
            return str(outputs)
        return str(outputs) if outputs else None

    # ── Public API ──────────────────────────────────────────────

    def to_trace(self) -> TraceV01 | None:
        """Produce an isnad_trace v0.1 document from the captured run.

        Returns None if no chain was captured.
        """
        chain = self._build_chain()
        if not chain:
            return None

        # Compute chain integrity from per-node grades
        grades = [node.grade.chain_integrity for node in chain]
        chain_integrity = ChainIntegrity.UNGRADED
        if grades:
            if ChainIntegrity.MAWDU in grades:
                chain_integrity = ChainIntegrity.MAWDU
            elif ChainIntegrity.DAIF in grades:
                chain_integrity = ChainIntegrity.DAIF
            elif ChainIntegrity.HASAN in grades:
                chain_integrity = ChainIntegrity.HASAN
            elif all(g == ChainIntegrity.SAHIH for g in grades):
                chain_integrity = ChainIntegrity.SAHIH

        # Best origin strength across all nodes
        origin_order = [
            OriginStrength.VERIFIED,
            OriginStrength.ATTESTED,
            OriginStrength.REPUTABLE,
            OriginStrength.UNKNOWN,
            OriginStrength.SUSPECT,
            OriginStrength.COMPROMISED,
        ]
        origin_strength = OriginStrength.UNKNOWN
        for node in chain:
            node_origin = node.grade.origin_strength
            try:
                if origin_order.index(node_origin) < origin_order.index(origin_strength):
                    origin_strength = node_origin
            except ValueError:
                pass

        # Binding constraint: find the weakest node
        weakest_order = [
            ChainIntegrity.MAWDU,
            ChainIntegrity.DAIF,
            ChainIntegrity.HASAN,
            ChainIntegrity.SAHIH,
        ]
        binding_step = 0
        binding_node = chain[0] if chain else None
        for i, node in enumerate(chain):
            gi = node.grade.chain_integrity
            bg = binding_node.grade.chain_integrity if binding_node else ChainIntegrity.SAHIH
            try:
                if weakest_order.index(gi) < weakest_order.index(bg):
                    binding_node = node
                    binding_step = i
            except ValueError:
                pass

        binding_constraint = (
            f"Bounded by {binding_node.role.value} step "
            f"({binding_node.narrator_id}, grade: {binding_node.grade.chain_integrity.value})"
            if binding_node
            else "No binding constraint identified"
        )

        claim_text = self._final_claim or "(no claim captured)"

        # Detect shared ancestry (for now, single chain — corroboration not yet captured
        # across multiple runs; this is a placeholder for future multi-chain support)
        independence = CorroborationVerdict.UNVERIFIED
        independence_detail = "Single run — cross-run corroboration not yet captured."

        return TraceV01(
            trace_id=self.trace_id,
            claim_text=claim_text,
            claim_domain=self.domain,
            chain=chain,
            chain_integrity=chain_integrity,
            origin_strength=origin_strength,
            independence=independence,
            independence_detail=independence_detail,
            binding_constraint=binding_constraint,
            binding_step=binding_step if binding_node else None,
            capture_source="langchain",
        )

    def reset(self) -> None:
        """Reset all captured state for a new run."""
        self._nodes.clear()
        self._edges.clear()
        self._step = 0
        self._final_claim = None

    # ── Safety ──────────────────────────────────────────────────

    def _safe(self, fn):
        """Wrap a callback in try/except. Never let a callback exception
        break the user's pipeline."""
        try:
            fn()
        except Exception:
            logger.exception("IsnadCallbackHandler: callback failed")


# ── Async callback handler ──────────────────────────────────────


class AsyncIsnadCallbackHandler(AsyncCallbackHandler):  # type: ignore[misc,valid-type]
    """Async variant of IsnadCallbackHandler.

    Delegates to a sync handler under the hood. The sync handler's methods
    are not async-safe for concurrent invocation — each async run should
    use its own handler instance, or the user should manage a per-run pool.
    """

    def __init__(
        self,
        registry: Registry,
        *,
        domain: str = "general",
        capture_full_content: bool = False,
        trace_id: str | None = None,
    ):
        if not _LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is required for AsyncIsnadCallbackHandler. "
                "Install with: pip install isnad[langchain]"
            )
        super().__init__()
        self._sync = IsnadCallbackHandler(
            registry=registry,
            domain=domain,
            capture_full_content=capture_full_content,
            trace_id=trace_id,
        )

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: Any,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._sync.on_chain_start(
            serialized, inputs, run_id=run_id, parent_run_id=parent_run_id, **kwargs
        )

    async def on_retriever_end(
        self,
        documents: list[Any],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._sync.on_retriever_end(documents, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._sync.on_tool_start(
            serialized, input_str, run_id=run_id, parent_run_id=parent_run_id, **kwargs
        )

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[Any],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._sync.on_llm_start(
            serialized, prompts, run_id=run_id, parent_run_id=parent_run_id, **kwargs
        )

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._sync.on_chat_model_start(
            serialized, messages, run_id=run_id, parent_run_id=parent_run_id, **kwargs
        )

    async def on_llm_end(self, response: Any, *, run_id: str, **kwargs: Any) -> None:
        self._sync.on_llm_end(response, run_id=run_id, **kwargs)

    async def on_chain_end(self, outputs: Any, *, run_id: str, **kwargs: Any) -> None:
        self._sync.on_chain_end(outputs, run_id=run_id, **kwargs)

    async def on_tool_end(self, output: Any, *, run_id: str, **kwargs: Any) -> None:
        self._sync.on_tool_end(output, run_id=run_id, **kwargs)

    async def on_retriever_error(self, error: BaseException, *, run_id: str, **kwargs: Any) -> None:
        self._sync.on_retriever_error(error, run_id=run_id, **kwargs)

    async def on_llm_error(self, error: BaseException, *, run_id: str, **kwargs: Any) -> None:
        self._sync.on_llm_error(error, run_id=run_id, **kwargs)

    async def on_tool_error(self, error: BaseException, *, run_id: str, **kwargs: Any) -> None:
        self._sync.on_tool_error(error, run_id=run_id, **kwargs)

    async def on_chain_error(self, error: BaseException, *, run_id: str, **kwargs: Any) -> None:
        self._sync.on_chain_error(error, run_id=run_id, **kwargs)

    def to_trace(self) -> TraceV01 | None:
        """Produce the trace from the captured run."""
        return self._sync.to_trace()

    def reset(self) -> None:
        """Reset all captured state."""
        self._sync.reset()
