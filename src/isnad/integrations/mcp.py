"""isnad-mcp — grade MCP servers as narrators (issue #59).

The Model Context Protocol (MCP) is the 2025–26 standard for exposing tools to
agents. An MCP *server* is a transmitter of claims (tool outputs), and ISNAD's
graded rijāl registry is the approval/audit layer the MCP ecosystem has been
missing.

This module provides two things, both **duck-typed** (no ``mcp`` import at
module load, so it ships and is unit-testable without the SDK):

1. ``MCPToolObserver`` — record each MCP tool call as a TOOL narrator link and
   grade the resulting chain with the existing ``grade_chain`` + ``Registry``.
2. ``build_mcp_tools`` + ``handle_grade_claim`` — a ``grade_claim`` tool
   (MCP tool-shape description + dispatcher) that exposes the operator's
   registry to an agent, so it can ask "how much should I trust this claim?"
   at runtime.

SECURITY (read before exposing to real agents): ``handle_grade_claim`` is a
**read-oracle over the operator's registry** — it returns grades for whatever
narrator ids the caller names, with no authentication and no allow-list. Serve
it behind your own auth/allow-list; the function itself is a bare library
primitive and deliberately does not assume a trust boundary. It also grades a
**caller-supplied chain**: the names it receives are asserted, not observed, so
the result is always marked ``chain_supplied_by_caller: true`` — an agent must
not treat it as evidence that those narrators actually transmitted the claim.

HONEST LIMITS (the moat, not a sales line):
- Tool narrators stay **UNGRADED by default** (majhūl → capped at ḍaʿīf under
  the strict default). This module never auto-grades a tool from call volume —
  auto-grading a tool from call counts would be GIGO, exactly what the README's
  Scope-and-limitations disclaims.
- The registry-exposing tool returns the *grade the operator already assigned*
  (or UNGRADED); it does not manufacture grades.
- The grade is local to the operator's registry. This module never imports a
  grade from another operator (the #44 no-federation invariant).
"""

from __future__ import annotations

from dataclasses import dataclass

from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.types import NarratorGrade, NarratorType, TransformType


@dataclass
class ToolCallRecord:
    """One observed MCP tool invocation, reduced to ISNAD-relevant fields."""

    tool_name: str
    server_name: str = "mcp"
    domain: str = "general"

    @property
    def narrator_id(self) -> str:
        """The registry key for this tool narrator: ``tool:<server>:<name>``."""
        return f"tool:{self.server_name}:{self.tool_name}"


class MCPToolObserver:
    """Record MCP tool calls as TOOL narrator links and grade the chain.

    Usage (with the MCP Python SDK installed by the caller):

        from isnad.integrations.mcp import MCPToolObserver

        obs = MCPToolObserver(registry, domain="finance")
        # per tool call:
        obs.record_call(tool_name="query", server_name="data-warehouse")
        # when the agent produces a claim from those tools:
        result = obs.grade("revenue grew 12% YoY")
        print(result["chain_grade"])

    The observer is a duck-typed recorder: it does not import the MCP SDK, so it
    can be wired into any MCP client by the caller at the ``call_tool`` site.
    """

    def __init__(
        self,
        registry: Registry,
        domain: str = "general",
        *,
        lenient_unknown: bool = False,
    ) -> None:
        self.registry = registry
        self.domain = domain
        self.lenient_unknown = lenient_unknown
        self._calls: list[ToolCallRecord] = []

    def record_call(self, *, tool_name: str, server_name: str = "mcp") -> None:
        """Record one tool call in order (the isnād of tool transmissions)."""
        self._calls.append(
            ToolCallRecord(tool_name=tool_name, server_name=server_name, domain=self.domain)
        )

    def clear(self) -> None:
        self._calls.clear()

    def _ensure_registered(self, rec: ToolCallRecord) -> None:
        """Register the tool narrator as UNGRADED TOOL if not already present.

        Never assigns a grade — a tool is majhūl until the operator seeds or
        logs evidence. Registering the narrator (with no grade) lets the
        registry track it without over-claiming its reliability.
        """
        if self.registry.get(rec.narrator_id, rec.domain) is None:
            self.registry.register(
                rec.narrator_id,
                rec.domain,
                narrator_type=NarratorType.TOOL,
                grade=NarratorGrade.UNGRADED,
            )

    def grade(self, claim: str) -> dict[str, object]:
        """Grade a claim transmitted through the recorded tool calls.

        The chain is the ordered sequence of tool narrators; each is a
        DESTRUCTIVE link (a tool output can only lose or corrupt information,
        never recover upstream loss). Weakest-link, completeness-aware.
        """
        narrators = [rec.narrator_id for rec in self._calls]
        for rec in self._calls:
            self._ensure_registered(rec)
        # Look up each narrator by the domain captured at record time — a
        # narrator graded in rec.domain must not be queried under a later
        # self.domain reassignment.
        grades = [self.registry.get_grade(rec.narrator_id, rec.domain) for rec in self._calls]
        chain_grade = grade_chain(
            grades,
            [TransformType.DESTRUCTIVE] * len(grades),
            is_complete=bool(narrators),
            lenient_unknown=self.lenient_unknown,
        )
        return {
            "claim": claim,
            "narrators": narrators,
            "grades": [g.value for g in grades],
            "chain_grade": chain_grade.value,
        }


