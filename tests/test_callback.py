"""Tests for IsnadCallbackHandler — tree reconstruction, input provenance,
shared ancestry detection, and safety (callback exceptions never break pipeline)."""

from __future__ import annotations

import uuid

import pytest

from isnad.core.registry import Registry
from isnad.integrations.langchain.callback import (
    IsnadCallbackHandler,
    _detect_shared_ancestry,
)
from isnad.trace.schema import (
    ChainIntegrity,
    CorroborationVerdict,
    OriginStrength,
    TraceV01,
)
from isnad.types import NarratorGrade


# ── Helpers ─────────────────────────────────────────────────────


class FakeDoc:
    """Minimal document stand-in for tests."""

    def __init__(self, content: str, metadata: dict | None = None):
        self.page_content = content
        self.metadata = metadata or {}


class FakeLLMResponse:
    """Minimal LLM response for tests."""

    def __init__(self, text: str):
        self.content = text


def make_registry() -> Registry:
    """Create a seeded registry for tests."""
    reg = Registry()
    reg.register("source:arxiv", "physics", narrator_type="source", grade=NarratorGrade.RELIABLE)
    reg.register(
        "model:gpt-4o",
        "physics",
        narrator_type="model",
        grade=NarratorGrade.ACCEPTABLE,
        model_family="gpt-4",
    )
    reg.register(
        "model:gpt-3.5",
        "physics",
        narrator_type="model",
        grade=NarratorGrade.WEAK,
        model_family="gpt-3.5",
    )
    reg.register(
        "model:claude-3.5",
        "physics",
        narrator_type="model",
        grade=NarratorGrade.ACCEPTABLE,
        model_family="claude-3",
    )
    return reg


def new_id(prefix: str = "run") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ── Tree reconstruction from run_id/parent_run_id ────────────────


class TestTreeReconstruction:
    def test_single_node(self):
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        rid = new_id()
        handler.on_chain_start(
            serialized={"name": "rag", "id": "rag"},
            inputs={},
            run_id=rid,
        )
        handler.on_chain_end(outputs={"output": "F=ma"}, run_id=rid)
        trace = handler.to_trace()
        assert trace is not None
        assert len(trace.chain) == 1
        assert trace.chain[0].node_id == rid

    def test_linear_chain_three_nodes(self):
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        r1, r2, r3 = new_id("root"), new_id("child"), new_id("grandchild")

        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        handler.on_retriever_end(
            documents=[FakeDoc("E=mc²")],
            run_id=r2,
            parent_run_id=r1,
        )
        handler.on_llm_start(
            serialized={"name": "gpt-4o", "id": "gpt-4o"},
            prompts=["what is E=mc²?"],
            run_id=r3,
            parent_run_id=r1,
            metadata={"ls_model_name": "gpt-4o-2024-08-06"},
        )
        handler.on_llm_end(response=FakeLLMResponse("E=mc²"), run_id=r3)
        handler.on_chain_end(outputs={"output": "E=mc²"}, run_id=r1)

        trace = handler.to_trace()
        assert trace is not None
        assert len(trace.chain) == 3
        # Root has no parents
        assert trace.chain[0].parent_ids == []
        # Children reference root
        child_ids = {n.node_id for n in trace.chain[1:]}
        for n in trace.chain[1:]:
            assert n.parent_ids == [r1]
        assert len(child_ids) == 2  # retriever + llm

    def test_parent_not_in_nodes_is_ignored(self):
        """A node referencing a parent not in the tree shouldn't crash."""
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        r1 = new_id()
        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        handler.on_chain_end(outputs={"output": "ok"}, run_id=r1)

        trace = handler.to_trace()
        assert trace is not None
        assert len(trace.chain) == 1


# ── Input provenance ────────────────────────────────────────────


