"""IsnadMiddleware — grade and gate agent claims at ingest.

Demonstrates the policy layer in offline mode (no full `langchain` install
required): grade a tool output against the registry and gate (quarantine) the
claim when its chain is MAWDU — a REJECTED narrator transmitted it.

Framing: *"PIIMiddleware stops sensitive data leaving; IsnadMiddleware stops
untrustworthy claims entering."*

Run:  python examples/langchain_middleware_demo.py
"""

from __future__ import annotations

from isnad import Registry
from isnad.integrations.langchain import IsnadMiddleware, gate
from isnad.types import NarratorGrade


def main() -> None:
    print("=" * 68)
    print("IsnadMiddleware — grade and gate at ingest")
    print("=" * 68)

    reg = Registry()
    reg.register("tool:docs-search", "general", grade=NarratorGrade.RELIABLE)
    reg.register("tool:untrusted", "general", grade=NarratorGrade.REJECTED)

    # 1. The testable core: grade a chain and decide whether to gate it.
    print("\n1. gate() — the core decision:")
    clean = gate("the sky is blue", ["tool:docs-search"], reg, domain="general")
    print(f"   clean claim  -> gated={clean.gated} ({clean.verdict.chain_grade.value})")

    bad = gate("a fabricated claim", ["tool:untrusted"], reg, domain="general")
    print(f"   bad claim    -> gated={bad.gated} ({bad.verdict.chain_grade.value})")
    print(f"   why: {bad.verdict.why}")

    # 2. The middleware adapter (offline, stub request/result).
    print("\n2. IsnadMiddleware — wrap_tool_call gates MAWDU chains:")

    class _ToolRequest:
        tool_name = "tool:untrusted"

    class _ToolResult:
        content = "another fabricated claim"

    mw = IsnadMiddleware(reg, domain="general")
    result = mw.wrap_tool_call(_ToolRequest(), lambda req: _ToolResult())
    print(f"   tool:untrusted output -> quarantined={getattr(result, 'quarantined', False)}")

    print("\n" + "=" * 68)
    print("Done.")
    print("=" * 68)


if __name__ == "__main__":
    main()
