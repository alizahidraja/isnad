"""Tests for IsnadMiddleware's testable core (gate) and the offline adapter.

The middleware targets LangChain's AgentMiddleware API (not installed here),
so these tests exercise ``gate()`` — the grading/gating core — and the
``IsnadMiddleware`` adapter with stub objects, not a live agent runtime.
"""

from __future__ import annotations

from isnad import Registry, grade
from isnad.integrations.langchain.middleware import GateResult, IsnadMiddleware, gate
from isnad.types import ChainGrade, NarratorGrade


def _registry(*narrators: tuple[str, NarratorGrade]) -> Registry:
    reg = Registry()
    for nid, g in narrators:
        reg.register(nid, "physics", grade=g)
    return reg


class TestGate:
    def test_rejected_narrator_gates(self) -> None:
        reg = _registry(("model:bad", NarratorGrade.REJECTED))
        r = gate("x", ["model:bad"], reg, domain="physics")
        assert r.gated is True
        assert r.verdict.chain_grade == ChainGrade.MAWDU

    def test_reliable_narrator_does_not_gate(self) -> None:
        reg = _registry(("model:good", NarratorGrade.RELIABLE))
        r = gate("x", ["model:good"], reg, domain="physics")
        assert r.gated is False
        assert r.verdict.chain_grade == ChainGrade.SAHIH

    def test_quarantine_false_never_gates(self) -> None:
        reg = _registry(("model:bad", NarratorGrade.REJECTED))
        r = gate("x", ["model:bad"], reg, domain="physics", quarantine=False)
        assert r.gated is False  # grading still happens, gating is off

    def test_gate_is_deterministic(self) -> None:
        reg = _registry(("model:bad", NarratorGrade.REJECTED))
        a = gate("x", ["model:bad"], reg, domain="physics")
        b = gate("x", ["model:bad"], reg, domain="physics")
        assert a.gated == b.gated and a.verdict.why == b.verdict.why


class TestMiddlewareAdapter:
    def test_middleware_wraps_tool_call_and_gates(self) -> None:
        reg = _registry(("tool:bad", NarratorGrade.REJECTED))
        mw = IsnadMiddleware(reg, domain="physics")

        class _Req:
            tool_name = "tool:bad"

        class _Res:
            content = "a fabricated claim"

        result = mw.wrap_tool_call(_Req(), lambda req: _Res())
        assert getattr(result, "quarantined", False) is True

    def test_middleware_passes_clean_tool_call(self) -> None:
        reg = _registry(("tool:good", NarratorGrade.RELIABLE))
        mw = IsnadMiddleware(reg, domain="physics")

        class _Req:
            tool_name = "tool:good"

        class _Res:
            content = "a sound claim"

        result = mw.wrap_tool_call(_Req(), lambda req: _Res())
        assert getattr(result, "quarantined", False) is False

    def test_middleware_degrades_without_langchain(self) -> None:
        # The import guard falls back to object; the class must still construct.
        from isnad.integrations.langchain import middleware as mw_mod

        assert mw_mod._LANGCHAIN_MIDDLEWARE_AVAILABLE is False
        reg = _registry(("tool:good", NarratorGrade.RELIABLE))
        mw = IsnadMiddleware(reg, domain="physics")
        assert mw.registry is reg