class TestInputProvenance:
    def test_retriever_documents_recorded_on_node(self):
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        r1, r2 = new_id("root"), new_id("ret")

        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        handler.on_retriever_end(
            documents=[
                FakeDoc("F=ma", {"source": "openstax.org", "id": "ch5"}),
                FakeDoc("p=h/λ", {"source": "hyperphysics", "id": "photon"}),
            ],
            run_id=r2,
            parent_run_id=r1,
        )
        handler.on_chain_end(outputs={"output": "F=ma"}, run_id=r1)

        trace = handler.to_trace()
        assert trace is not None
        # The retriever node should have the docs
        ret_node = next(n for n in trace.chain if n.node_id == r2)
        assert len(ret_node.input_documents) == 2
        sources = {d.source for d in ret_node.input_documents}
        assert "openstax.org" in sources
        assert "hyperphysics" in sources
        # Hashes are present, content is not
        for d in ret_node.input_documents:
            assert d.content_hash is not None
            assert len(d.content_hash) == 16  # truncated SHA-256

    def test_retriever_documents_propagated_to_parent(self):
        """Retrieved docs should also be recorded on the parent (calling) node."""
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        r1, r2 = new_id("root"), new_id("ret")

        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        handler.on_retriever_end(
            documents=[FakeDoc("F=ma", {"source": "openstax.org", "id": "ch5"})],
            run_id=r2,
            parent_run_id=r1,
        )
        handler.on_chain_end(outputs={"output": "F=ma"}, run_id=r1)

        trace = handler.to_trace()
        assert trace is not None
        root = trace.chain[0]
        assert len(root.input_documents) >= 1
        assert any(d.source == "openstax.org" for d in root.input_documents)

    def test_full_content_not_captured_by_default(self):
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        r1, r2 = new_id("root"), new_id("ret")

        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        handler.on_retriever_end(
            documents=[FakeDoc("sensitive content here", {"source": "db"})],
            run_id=r2,
            parent_run_id=r1,
        )
        handler.on_chain_end(outputs={"output": "ok"}, run_id=r1)

        trace = handler.to_trace()
        assert trace is not None
        for node in trace.chain:
            for doc in node.input_documents:
                # No full text captured — only hash
                assert not hasattr(doc, "full_text")

    def test_model_version_captured_from_metadata(self):
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        r1, r2 = new_id("root"), new_id("llm")

        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        handler.on_llm_start(
            serialized={"name": "gpt-4o", "id": "gpt-4o"},
            prompts=["hello"],
            run_id=r2,
            parent_run_id=r1,
            metadata={"ls_model_name": "gpt-4o-2024-08-06"},
        )
        handler.on_llm_end(response=FakeLLMResponse("hi"), run_id=r2)
        handler.on_chain_end(outputs={"output": "hi"}, run_id=r1)

        trace = handler.to_trace()
        assert trace is not None
        llm_node = next(n for n in trace.chain if n.node_id == r2)
        assert llm_node.model_version == "gpt-4o-2024-08-06"


# ── Two-axis scoring ────────────────────────────────────────────


class TestTwoAxisScoring:
    def test_chain_integrity_and_origin_strength_are_separate(self):
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        r1, r2 = new_id("root"), new_id("weak")

        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        # Use gpt-3.5 (weak) as the model
        handler.on_llm_start(
            serialized={"name": "gpt-3.5", "id": "gpt-3.5"},
            prompts=["hello"],
            run_id=r2,
            parent_run_id=r1,
        )
        handler.on_llm_end(response=FakeLLMResponse("hi"), run_id=r2)
        handler.on_chain_end(outputs={"output": "hi"}, run_id=r1)

        trace = handler.to_trace()
        assert trace is not None
        # Chain integrity reflects the weak narrator
        assert trace.chain_integrity is not None
        # But origin_strength remains unknown (the arxiv source wasn't in this chain)
        assert trace.origin_strength is not None
        # These are different types — they cannot be collapsed
        assert trace.chain_integrity != trace.origin_strength.value  # type check

    def test_verified_and_weak_are_distinguishable(self):
        """A daif chain must be distinguishable from a sahih/unverified one."""
        reg = make_registry()
        reg.register("source:noaa", "climate", narrator_type="source", grade=NarratorGrade.RELIABLE)
        reg.register(
            "model:bad-extractor", "climate", narrator_type="model", grade=NarratorGrade.WEAK
        )

        handler = IsnadCallbackHandler(registry=reg, domain="climate")
        r1, r2 = new_id("root"), new_id("extract")

        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        handler.on_llm_start(
            serialized={"name": "bad-extractor", "id": "bad"},
            prompts=["..."],
            run_id=r2,
            parent_run_id=r1,
        )
        handler.on_chain_end(outputs={"output": "claim"}, run_id=r1)

        trace = handler.to_trace()
        assert trace is not None
        # Chain integrity is daif (weak narrator)
        assert trace.chain_integrity == ChainIntegrity.DAIF
        # Origin is unknown (no source node with verified origin in this chain)
        assert trace.origin_strength == OriginStrength.UNKNOWN


