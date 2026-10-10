"""Tests for the 3.1.5 audit-honesty fixes.

- signature commitment bound into the append-only log / Merkle leaf (forgery fails)
- per-record governance mapping (hash-committed)
- keyed claim-text commitment (erasure, not plain-hash pseudonymization)
"""

from __future__ import annotations

from isnad.audit.canonical import canonical_hash, sha256_hex, sig_commitment_hex
from isnad.audit.chainlog import (
    _read_chain,
    append_record,
    verify_chain,
    verify_signature_commitment,
)
from isnad.audit.erasure import commit_claim_text
from isnad.audit.exporter import attach_governance_mapping
from isnad.audit.merkle_log import record_to_leaf
from isnad.audit.schema import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    GradingStrategy,
    Integrity,
    SourceDocument,
    WeakestLink,
)


def _record(
    claim_text: str, record_hash: str, detached_signature: str | None = None
) -> AuditRecord:
    return AuditRecord(
        record_id="rec-1",
        record_version="1.0",
        generated_at="2026-10-08T00:00:00Z",
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
        environment=Environment(isnad_version="3.1.5", python_version="3.11", platform="test"),
        integrity=Integrity(record_hash=record_hash, detached_signature=detached_signature),
    )


# ---- Fix 1: signature commitment ----
def test_forged_record_breaks_signature_commitment(tmp_path):
    path = tmp_path / "chain.jsonl"
    record_hash = sha256_hex("claim: alice owes bob 100")
    signature = "feedface" * 8
    sig_commitment = sig_commitment_hex(record_hash, signature)
    assert sig_commitment is not None
    append_record(path, "rec-1", record_hash, sig_commitment)

    entry = _read_chain(path)[0]
    assert entry.sig_commitment == sig_commitment

    # Forge: rewrite the claim -> new self-hash, keep the OLD detached signature.
    forged_record_hash = sha256_hex("claim: alice owes bob 999")
    assert verify_signature_commitment(entry.sig_commitment, forged_record_hash, signature) is False
    assert verify_signature_commitment(entry.sig_commitment, record_hash, signature) is True
    # The hash-chain linkage itself is still linear (unchanged behavior).
    assert verify_chain(path) is None


def test_unsigned_record_has_null_commitment_and_verifies(tmp_path):
    path = tmp_path / "chain.jsonl"
    append_record(path, "rec-1", sha256_hex("x"))
    entry = _read_chain(path)[0]
    assert entry.sig_commitment is None
    assert verify_chain(path) is None


def test_record_to_leaf_binds_signature():
    rec = _record("c", "abc123" * 8, detached_signature="feedface" * 8)
    rid, rhash, sc = record_to_leaf(rec)
    assert (rid, rhash) == ("rec-1", "abc123" * 8)
    assert sc == sig_commitment_hex("abc123" * 8, "feedface" * 8)

    unsigned = _record("c", "abc123" * 8)
    assert record_to_leaf(unsigned) == ("rec-1", "abc123" * 8, None)


# ---- Fix 2: governance mapping ----
def test_governance_mapping_is_hash_committed():
    rec = _record("c", "abc123" * 8)
    before = canonical_hash(rec.to_dict(include_integrity=False))
    attach_governance_mapping(rec)
    assert rec.governance
    assert all("instrument" in g and "article" in g for g in rec.governance)
    after = canonical_hash(rec.to_dict(include_integrity=False))
    assert before != after


# ---- Fix 3: keyed erasure commitment ----
def test_keyed_commitment_differs_from_plain_hash():
    claim = "Applicant AC-2041"
    plain = sha256_hex(claim)
    keyed = commit_claim_text(claim, "secret-1")
    assert keyed != plain
    assert commit_claim_text(claim, "secret-1") == keyed
    assert commit_claim_text(claim, "secret-2") != keyed
