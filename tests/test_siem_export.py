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


def test_siem_emitted_hash_verifies_against_redacted_payload():
    """The emitted record_hash must be recomputable from the emitted (redacted) payload.
    (Redaction must happen BEFORE hashing, so the hash commits to what is emitted.)"""
    from isnad.audit.canonical import canonical_hash

    rec = _record("the dosage is 5 mg")
    # simulate the fixed CLI path: redact BEFORE hashing
    rec.claim_text = "<redacted>"
    rec.integrity = Integrity(
        record_hash=canonical_hash(rec.to_dict(include_integrity=False)),
        detached_signature="sig",
    )
    obj = siem_dict(rec, redact=False)  # already redacted
    assert canonical_hash(obj["audit"]) == obj["record_hash"]


def test_cli_siem_format_round_trip(monkeypatch, tmp_path, capsys):
    """`isnad export --format siem` emits a redacted signed-JSON line."""
    from isnad.cli import main as cli_main

    # build a signed record + stub the loader, mirroring the audit test pattern
    from isnad.audit.canonical import canonical_hash

    cli_main._load_registry_and_session = lambda: (_FakeRegistry(), _DummySession())
    import isnad.audit as _audit

    def _fake_build(claim, session, registry, redact_fn=None, **k):
        r = _record("the dosage is 5 mg")
        if redact_fn is not None:
            r.claim_text = "<redacted>"
        r.integrity = Integrity(
            record_hash=canonical_hash(r.to_dict(include_integrity=False)),
            detached_signature="sig",
        )
        return r

    monkeypatch.setattr(_audit, "build_audit_record", _fake_build)

    code = cli_main._export(["--claim", "c1", "--format", "siem"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert obj["audit"]["claim_text"] == "<redacted>"
    assert canonical_hash(obj["audit"]) == obj["record_hash"]


class _FakeRegistry:
    def get(self, *a, **k):
        return None


class _DummySession:
    def close(self):
        pass