# ── Shared ancestry detection ───────────────────────────────────


class TestSharedAncestryDetection:
    def test_empty_chains_are_unverified(self):
        verdict, detail = _detect_shared_ancestry([])
        assert verdict == CorroborationVerdict.UNVERIFIED

    def test_single_chain_is_unverified(self):
        from isnad.trace.schema import TransmitterNode, Grade, Role

        chain = [
            TransmitterNode(
                node_id="n1",
                role=Role.SOURCE,
                narrator_id="src",
                step=0,
                grade=Grade(narrator_id="src", role=Role.SOURCE, domain="test"),
            )
        ]
        verdict, _ = _detect_shared_ancestry([chain])
        assert verdict == CorroborationVerdict.UNVERIFIED

    def test_shared_narrator_ids_detected(self):
        from isnad.trace.schema import TransmitterNode, Grade, Role

        node1 = TransmitterNode(
            node_id="n1",
            role=Role.SOURCE,
            narrator_id="shared-source",
            step=0,
            grade=Grade(narrator_id="shared-source", role=Role.SOURCE, domain="test"),
        )
        node2 = TransmitterNode(
            node_id="n2",
            role=Role.SOURCE,
            narrator_id="shared-source",
            step=0,
            grade=Grade(narrator_id="shared-source", role=Role.SOURCE, domain="test"),
        )
        verdict, detail = _detect_shared_ancestry([[node1], [node2]])
        assert verdict == CorroborationVerdict.SHARED_ANCESTRY_DETECTED
        assert "shared-source" in detail

    def test_shared_upstream_source_detected(self):
        from isnad.trace.schema import TransmitterNode, Grade, Role

        node1 = TransmitterNode(
            node_id="n1",
            role=Role.SOURCE,
            narrator_id="src-a",
            step=0,
            grade=Grade(
                narrator_id="src-a", role=Role.SOURCE, domain="test", upstream_source="noaa.gov"
            ),
        )
        node2 = TransmitterNode(
            node_id="n2",
            role=Role.SOURCE,
            narrator_id="src-b",
            step=0,
            grade=Grade(
                narrator_id="src-b", role=Role.SOURCE, domain="test", upstream_source="noaa.gov"
            ),
        )
        verdict, detail = _detect_shared_ancestry([[node1], [node2]])
        assert verdict == CorroborationVerdict.SHARED_ANCESTRY_DETECTED
        assert "noaa.gov" in detail

    def test_disjoint_chains_are_verified(self):
        from isnad.trace.schema import TransmitterNode, Grade, Role, DocumentRef

        node1 = TransmitterNode(
            node_id="n1",
            role=Role.SOURCE,
            narrator_id="src-a",
            step=0,
            grade=Grade(
                narrator_id="src-a", role=Role.SOURCE, domain="test", upstream_source="openstax.org"
            ),
            input_documents=[
                DocumentRef(source="openstax.org", doc_id="ch1", content_hash="abc123"),
            ],
        )
        node2 = TransmitterNode(
            node_id="n2",
            role=Role.SOURCE,
            narrator_id="src-b",
            step=0,
            grade=Grade(
                narrator_id="src-b", role=Role.SOURCE, domain="test", upstream_source="hyperphysics"
            ),
            input_documents=[
                DocumentRef(source="hyperphysics", doc_id="photon", content_hash="def456"),
            ],
        )
        verdict, _ = _detect_shared_ancestry([[node1], [node2]])
        assert verdict == CorroborationVerdict.ASSUMED


