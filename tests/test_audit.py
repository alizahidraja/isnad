"""Tests for the audit evidence layer — AuditRecord, exporter, integrity, chainlog.

The core guarantee: an AuditRecord is a *self-authenticating evidence artifact*.
Its record_hash is SHA-256 over the RFC 8785-canonical form of its own payload,
so tampering is detectable by recomputation — and it never claims compliance.
"""

from __future__ import annotations

import json

import pytest

from isnad import __version__
from isnad.audit import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    GradingStrategy,
    HumanOversight,
    Integrity,
    SourceDocument,
    WeakestLink,
)
from isnad.audit.canonical import canonical_hash, canonical_json, sha256_hex
from isnad.audit.chainlog import append_record, verify_chain
from isnad.audit.schema import RECORD_VERSION, new_record_id, utcnow_iso


class TestCanonicalJson:
    def test_key_order_is_irrelevant(self) -> None:
        assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})

    def test_nested_and_unicode(self) -> None:
        assert canonical_json({"x": ["a", 1, True, None], "k": "p=mv"}) == (
            '{"k":"p=mv","x":["a",1,true,null]}'
        )

    def test_jcs_control_char_short_escapes(self) -> None:
        """RFC 8785 §3.2.2.2 mandates the SHORT escapes \\n \\t \\r \\b \\f for
        those control characters (NOT \\uXXXX), and raw UTF-8 for non-ASCII.
        Pin both so a future 'fix' that switches to \\uXXXX escapes — or a
        regression to ASCII-escaping non-ASCII — fails."""
        assert canonical_json({"x": "a\nb\tc\rd"}) == '{"x":"a\\nb\\tc\\rd"}'
        assert canonical_json({"x": "héllo"}) == '{"x":"héllo"}'

    def test_sha256_known_vector(self) -> None:
        assert sha256_hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _record() -> AuditRecord:
    return AuditRecord(
        record_id=new_record_id(),
        record_version=RECORD_VERSION,
        generated_at=utcnow_iso(),
        claim_id="c1",
        claim_text="p = mv",
        final_grade="hasan",
        grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
        chain=[
            ChainNodeAudit("src", "dataset", "reliable", "r"),
            ChainNodeAudit("m", "model", "acceptable", "r", upstream_ids=["src"]),
        ],
        weakest_link=WeakestLink("m", "acceptable", "lowest grade"),
        source_documents=[SourceDocument("https://e/x")],
        human_oversight=[],
        environment=Environment(__version__, "3.12", "darwin"),
    )


class TestAuditRecord:
    def test_hash_is_over_payload_without_integrity(self) -> None:
        rec = _record()
        rec.integrity = Integrity(record_hash=canonical_hash(rec.to_dict(include_integrity=False)))
        # Recomputing from the same payload yields the same hash.
        assert rec.integrity.record_hash == canonical_hash(rec.to_dict(include_integrity=False))
        # The full dict (with integrity) hashes differently.
        assert rec.integrity.record_hash != canonical_hash(rec.to_dict(include_integrity=True))

    def test_tampering_changes_hash(self) -> None:
        rec = _record()
        rec.integrity = Integrity(record_hash=canonical_hash(rec.to_dict(include_integrity=False)))
        rec.claim_text = "p = h/lambda"  # tamper
        assert rec.integrity.record_hash != canonical_hash(rec.to_dict(include_integrity=False))

    def test_to_dict_shape(self) -> None:
        d = _record().to_dict()
        assert set(d) == {
            "record_id",
            "record_version",
            "generated_at",
            "claim_id",
            "claim_text",
            "final_grade",
            "grading_strategy",
            "chain",
            "weakest_link",
            "source_documents",
            "human_oversight",
            "environment",
            "integrity",
        }


class TestChainLog:
    def test_intact_chain_verifies(self, tmp_path) -> None:
        p = tmp_path / "chain.jsonl"
        append_record(p, "r0", "h0")
        append_record(p, "r1", "h1")
        assert verify_chain(p) is None

    def test_tampered_chain_breaks(self, tmp_path) -> None:
        p = tmp_path / "chain.jsonl"
        append_record(p, "r0", "h0")
        append_record(p, "r1", "h1")
        # Rewrite the first entry's hash.
        lines = p.read_text().splitlines()
        d = json.loads(lines[0])
        d["record_hash"] = "forged"
        lines[0] = json.dumps(d, separators=(",", ":"))
        p.write_text("\n".join(lines) + "\n")
        break_ = verify_chain(p)
        assert break_ is not None
        assert break_.index == 1  # the link after the forged entry

    def test_empty_chain_verifies(self, tmp_path) -> None:
        assert verify_chain(tmp_path / "nonexistent.jsonl") is None

    def test_malformed_chain_reports_malformed(self, tmp_path) -> None:
        """#108: a malformed chain line returns a ChainBreak, not a crash."""
        p = tmp_path / "chain.jsonl"
        append_record(p, "r0", "h0")
        append_record(p, "r1", "h1")
        lines = p.read_text().splitlines()
        lines[1] = "{not json"
        p.write_text("\n".join(lines) + "\n")
        break_ = verify_chain(p)
        assert break_ is not None
        assert break_.index == 1
        assert "invalid JSON" in break_.reason

    def test_missing_key_chain_reports_malformed(self, tmp_path) -> None:
        """#108: a missing key returns a ChainBreak with a clear reason."""
        p = tmp_path / "chain.jsonl"
        append_record(p, "r0", "h0")
        lines = p.read_text().splitlines()
        d = json.loads(lines[0])
        del d["record_hash"]
        lines[0] = json.dumps(d)
        p.write_text("\n".join(lines) + "\n")
        break_ = verify_chain(p)
        assert break_ is not None
        assert "record_hash" in break_.reason


