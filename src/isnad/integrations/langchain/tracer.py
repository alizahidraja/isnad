"""IsnadTracer — LangChain callback handler for ISNAD provenance.

Observes a LangChain/LangGraph run and records the transmission chain
for each claim/output automatically.  Hooks LLM, chain, tool, and
retriever callbacks to capture each transformation step as an ISNAD
narrator link.

LIMITATIONS:
- The default content critic is a non-functional stub on real text.
  Supply a real critic for practical coverage.
- Corroboration is experimentally untested.
- Seed-grade your known narrators before use.
"""

from __future__ import annotations

import uuid
from typing import Any

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.grading import grade_chain
from isnad.matn import DeterministicRuleCritic
from isnad.core.decision import decide, describe_action
from isnad.core.registry import Registry
from isnad.critics.base import ContentCritic
from isnad.types import (
    Action,
    NarratorGrade,
    TransformType,
)

_LANGCHAIN_AVAILABLE = False
try:
    from langchain_core.callbacks import (
        BaseCallbackHandler,  # type: ignore[import-not-found,unused-ignore]
    )

    _LANGCHAIN_AVAILABLE = True
except ImportError:
    BaseCallbackHandler = object


class IsnadTracer(BaseCallbackHandler):  # type: ignore[misc,valid-type]
    """LangChain callback handler that records ISNAD transmission chains.

    Attach to any LangChain/LangGraph run to automatically build graded
    chains for every output claim.

    Usage:
        from isnad.integrations.langchain import IsnadTracer, seed_registry
        reg = seed_registry({"source:my-docs": "reliable", "gpt-4": "acceptable"})
        tracer = IsnadTracer(registry=reg)
        chain.invoke("...", config={"callbacks": [tracer]})
        print(tracer.report())

    LIMITATIONS: The bundled content critic is a non-functional reference
    stub on real text. For practical coverage, pass `critic=my_critic` to
    the constructor with an LLM- or embedding-backed ContentCritic.
    """

    def __init__(
        self,
        registry: Registry,
        critic: ContentCritic | None = None,
        domain: str = "general",
    ):
        if not _LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is required for IsnadTracer. Install with: pip install isnad[langchain]"
            )
        super().__init__()
        self.registry = registry
        self.critic = critic or DeterministicRuleCritic()
        self.domain = domain

        # Per-run state
        self._run_id = str(uuid.uuid4())[:8]
        self._links: list[ChainLinkSpec] = []
        self._step = 0
        self._graded_claims: list[dict[str, Any]] = []

    # ── Callback hooks ──────────────────────────────────────────

    def on_chain_start(self, serialized: dict[str, Any], inputs: Any, **kwargs: Any) -> None:
        chain_name = serialized.get("name", serialized.get("id", "chain"))
        self._add_link(str(chain_name), TransformType.PASS_THROUGH)

    def on_retriever_end(self, documents: list[Any], *, run_id: str, **kwargs: Any) -> None:
        for doc in documents:
            source = getattr(doc, "metadata", {}).get("source", "document")
            self._add_link(f"retriever:{source}", TransformType.DESTRUCTIVE)

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "tool")
        self._add_link(f"tool:{tool_name}", TransformType.DESTRUCTIVE)

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[Any], **kwargs: Any) -> None:
        model = serialized.get("name", serialized.get("id", "llm"))
        self._add_link(f"model:{model}", TransformType.GENERATIVE)

    def on_chain_end(self, outputs: Any, **kwargs: Any) -> None:
        # Extract claims from chain output
        claim_texts = self._extract_claims(outputs)
        for text in claim_texts:
            chain = Chain(list(self._links))
            link_grades = [
                self.registry.get_grade(link.narrator_id, link.domain) for link in chain.links
            ]
            link_transforms = [link.transform_type for link in chain.links]

            cg = grade_chain(
                link_grades,
                link_transforms,
                is_complete=chain.is_complete,
            )

            cv = self.critic.evaluate(text, text, [], self.domain)
            action = decide(cg, cv)

            self._graded_claims.append(
                {
                    "claim_text": text,
                    "chain": chain,
                    "link_grades": link_grades,
                    "link_transforms": link_transforms,
                    "chain_grade": cg,
                    "content_verdict": cv,
                    "action": action,
                    "description": describe_action(cg, cv),
                }
            )

    # ── Public API ──────────────────────────────────────────────

    def report(self) -> str:
        """Return a human-readable report of all graded claims."""
        if not self._graded_claims:
            return "No claims recorded."

        lines = [
            f"ISNAD Report — {len(self._graded_claims)} claims",
            "=" * 60,
        ]
        for i, gc in enumerate(self._graded_claims):
            cg = gc["chain_grade"]
            action = gc["action"]
            chain = gc["chain"]
            lines.append(f"\nClaim {i + 1}: {gc['claim_text'][:80]}")
            lines.append(f"  Chain: {' → '.join(chain.narrator_ids)}")
            grades = " → ".join(f"{g.value.upper()}" for g in gc["link_grades"])
            lines.append(f"  Grades: {grades}")
            lines.append(f"  Grade: {cg.value.upper()} | Action: {action.value.upper()}")

            if action == Action.REJECT_AND_QUARANTINE_NARRATOR:
                for _j, (link, grade) in enumerate(
                    zip(chain.links, gc["link_grades"], strict=False)
                ):
                    if grade == NarratorGrade.REJECTED:
                        lines.append(f"  ⚠ QUARANTINED: {link.narrator_id} is REJECTED")
                        break
            elif action == Action.REVIEW:
                lines.append(f"  ⚠ HELD FOR REVIEW: content is {gc['content_verdict'].value}")
                lines.append("     (tip: supply an LLM-backed critic for CONSISTENT verdicts)")

        served = sum(
            1
            for gc in self._graded_claims
            if gc["action"] in (Action.SERVE, Action.SERVE_WITH_CAVEAT)
        )
        lines.append(f"\nServed: {served}/{len(self._graded_claims)}")
        lines.append("Note: Default critic is a stub. Supply a real one for coverage.")
        lines.append("See: experiments/s8_gated_vs_ungated/results/RESULTS.md")
        return "\n".join(lines)

    def graded_chains(self) -> list[dict[str, Any]]:
        """Return graded claim data for programmatic use."""
        return self._graded_claims

    # ── Internal ────────────────────────────────────────────────

    def _add_link(self, narrator_id: str, transform_type: TransformType) -> None:
        self._links.append(
            ChainLinkSpec(
                narrator_id=narrator_id,
                step=self._step,
                transform_type=transform_type,
                domain=self.domain,
                trace_id=f"{self._run_id}-{self._step}",
            )
        )
        self._step += 1

    @staticmethod
    def _extract_claims(outputs: Any) -> list[str]:
        """Extract claim texts from chain output."""
        if isinstance(outputs, str):
            return [outputs]
        if isinstance(outputs, dict):
            # Try common keys
            for key in ("output", "answer", "text", "result", "response"):
                if key in outputs:
                    val = outputs[key]
                    if isinstance(val, str):
                        return [val]
                    if isinstance(val, list):
                        return [str(v) for v in val]
            return [str(outputs)]
        if isinstance(outputs, list):
            return [str(o) for o in outputs]
        return [str(outputs)]
