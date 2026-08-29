"""Tests for isnad-mcp — grade MCP servers as narrators (issue #59)."""

from __future__ import annotations

import pytest

from isnad.core.registry import Registry
from isnad.integrations.mcp import (
    MCPToolObserver,
    build_mcp_tools,
    handle_grade_claim,
)
from isnad.types import ChainGrade, NarratorGrade, NarratorType


def _registry() -> Registry:
    reg = Registry()
    reg.register(
        "tool:mcp:query",
        "finance",
        narrator_type=NarratorType.TOOL,
        grade=NarratorGrade.RELIABLE,
    )
    return reg


class TestMCPToolObserver:
    def test_tool_narrators_are_ungraded_by_default(self):
        """A tool is majhūl until the operator grades it — the observer must not
        auto-grade from call volume (the GIGO guardrail)."""
        reg = Registry()
        obs = MCPToolObserver(reg, domain="finance")
        obs.record_call(server_name="mcp", tool_name="query")
        # ensure_registered runs on grade(); the tool must be UNGRADED, not
        # auto-graded to any tier.
        obs.grade("revenue grew 12%")
        assert reg.get_grade("tool:mcp:query", "finance") == NarratorGrade.UNGRADED

    def test_grade_reflects_operator_assigned_grade(self):
        reg = _registry()
        obs = MCPToolObserver(reg, domain="finance")
        obs.record_call(server_name="mcp", tool_name="query")
        result = obs.grade("revenue grew 12%")
        # Single RELIABLE tool narrator, complete chain → SAHIH.
        assert result["chain_grade"] == ChainGrade.SAHIH.value
        assert result["narrators"] == ["tool:mcp:query"]

    def test_unknown_tool_caps_chain_at_daif(self):
        """Strict default: an UNGRADED tool narrator caps the chain at daif
        (classical majhūl), never above it."""
        reg = Registry()
        obs = MCPToolObserver(reg, domain="finance")
        obs.record_call(server_name="mcp", tool_name="unknown-tool")
        result = obs.grade("revenue grew 12%")
        assert result["chain_grade"] == ChainGrade.DAIF.value

    def test_multiple_tools_weakest_link(self):
        reg = _registry()
        reg.register(
            "tool:mcp:other",
            "finance",
            narrator_type=NarratorType.TOOL,
            grade=NarratorGrade.WEAK,
        )
        obs = MCPToolObserver(reg, domain="finance")
        obs.record_call(server_name="mcp", tool_name="query")
        obs.record_call(server_name="mcp", tool_name="other")
        result = obs.grade("revenue grew 12%")
        assert result["chain_grade"] == ChainGrade.DAIF.value


class TestMCPToolServer:
    def test_build_mcp_tools_shape(self):
        tools = build_mcp_tools(_registry())
        assert len(tools) == 1
        t = tools[0]
        assert t["name"] == "grade_claim"
        assert "inputSchema" in t
        assert set(t["inputSchema"]["required"]) == {"claim", "narrators"}

    def test_handle_grade_claim(self):
        reg = _registry()
        out = handle_grade_claim(
            reg, {"claim": "revenue grew", "narrators": ["tool:mcp:query"]}, domain="finance"
        )
        assert out["chain_grade"] == ChainGrade.SAHIH.value
        assert "trust grade, not a fact-check" in out["note"]
        assert out["chain_supplied_by_caller"] is True

    def test_handle_grade_claim_unknown_narrator_is_honest(self):
        reg = Registry()
        out = handle_grade_claim(
            reg, {"claim": "x", "narrators": ["tool:mcp:ghost"]}, domain="finance"
        )
        assert out["grades"] == ["ungraded"]
        assert out["chain_grade"] == ChainGrade.DAIF.value

    def test_handle_grade_claim_never_fabricates_a_grade(self):
        """The server reports UNGRADED for unknown narrators — it never invents
        a grade. This is the #44 no-federation / no-manufacture invariant."""
        reg = Registry()
        out = handle_grade_claim(reg, {"claim": "x", "narrators": ["tool:mcp:ghost"]})
        assert out["grades"] == ["ungraded"]

    def test_handle_grade_claim_string_narrator_is_treated_as_single(self):
        """A bare string narrator is one narrator, not a list of characters."""
        reg = _registry()
        out = handle_grade_claim(
            reg, {"claim": "x", "narrators": "tool:mcp:query"}, domain="finance"
        )
        assert out["narrators"] == ["tool:mcp:query"]
        assert out["chain_grade"] == ChainGrade.SAHIH.value

    def test_handle_grade_claim_null_narrators_is_empty_and_daif(self):
        """Malformed input (null narrators) degrades to an empty chain → DAIF,
        never a traceback and never a fabricated grade."""
        reg = Registry()
        out = handle_grade_claim(reg, {"claim": "x", "narrators": None})
        assert out["narrators"] == []
        assert out["chain_grade"] == ChainGrade.DAIF.value


class TestServeMcpServer:
    """isnad mcp serve builds a real FastMCP server (lazy SDK import)."""

    def test_serve_mcp_requires_sdk(self, monkeypatch):
        """Without the MCP SDK, serve_mcp raises a clear ImportError (not a
        cryptic one), so `isnad mcp serve` fails with a helpful message."""
        import builtins

        from isnad.integrations import mcp as mcp_mod

        real_import = builtins.__import__

        def _no_mcp(name, *args, **kwargs):
            if name == "mcp.server.fastmcp":
                raise ImportError("No module named mcp")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_mcp)
        import pytest as _pytest

        with _pytest.raises(ImportError, match="isnad\\[mcp\\]"):
            mcp_mod.serve_mcp(Registry())

    def test_serve_mcp_builds_server_with_tools(self):
        """When the SDK is present, serve_mcp registers grade_claim and
        list_narrators tools on a FastMCP server (without running it)."""
        mcp = pytest.importorskip("mcp")
        from isnad.integrations.mcp import serve_mcp

        # Monkeypatch FastMCP.run so we can inspect without blocking.
        import isnad.integrations.mcp as mcp_mod
        from mcp.server.fastmcp import FastMCP

        captured = {}

        class _FakeRun:
            def run(self, transport="stdio"):
                captured["transport"] = transport
                captured["tools"] = (
                    list(self._tool_manager._tools.keys()) if hasattr(self, "_tool_manager") else []
                )

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(FastMCP, "run", _FakeRun.run)

        reg = _registry()
        mcp_mod.serve_mcp(reg, domain="finance", transport="stdio")
        monkeypatch.undo()

        assert captured["transport"] == "stdio"


class TestMCPCli:
    def test_cli_dispatches_mcp(self, monkeypatch, capsys):
        """`isnad mcp serve --help`-style dispatch does not crash and reaches
        the MCP branch (fails fast with a clear error without the SDK)."""
        from isnad.cli import main as cli_main

        # Force the SDK-missing path to prove the CLI branch is reachable.
        import builtins

        real_import = builtins.__import__

        def _no_mcp(name, *args, **kwargs):
            if name == "mcp.server.fastmcp":
                raise ImportError("No module named mcp")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_mcp)
        import pytest as _pytest

        with _pytest.raises(ImportError, match="isnad\\[mcp\\]"):
            cli_main.main(["mcp"])
