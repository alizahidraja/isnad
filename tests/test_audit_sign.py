"""Detached signatures for audit records (issue #97)."""

from __future__ import annotations

from isnad.audit import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    GradingStrategy,
    SourceDocument,
    WeakestLink,
    hmac_signer,
    hmac_verifier,
    sign_detached,
    verify_detached,
)
from isnad.audit.schema import RECORD_VERSION, new_record_id, utcnow_iso


def _record() -> AuditRecord:
    return AuditRecord(
        record_id=new_record_id(),
        record_version=RECORD_VERSION,
        generated_at=utcnow_iso(),
        claim_id="c1",
        claim_text="p = mv",
        final_grade="hasan",
        grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
        chain=[ChainNodeAudit("src", "dataset", "reliable", "r")],
        weakest_link=WeakestLink("src", "reliable", "lowest grade"),
        source_documents=[SourceDocument("https://e/x")],
        human_oversight=[],
        environment=Environment("2.6.2", "3.12", "darwin"),
    )


def test_sign_then_verify_round_trips() -> None:
    rec = _record()
    sign_detached(rec, hmac_signer("secret"))
    assert rec.integrity.detached_signature is not None
    assert verify_detached(rec, hmac_verifier("secret")) is True


def test_wrong_secret_fails() -> None:
    rec = _record()
    sign_detached(rec, hmac_signer("secret"))
    assert verify_detached(rec, hmac_verifier("other-secret")) is False


def test_unsigned_record_does_not_verify() -> None:
    rec = _record()
    assert rec.integrity.detached_signature is None
    assert verify_detached(rec, hmac_verifier("secret")) is False


def test_tampering_after_signing_fails() -> None:
    """The whole point of a detached signature: mutate the record after signing
    and the signature no longer matches."""
    rec = _record()
    sign_detached(rec, hmac_signer("secret"))
    rec.claim_text = "p = h/lambda"  # tamper
    assert verify_detached(rec, hmac_verifier("secret")) is False


class TestEd25519DetachedSignature:
    """Asymmetric (no shared secret) detached signatures — issue #97 follow-up."""

    def test_round_trip(self) -> None:
        import pytest

        pytest.importorskip("cryptography")
        from isnad.audit import ed25519_keypair, ed25519_signer, ed25519_verifier

        private, public = ed25519_keypair()
        rec = _record()
        sign_detached(rec, ed25519_signer(private))
        assert verify_detached(rec, ed25519_verifier(public)) is True

    def test_wrong_public_key_fails(self) -> None:
        import pytest

        pytest.importorskip("cryptography")
        from isnad.audit import ed25519_keypair, ed25519_signer, ed25519_verifier

        private, _ = ed25519_keypair()
        _, other_public = ed25519_keypair()
        rec = _record()
        sign_detached(rec, ed25519_signer(private))
        assert verify_detached(rec, ed25519_verifier(other_public)) is False

    def test_tampered_record_fails(self) -> None:
        import pytest

        pytest.importorskip("cryptography")
        from isnad.audit import ed25519_keypair, ed25519_signer, ed25519_verifier

        private, public = ed25519_keypair()
        rec = _record()
        sign_detached(rec, ed25519_signer(private))
        rec.claim_text = "tampered"
        assert verify_detached(rec, ed25519_verifier(public)) is False
