"""Tests for the 3.1.7 enforcement fixes.

- signature commitment now ENFORCED by `isnad verify --chain-log`
- governance mapping attached + hash-covered inside the export builder
"""

from __future__ import annotations

import json

from isnad.audit.canonical import canonical_hash, sig_commitment_hex
from isnad.audit.chainlog import append_record
from isnad.audit.exporter import build_audit_record_from_nodes
from isnad.audit.schema import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    GradingStrategy,
    Integrity,
    SourceDocument,
    WeakestLink,
)
from isnad.audit.sign import hmac_signer, sign_detached


def _record(claim_text: str) -> AuditRecord:
    return AuditRecord(
        record_id="rec-1",
        record_version="1.0",
        generated_at="2026-10-10T00:00:00Z",
        claim_id="c1",
        claim_text=claim_text,
        final_grade="hasan",
        grading_strategy=GradingStrategy(name="RefinedWeakestLink", version="1"),
        chain=[
            ChainNodeAudit(
                narrator_id="src", narrator_type="dataset", grade="reliable", grade_rationale="r"
            )
        ],
        weakest_link=WeakestLink(narrator_id="src", grade="reliable", why="lowest"),
        source_documents=[SourceDocument(uri="https://example.com/x")],
        human_oversight=[],
        environment=Environment(isnad_version="3.1.7", python_version="3.11", platform="test"),
        integrity=Integrity(record_hash="placeholder"),
    )


def _signed(claim_text: str, secret: str) -> AuditRecord:
    rec = _record(claim_text)
    rec.integrity = Integrity(record_hash=canonical_hash(rec.to_dict(include_integrity=False)))
    sign_detached(rec, hmac_signer(secret))
    return rec


def test_cli_verify_enforces_chain_log_commitment(tmp_path):
    """A forged record (recomputed self-hash + kept OLD signature) must fail
    `isnad verify --chain-log` at the commitment cross-check."""
    from isnad.cli.main import _verify

    secret = "test-secret"
    rec = _signed("alice owes bob 100", secret)
    rec_path = tmp_path / "record.json"
    rec_path.write_text(json.dumps(rec.to_dict()))
    chain_path = tmp_path / "chain.jsonl"
    sc = sig_commitment_hex(rec.integrity.record_hash, rec.integrity.detached_signature)
    append_record(chain_path, rec.record_id, rec.integrity.record_hash, sc)

    # intact record verifies
    assert (
        _verify([
            "--record",
            str(rec_path),
            "--chain-log",
            str(chain_path),
            "--hmac-secret",
            secret,
        ])
        == 0
    )

    # forge: rewrite the claim, recompute the self-hash, keep the OLD signature
    forged = _record("alice owes bob 999")
    forged.integrity = Integrity(
        record_hash=canonical_hash(forged.to_dict(include_integrity=False)),
        detached_signature=rec.integrity.detached_signature,
    )
    rec_path.write_text(json.dumps(forged.to_dict()))

    # the log entry's sig_commitment no longer matches -> verify fails
    assert (
        _verify([
            "--record",
            str(rec_path),
            "--chain-log",
            str(chain_path),
            "--hmac-secret",
            secret,
        ])
        == 1
    )


def test_builder_attaches_governance_and_hash_covers_it():
    rec = build_audit_record_from_nodes(
        claim_id="c1",
        claim_text="Applicant AC-2041 is eligible for a loan",
        final_grade="hasan",
        grading_strategy=GradingStrategy(name="RefinedWeakestLink", version="1"),
        nodes=[
            ChainNodeAudit(
                narrator_id="src", narrator_type="dataset", grade="reliable", grade_rationale="r"
            )
        ],
        weakest_link=WeakestLink(narrator_id="src", grade="reliable", why="lowest"),
    )
    assert rec.governance, "builder must attach the governance mapping"
    assert all("instrument" in g and "article" in g for g in rec.governance)
    assert rec.integrity.record_hash == canonical_hash(rec.to_dict(include_integrity=False)), (
        "record hash must cover the governance block"
    )
