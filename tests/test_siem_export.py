"""Tests for the generic signed-JSON SIEM export (audit.siem)."""

from __future__ import annotations

import json

import pytest

from isnad.audit.schema import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    GradingStrategy,
    Integrity,
    SourceDocument,
    WeakestLink,
    new_record_id,
    utcnow_iso,
)
from isnad.audit.siem import siem_dict, siem_jsonl


def _record(claim_text: str = "the dosage is 5 mg") -> AuditRecord:
    rec = AuditRecord(
        record_id=new_record_id(),
        record_version="1.0",
        generated_at=utcnow_iso(),
        claim_id="c1",
        claim_text=claim_text,
        final_grade="hasan",
        grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
        chain=[ChainNodeAudit("src", "dataset", "reliable", "r")],
        weakest_link=WeakestLink("src", "reliable", "lowest grade"),
        source_documents=[SourceDocument("https://example.com/x")],
        human_oversight=[],
        environment=Environment("2.25.0", "3.12", "darwin"),
        integrity=Integrity(record_hash="a" * 64, detached_signature="sig"),
    )
    return rec


def test_siem_jsonl_emits_json_with_hash_and_redacted_claim():
    rec = _record()
    lines = list(siem_jsonl([rec]))
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["record_hash"] == "a" * 64
    assert obj["detached_signature"] == "sig"
    assert obj["chain_head"] == "a" * 64
    assert obj["timestamp"] == rec.generated_at
    assert obj["audit"]["claim_text"] == "<redacted>"
    assert obj["audit"]["record_id"] == rec.record_id


def test_siem_redact_false_emits_full_claim_text():
    rec = _record("the dosage is 5 mg")
    obj = siem_dict(rec, redact=False)
    assert obj["audit"]["claim_text"] == "the dosage is 5 mg"


def test_cli_siem_format_round_trip(monkeypatch, tmp_path, capsys):
    """`isnad export --format siem` emits a redacted signed-JSON line."""
    from isnad.cli import main as cli_main

    # build a signed record + stub the loader, mirroring the audit test pattern
    rec = _record()
    cli_main._load_registry_and_session = lambda: (_FakeRegistry(), _DummySession())
    import isnad.audit as _audit

    monkeypatch.setattr(_audit, "build_audit_record", lambda *a, **k: rec)

    code = cli_main._export(["--claim", "c1", "--format", "siem"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert obj["record_hash"] == "a" * 64
    assert obj["audit"]["claim_text"] == "<redacted>"


class _FakeRegistry:
    def get(self, *a, **k):
        return None


class _DummySession:
    def close(self):
        pass
