"""Detached signatures for audit records (issue #97).

``integrity.record_hash`` is a *self*-hash: anyone who can rewrite the record
can recompute it, so it detects accidental corruption and post-hoc modification
but not a forger who rebuilds the whole record. A **detached signature** over
the canonical payload fixes that: an operator signs the canonical JSON with
their key and the signature is stored in ``integrity.detached_signature``.

Stdlib-only and signer-agnostic — the caller supplies ``signer`` / ``verifier``
callables (Ed25519, a Sigstore/cosign-backed function, …). A dependency-free
HMAC-SHA256 signer/verifier is provided for shared-secret deployments.

.. code-block:: python

    from isnad.audit import sign_detached, verify_detached, hmac_signer, hmac_verifier

    sign_detached(record, hmac_signer("my-secret"))
    assert verify_detached(record, hmac_verifier("my-secret"))
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from typing import Any

from isnad.audit.canonical import canonical_json
from isnad.audit.schema import AuditRecord

# A detached signature covers the canonical JSON of the record *payload* (the
# exact object `record_hash` commits to, excluding `integrity` itself).
Signer = Callable[[str], str]
Verifier = Callable[[str, str], bool]


def sign_detached(record: AuditRecord, signer: Signer) -> AuditRecord:
    """Sign the record's canonical payload and store the detached signature."""
    payload = canonical_json(record.to_dict(include_integrity=False))
    record.integrity.detached_signature = signer(payload)
    return record


def verify_detached(record: AuditRecord, verifier: Verifier) -> bool:
    """Verify the stored detached signature against the canonical payload.

    Returns False when there is no signature (a self-hashed record is not
    tamper-evident against a forger).
    """
    if not record.integrity.detached_signature:
        return False
    payload = canonical_json(record.to_dict(include_integrity=False))
    return verifier(payload, record.integrity.detached_signature)


def hmac_signer(secret: str) -> Signer:
    """A dependency-free HMAC-SHA256 signer for shared-secret deployments."""

    def sign(payload: str) -> str:
        return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    return sign


def hmac_verifier(secret: str) -> Verifier:
    """The matching HMAC-SHA256 verifier (constant-time compare)."""

    def verify(payload: str, signature: str) -> bool:
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    return verify


def ed25519_keypair() -> tuple[Any, Any]:
    """Generate an Ed25519 (private, public) keypair via ``cryptography``.

    ``cryptography`` is an optional dependency; it is imported lazily and this
    raises ``ImportError`` if it is not installed.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    return private, private.public_key()


def ed25519_signer(private_key: Any) -> Signer:
    """An Ed25519 detached signer (asymmetric — no shared secret)."""

    def sign(payload: str) -> str:
        return str(private_key.sign(payload.encode()).hex())

    return sign


def ed25519_verifier(public_key: Any) -> Verifier:
    """The matching Ed25519 detached verifier."""
    from cryptography.exceptions import InvalidSignature

    def verify(payload: str, signature: str) -> bool:
        try:
            public_key.verify(bytes.fromhex(signature), payload.encode())
            return True
        except (InvalidSignature, ValueError):
            return False

    return verify
