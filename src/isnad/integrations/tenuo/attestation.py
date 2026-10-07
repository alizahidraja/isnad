"""Signed grade attestations for the Tenuo bridge (3.1.1).

A *grade attestation* is a compact, offline-verifiable statement that a single
argument value carries a given ISNAD chain grade. Tenuo's warrants authorize
*what* an agent may call; they never check whether the *data behind an allowed
argument is true*. This module mints and verifies exactly that check: the
value's hash, the claim's isnād digest, its grade, and an expiry, all bound by
an Ed25519 signature.

Stdlib + ``cryptography`` only (no ``tenuo`` import), so the verifier is
dependency-light and works standalone as well as inside a Tenuo constraint.

The plain grade names (sound/good/weak/very weak/fabricated) are the "plain
grade names first, hadith terms second" mapping of
``isnad.types.ChainGrade``: sahih -> sound, hasan -> good, daif -> weak,
daif_jiddan -> very weak, mawdu -> fabricated.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Plain grade names in descending trust order. ``grade >= min_grade`` compares
# these integer ranks, matching ChainGrade.SAHIH > HASAN > DAIF > DAIF_JIDDAN
# > MAWDU.
GRADE_ORDER: dict[str, int] = {
    "sound": 5,  # sahih
    "good": 4,  # hasan
    "weak": 3,  # daif
    "very weak": 2,  # daif_jiddan
    "fabricated": 1,  # mawdu
}

# ChainGrade.value -> plain name (for callers that hold a ChainGrade).
CHAIN_GRADE_PLAIN: dict[str, str] = {
    "sahih": "sound",
    "hasan": "good",
    "daif": "weak",
    "daif_jiddan": "very weak",
    "mawdu": "fabricated",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _canonical(value: Any) -> str:
    """Deterministic canonical JSON of an arbitrary value."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def value_hash(value: Any) -> str:
    """SHA-256 hex of the canonical serialization of ``value``."""
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def plain_grade(grade: str) -> str:
    """Normalize a grade to a plain name.

    Accepts a plain name ("sound") or a ChainGrade value ("sahih").
    """
    return CHAIN_GRADE_PLAIN.get(grade, grade)


@dataclass(frozen=True)
class GradeAttestation:
    """The signed fields of a grade attestation (no signature)."""

    value_hash: str
    isnad_digest: str
    grade: str
    issued_at: str
    expires_at: str

    def payload_json(self) -> str:
        """Deterministic canonical JSON of the signed fields."""
        return _canonical({
            "value_hash": self.value_hash,
            "isnad_digest": self.isnad_digest,
            "grade": self.grade,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        })


def ed25519_signing_key() -> Ed25519PrivateKey:
    """Generate a fresh Ed25519 signing key."""
    return Ed25519PrivateKey.generate()


def ed25519_public_bytes(key: Any) -> bytes:
    """32-byte raw Ed25519 public key (accepts a private or public key)."""
    if isinstance(key, Ed25519PrivateKey):
        key = key.public_key()
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def ed25519_public_key_from_bytes(data: bytes) -> Ed25519PublicKey:
    """Reconstruct an Ed25519 public key from its 32-byte raw form."""
    return Ed25519PublicKey.from_public_bytes(data)


def mint_grade_attestation(
    value: Any,
    grade: str,
    isnad_digest: str,
    ttl_seconds: int,
    signing_key: Ed25519PrivateKey,
) -> str:
    """Mint a compact signed grade attestation (returned as a JSON string).

    Raises ``ValueError`` for an unknown grade (the only failure mode here —
    minting is the trusted side).
    """
    grade = plain_grade(grade)
    if grade not in GRADE_ORDER:
        raise ValueError(f"unknown grade {grade!r}; use one of {sorted(GRADE_ORDER)}")
    now = _utcnow()
    att = GradeAttestation(
        value_hash=value_hash(value),
        isnad_digest=isnad_digest,
        grade=grade,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=ttl_seconds)).isoformat(),
    )
    sig = signing_key.sign(att.payload_json().encode("utf-8"))
    return json.dumps(
        {
            "value_hash": att.value_hash,
            "isnad_digest": att.isnad_digest,
            "grade": att.grade,
            "issued_at": att.issued_at,
            "expires_at": att.expires_at,
            "sig": base64.b64encode(sig).decode("ascii"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def verify_grade_attestation(
    value: Any,
    attestation: str,
    public_key: Ed25519PublicKey,
    *,
    min_grade: str,
    now: datetime | None = None,
) -> bool:
    """Offline, pure, fail-closed verification. Never raises.

    Returns True only when the signature verifies, the value hash matches,
    the grade meets ``min_grade``, and the attestation is unexpired.
    """
    try:
        data = json.loads(attestation)
        att = GradeAttestation(
            value_hash=data["value_hash"],
            isnad_digest=data["isnad_digest"],
            grade=data["grade"],
            issued_at=data["issued_at"],
            expires_at=data["expires_at"],
        )
        sig = base64.b64decode(data["sig"])
        public_key.verify(sig, att.payload_json().encode("utf-8"))

        if att.value_hash != value_hash(value):
            return False
        if att.grade not in GRADE_ORDER or min_grade not in GRADE_ORDER:
            return False
        if GRADE_ORDER[att.grade] < GRADE_ORDER[min_grade]:
            return False
        expires = datetime.fromisoformat(att.expires_at)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        ref = now if now is not None else _utcnow()
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=UTC)
        return ref < expires
    except (InvalidSignature, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