class TestExporter:
    def test_builds_record_with_weakest_link_and_hash(self, tmp_path) -> None:
        import tempfile

        from sqlalchemy.orm import Session

        from isnad.audit import build_audit_record
        from isnad.core.chain import (
            Chain,
            ChainLinkSpec,
            hash_claim_text,
            normalize_claim_text,
            store_claim,
        )
        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine
        from isnad.types import NarratorGrade, NarratorType

        with tempfile.TemporaryDirectory() as d:
            url = f"sqlite:///{d}/a.db"
            reset_engine()
            init_db(url)
            engine = create_engine_from_url(url)

            with Session(engine) as s:
                rdb = RegistryDB(session=s)
                rdb.registry.register(
                    "src",
                    "physics",
                    grade=NarratorGrade.RELIABLE,
                    narrator_type=NarratorType.SOURCE,
                )
                rdb.registry.register("model-x", "physics", grade=NarratorGrade.ACCEPTABLE)
                chain = Chain([
                    ChainLinkSpec("src", 0, domain="physics"),
                    ChainLinkSpec("model-x", 1, domain="physics"),
                ])
                store_claim(s, "p = mv", "page", chain, chain_grade="hasan")
                s.commit()
                cid = hash_claim_text(normalize_claim_text("p = mv"))
                rec = build_audit_record(cid, s, rdb.registry)

            assert rec.final_grade == "hasan"
            assert rec.weakest_link.narrator_id == "model-x"
            assert rec.chain[0].narrator_type == "dataset"
            assert rec.chain[1].narrator_type == "model"
            # Self-authenticating: recompute matches.
            assert rec.integrity.record_hash == canonical_hash(rec.to_dict(include_integrity=False))

            reset_engine()

    def test_unknown_claim_raises(self, tmp_path) -> None:
        import tempfile

        from sqlalchemy.orm import Session

        import pytest

        from isnad.audit import build_audit_record
        from isnad.core.registry import Registry
        from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine

        with tempfile.TemporaryDirectory() as d:
            url = f"sqlite:///{d}/b.db"
            reset_engine()
            init_db(url)
            engine = create_engine_from_url(url)
            with Session(engine) as s, pytest.raises(KeyError):
                build_audit_record("nope", s, Registry())
            reset_engine()


class TestRedaction:
    def test_redact_fn_is_applied_before_hashing(self) -> None:
        from isnad.audit import build_audit_record_from_nodes

        def redact(field: str, value: object) -> object:
            if field == "claim_text":
                return "<redacted>"
            return value

        rec = build_audit_record_from_nodes(
            claim_id="c1",
            claim_text="a user's private medical history",
            final_grade="hasan",
            grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
            nodes=[ChainNodeAudit("m", "model", "acceptable", "r")],
            weakest_link=WeakestLink("m", "acceptable", "lowest"),
            redact_fn=redact,
        )
        assert rec.claim_text == "<redacted>"
        # The hash commits to the redacted form.
        assert rec.integrity.record_hash == canonical_hash(rec.to_dict(include_integrity=False))


class TestDagAndOversight:
    def test_build_from_nodes_supports_dag_upstream_ids(self) -> None:
        from isnad.audit import build_audit_record_from_nodes

        nodes = [
            ChainNodeAudit("src", "dataset", "reliable", "r"),
            ChainNodeAudit("retriever", "retriever", "acceptable", "r", upstream_ids=["src"]),
            ChainNodeAudit("model", "model", "weak", "r", upstream_ids=["retriever", "src"]),
        ]
        rec = build_audit_record_from_nodes(
            claim_id="c1",
            claim_text="x",
            final_grade="daif",
            grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
            nodes=nodes,
            weakest_link=WeakestLink("model", "weak", "lowest"),
        )
        assert rec.chain[1].upstream_ids == ["src"]
        assert rec.chain[2].upstream_ids == ["retriever", "src"]  # branch/merge, not linear

    def test_human_oversight_is_carried(self) -> None:
        from isnad.audit import build_audit_record_from_nodes

        oversight = [HumanOversight("reviewer-1", "approved", utcnow_iso(), "checked the diff")]
        rec = build_audit_record_from_nodes(
            claim_id="c1",
            claim_text="x",
            final_grade="hasan",
            grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
            nodes=[ChainNodeAudit("m", "model", "acceptable", "r")],
            weakest_link=WeakestLink("m", "acceptable", "lowest"),
            human_oversight=oversight,
        )
        assert rec.human_oversight[0].actor_ref == "reviewer-1"
        assert rec.human_oversight[0].action == "approved"
