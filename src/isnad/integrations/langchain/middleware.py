"""IsnadMiddleware — grade and gate agent claims the moment they enter.

This is the *policy* layer for LangChain agents: it grades each tool output and
model response against the rijāl registry and gates (quarantines) claims whose
chain is MAWDU — i.e. a REJECTED narrator transmitted them.

Forward-looking: it targets LangChain's ``AgentMiddleware`` API (2026).  The
older callback handler remains the trace-*capture* path; this is the
trace-*gate* path.  The core ``gate()`` function is importable and testable with
no LangChain installed; the ``IsnadMiddleware`` class degrades gracefully when
``langchain.agents.middleware`` is unavailable.

Framing: *"PIIMiddleware stops sensitive data leaving; IsnadMiddleware stops
untrustworthy claims entering."*
"""

from __future__ import annotations

from dataclasses import dataclass

from isnad import Registry, Verdict, grade
from isnad.core.decision import decide
from isnad.critics.base import ContentCritic
from isnad.types import Action, ChainGrade, TransformType

# ── LangChain availability guard (mirrors the callback's pattern) ────────────
_LANGCHAIN_MIDDLEWARE_AVAILABLE = False
try:
    from langchain.agents.middleware import (  # type: ignore[import-not-found]
        AgentMiddleware,
        after_agent,
        after_model,
        before_agent,
        wrap_tool_call,
    )

    _LANGCHAIN_MIDDLEWARE_AVAILABLE = True
except ImportError:  # pragma: no cover - only hit when langchain (full) is absent
    AgentMiddleware = object  # type: ignore[misc,assignment]

    def wrap_tool_call(fn):  # type: ignore[misc]
        return fn

    def after_model(fn):  # type: ignore[misc]
        return fn

    def before_agent(fn):  # type: ignore[misc]
        return fn

    def after_agent(fn):  # type: ignore[misc]
        return fn


@dataclass
class GateResult:
    """The outcome of grading one claim in the middleware."""

    verdict: Verdict
    gated: bool
    action: Action | None = None


def gate(
    claim: str,
    chain: list[str],
    registry: Registry,
    *,
    domain: str = "general",
    quarantine: bool = True,
    transform_types: list[TransformType] | None = None,
    critic: ContentCritic | None = None,
    corpus: list[str] | None = None,
) -> GateResult:
    """Grade a claim's chain and decide whether to gate it.

    Without a critic, gating is TRUE when the chain grade is ``MAWDU`` — a
    REJECTED narrator transmitted the claim — and ``quarantine`` is enabled
    (active containment, no content judgment).

    With a ``critic`` + ``corpus``, the full decision matrix runs: the claim's
    content is criticized against the corpus and routed to serve / review /
    quarantine. Gating is then TRUE for QUARANTINE or
    REJECT_AND_QUARANTINE_NARRATOR — so a contradiction (not just a bad
    narrator) also blocks the claim.

    This function has no LangChain dependency and is the unit-testable core.
    """
    verdict = grade(
        claim,
        chain,
        registry,
        domain=domain,
        transform_types=transform_types,
    )
    chain_grade = verdict.chain_grade

    if critic is not None and corpus is not None:
        content = critic.evaluate(claim, claim.lower(), corpus, domain)
        action = decide(chain_grade, content)
        gated = action in (Action.QUARANTINE, Action.REJECT_AND_QUARANTINE_NARRATOR)
    else:
        action = Action.REJECT_AND_QUARANTINE_NARRATOR if chain_grade == ChainGrade.MAWDU else None
        gated = quarantine and chain_grade == ChainGrade.MAWDU

    return GateResult(verdict=verdict, gated=gated, action=action)


class IsnadMiddleware(AgentMiddleware):  # type: ignore[misc,valid-type]
    """Grade each claim that enters an agent and gate MAWDU chains.

    Args:
        registry: The graded-narrator registry.
        domain: Domain tag for grading.
        quarantine: When True, block (gate) claims whose chain is MAWDU.
    """

    def __init__(
        self,
        registry: Registry,
        *,
        domain: str = "general",
        quarantine: bool = True,
        critic: ContentCritic | None = None,
        corpus: list[str] | None = None,
    ):
        super().__init__()
        self.registry = registry
        self.domain = domain
        self.quarantine = quarantine
        self.critic = critic
        self.corpus = corpus or []

    def _gate(self, claim: str, narrator_id: str, transform: TransformType) -> GateResult:
        # v1 grades a single link (the arriving narrator).  Multi-link chain
        # accumulation across the run is a documented follow-up: it needs a
        # custom AgentState schema to carry the chain between hooks.
        return gate(
            claim,
            [narrator_id],
            self.registry,
            domain=self.domain,
            quarantine=self.quarantine,
            transform_types=[transform],
            critic=self.critic,
            corpus=self.corpus,
        )

    @wrap_tool_call
    def wrap_tool_call(self, request, handler):
        """Grade the tool's output as a DESTRUCTIVE link; gate MAWDU chains."""
        result = handler(request)
        claim = _extract_text(result)
        tool_name = getattr(request, "tool_name", getattr(request, "name", "tool"))
        gate_result = self._gate(claim, tool_name, TransformType.DESTRUCTIVE)
        if gate_result.gated:
            return _quarantined(result, gate_result.verdict)
        return _annotated(result, gate_result.verdict)

    @after_model
    def after_model(self, state, runtime):
        """Grade the model's response as a GENERATIVE link (logging only)."""
        messages = state.get("messages", []) if isinstance(state, dict) else []
        if not messages:
            return None
        last = messages[-1]
        claim = getattr(last, "content", "") or ""
        if claim:
            self._gate(claim, "model", TransformType.GENERATIVE)
        return None

    @before_agent
    def before_agent(self, state, runtime):
        # The registry is already loaded by the caller; nothing to do per-run.
        return None

    @after_agent
    def after_agent(self, state, runtime):
        # Persistence is the caller's responsibility (the registry outlives the run).
        return None


def _extract_text(result: object) -> str:
    """Best-effort claim text from a tool/model result object."""
    for attr in ("content", "output", "result"):
        value = getattr(result, attr, None)
        if isinstance(value, str):
            return value
    if isinstance(result, str):
        return result
    return ""


def _annotated(result: object, verdict: Verdict) -> object:
    """Return the result unchanged; annotation is a no-op in the offline core."""
    return result


def _quarantined(result: object, verdict: Verdict) -> object:
    """Short-circuit a gated (MAWDU) claim.

    With a real AgentMiddleware this would inject a Command that blocks the
    tool result; in the offline core it returns a sentinel so the decision is
    observable and testable.
    """
    return _Quarantined(result, verdict.why)


class _Quarantined:
    """Sentinel for a gated claim (offline core only)."""

    def __init__(self, original: object, why: str):
        self.original = original
        self.why = why
        self.quarantined = True

    def __repr__(self) -> str:  # pragma: no cover
        return f"<quarantined claim: {self.why}>"


__all__ = ["GateResult", "IsnadMiddleware", "gate"]