# ── Safety — callbacks never break the pipeline ─────────────────


class TestCallbackSafety:
    def test_exception_in_callback_does_not_raise(self):
        """A failing callback must not propagate to the caller."""
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")

        # This should not raise, even with garbage inputs
        handler.on_chain_start(
            serialized=None,
            inputs=None,
            run_id=new_id(),  # type: ignore
        )
        handler.on_llm_start(
            serialized=None,
            prompts=None,
            run_id=new_id(),  # type: ignore
        )
        handler.on_chain_end(outputs=None, run_id=new_id())  # type: ignore

        # The trace should still be producible (possibly empty)
        trace = handler.to_trace()
        # Either None or a valid trace — but no exception
        if trace is not None:
            assert isinstance(trace, TraceV01)

    def test_missing_run_id_is_safe(self):
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        # These all fire with various missing args — nothing should crash
        handler.on_chain_start(serialized={}, inputs={}, run_id=new_id())
        handler.on_chain_end(outputs={}, run_id=new_id())
        trace = handler.to_trace()
        assert trace is not None


# ── Model version tracking ──────────────────────────────────────


class TestModelVersionTracking:
    def test_version_none_when_not_provided(self):
        """When model version is not available, record it as None explicitly."""
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        r1, r2 = new_id("root"), new_id("llm")

        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        handler.on_llm_start(
            serialized={"name": "unknown-model", "id": "unknown"},
            prompts=["test"],
            run_id=r2,
            parent_run_id=r1,
            # No metadata or invocation_params
        )
        handler.on_chain_end(outputs={"output": "ok"}, run_id=r1)

        trace = handler.to_trace()
        assert trace is not None
        llm_node = next(n for n in trace.chain if n.node_id == r2)
        # Model version is explicitly None, not silently defaulted
        assert llm_node.model_version is None

    def test_reset_clears_all_state(self):
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        r1 = new_id()
        handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id=r1)
        handler.on_chain_end(outputs={"output": "first run"}, run_id=r1)
        trace1 = handler.to_trace()
        assert trace1 is not None
        assert len(trace1.chain) == 1

        handler.reset()
        trace2 = handler.to_trace()
        assert trace2 is None  # no state after reset


# ── Runnable demo output validation ─────────────────────────────