def build_mcp_tools(registry: Registry, domain: str = "general") -> list[dict[str, object]]:
    """A ``grade_claim`` tool definition (MCP JSON-RPC tool shape) that exposes
    the operator's registry — grades only, never manufactured, never imported.

    The returned list is a plain MCP ``tools/list``-shaped description; the
    caller serves it through their MCP server and dispatches to
    ``handle_grade_claim``. Duck-typed: no MCP SDK import.
    """
    return [
        {
            "name": "grade_claim",
            "description": (
                "Grade how much to trust a claim, from the local ISNAD registry: "
                "returns the weakest-link chain grade (sahih/hasan/daif/mawdu) for "
                "the narrators the caller names. Grades are operator-assigned; this "
                "does not fact-check the claim."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "The claim text."},
                    "narrators": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered narrator ids (source/model/tool names).",
                    },
                },
                "required": ["claim", "narrators"],
            },
        }
    ]


def handle_grade_claim(
    registry: Registry,
    arguments: dict[str, object],
    domain: str = "general",
    *,
    lenient_unknown: bool = False,
) -> dict[str, object]:
    """Serve a ``grade_claim`` MCP tool call. Grades the named chain, honestly.

    Returns the grade and a human-readable reason. Never fabricates a grade for
    an unknown narrator — it is reported as UNGRADED and the chain is capped
    accordingly. The chain is **caller-supplied**: the result is always marked
    ``chain_supplied_by_caller: true`` so a consumer cannot mistake it for
    observed transmission.

    This function is a bare library primitive: it performs no authentication and
    no narrator allow-listing. The caller (an MCP server) owns that boundary.
    """
    claim = str(arguments.get("claim") or "").strip()
    raw_narrators = arguments.get("narrators")
    if isinstance(raw_narrators, str):
        # A bare string is not a list of narrators — treat it as a single
        # narrator rather than silently iterating characters.
        raw_narrators = [raw_narrators]
    if not isinstance(raw_narrators, list):
        raw_narrators = []
    narrators = [str(n) for n in raw_narrators]
    # Never report a non-empty chain as complete when the caller supplied no
    # narrators; an empty chain grades DAIF (munqaṭiʿ), honestly.
    grades = [registry.get_grade(n, domain) for n in narrators]
    chain_grade = grade_chain(
        grades,
        [TransformType.PASS_THROUGH] * len(grades),
        is_complete=bool(narrators),
        lenient_unknown=lenient_unknown,
    )
    return {
        "claim": claim,
        "chain_grade": chain_grade.value,
        "narrators": narrators,
        "grades": [g.value for g in grades],
        "chain_supplied_by_caller": True,
        "note": (
            "Grades are operator-assigned from the local registry; this is a "
            "trust grade, not a fact-check. The chain is caller-supplied and "
            "unverified."
        ),
    }


__all__ = ["MCPToolObserver", "ToolCallRecord", "build_mcp_tools", "handle_grade_claim"]