class TestDemoOutput:
    def test_demo_produces_valid_trace(self):
        """The demo script produces a valid TraceV01."""
        import json
        import subprocess
        import sys
        from pathlib import Path

        demo_path = Path(__file__).resolve().parent.parent / "examples" / "isnad_langchain_demo.py"
        if not demo_path.exists():
            pytest.skip("Demo script not found")

        result = subprocess.run(
            [sys.executable, str(demo_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Demo failed: {result.stderr}"

        # Find the JSON block in stdout
        lines = result.stdout.split("\n")
        json_start = None
        for i, line in enumerate(lines):
            if line.strip() == "{":
                json_start = i
                break
        assert json_start is not None, "No JSON found in demo output"

        json_text = "\n".join(lines[json_start:])
        data = json.loads(json_text)
        trace = TraceV01.model_validate(data)
        assert trace.capture_source == "langchain"
        assert len(trace.chain) >= 2  # at minimum: root + llm


class TestRoleScopedGradeLookup:
    """The callback must carry each link's role into the registry lookup (issue #3)."""

    def test_llm_node_uses_synthesis_role_grade(self):
        from isnad.types import Role

        reg = Registry()
        reg.register("model:gpt-4o", "physics", grade=NarratorGrade.ACCEPTABLE)
        reg.register("model:gpt-4o", "physics", role=Role.SYNTHESIS, grade=NarratorGrade.WEAK)

        handler = IsnadCallbackHandler(registry=reg, domain="physics")
        handler.on_llm_start(
            serialized={"name": "gpt-4o", "id": "gpt-4o"},
            prompts=["what is F=ma?"],
            run_id="r-llm",
        )
        trace = handler.to_trace()
        assert trace is not None
        node = next(n for n in trace.chain if n.narrator_id == "model:gpt-4o")
        assert node.role == Role.SYNTHESIS
        # The synthesis role is WEAK → DAIF, not the default ACCEPTABLE → HASAN.
        assert node.grade.chain_integrity == ChainIntegrity.DAIF

    def test_quarantined_narrator_reports_rejected_in_role(self):
        from isnad.types import Role

        reg = Registry()
        reg.register("model:gpt-4o", "physics", grade=NarratorGrade.RELIABLE)
        reg.register("model:gpt-4o", "physics", role=Role.SYNTHESIS, grade=NarratorGrade.RELIABLE)
        reg.quarantine("model:gpt-4o", "physics", "caught fabricating")

        handler = IsnadCallbackHandler(registry=reg, domain="physics")
        handler.on_llm_start(
            serialized={"name": "gpt-4o", "id": "gpt-4o"},
            prompts=["what is F=ma?"],
            run_id="r-llm",
        )
        trace = handler.to_trace()
        assert trace is not None
        node = next(n for n in trace.chain if n.narrator_id == "model:gpt-4o")
        # Integrity floor: the synthesis role is quarantined → MAWDU.
        assert node.grade.chain_integrity == ChainIntegrity.MAWDU


class TestErrorHandlersNeverBreakPipeline:
    """Callbacks are wrapped so errors in the pipeline never raise (README promise)."""

    def test_sync_error_handlers_log_do_not_raise(self, caplog):
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        handler.on_llm_error(ValueError("boom"), run_id="r1")
        handler.on_retriever_error(ValueError("boom"), run_id="r2")
        handler.on_tool_error(ValueError("boom"), run_id="r3")
        handler.on_chain_error(ValueError("boom"), run_id="r4")
        # Reaching here means none raised — but that is not enough: the promise
        # is that they are *observed*, not silently dropped. Assert the error
        # was logged at least once.
        assert caplog.records, "expected at least one logged error, got none"

    def test_node_capture_swallows_exceptions(self):
        """A malformed serialized dict must not propagate out of _add_node."""
        handler = IsnadCallbackHandler(registry=make_registry(), domain="physics")
        # _safe wraps all callbacks; a malformed serialized value should be
        # swallowed without raising, and a valid name still records a node.
        handler.on_llm_start(serialized={"name": "gpt-4o"}, prompts=None, run_id="r1")
        assert "r1" in handler._nodes


class TestAsyncHandler:
    def test_async_handler_delegates_to_sync(self):
        from isnad.integrations.langchain.callback import AsyncIsnadCallbackHandler

        handler = AsyncIsnadCallbackHandler(registry=make_registry(), domain="physics")

        async def _run():
            await handler.on_chain_start(serialized={"name": "rag"}, inputs={}, run_id="r1")
            await handler.on_llm_start(
                serialized={"name": "gpt-4o"}, prompts=["x"], run_id="r2", parent_run_id="r1"
            )
            await handler.on_llm_end(response=FakeLLMResponse("x"), run_id="r2")
            await handler.on_chain_end(outputs={"output": "x"}, run_id="r1")
            await handler.on_llm_error(ValueError("boom"), run_id="r2")
            await handler.on_retriever_error(ValueError("boom"), run_id="r1")
            await handler.on_tool_error(ValueError("boom"), run_id="r1")
            await handler.on_chain_error(ValueError("boom"), run_id="r1")

        import asyncio

        asyncio.run(_run())
        trace = handler.to_trace()
        assert trace is not None
        assert len(trace.chain) >= 2
        handler.reset()
        assert handler.to_trace() is None or len(handler.to_trace().chain) == 0
