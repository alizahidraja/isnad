"""A Tenuo Tier-1 constraint that enforces a signed ISNAD grade attestation.

Tenuo's constraints all expose a unified ``.satisfies(value) -> bool`` method
(see Tenuo's ``tenuo/core.py``: "All tenuo_core constraint objects expose a
unified ``.satisfies(value)`` method... returns False, never True"). This
class implements exactly that protocol, so an operator can drop it onto a
high-risk warrant field **whose value is an ISNAD-attested envelope**:

.. code-block:: python

    Capability(
        "pay_vendor",
        iban=IsnadGradeConstraint(min_grade="good", trusted_public_key=pub),
    )

The constraint is pure Python (stdlib + ``cryptography``) and does NOT import
``tenuo``, so it works standalone and as a Tenuo constraint.

**Attested-argument shape.** Tenuo delivers the *raw field value* to
``satisfies()``. For this bridge the constrained field's value must therefore
**be** the attested envelope (the operator wraps the argument before the call;
the guarded tool unwraps it):

.. code-block:: python

    {"value": "DE89 3704 0044 0532 0130 00", "attestation": "<signed JSON>"}

``satisfies()`` verifies ``value`` against ``attestation`` using the fixed
trusted public key and minimum grade, and then the tool unwraps ``.value`` and
consumes the real argument. This is fail-closed: a bare value (a plain IBAN
string) or a missing attestation is **always denied** — there is no fail-open
``required=False`` escape hatch, because an optional field is simply absent
from the warrant (Tenuo never calls ``satisfies()`` for an absent field).
"""

from __future__ import annotations

from typing import Any

from isnad.integrations.tenuo.attestation import (
    ed25519_public_key_from_bytes,
    plain_grade,
    verify_grade_attestation,
)


def attest(value: Any, attestation: str) -> dict[str, Any]:
    """Wrap a value + its attestation into the attested-argument shape."""
    return {"value": value, "attestation": attestation}


def unwrap(attested: dict[str, Any]) -> Any:
    """Return the ``value`` half of an attested envelope.

    The guarded tool calls this after the constraint has passed, so the real
    argument (not the envelope) is what the tool body receives.
    """
    return attested["value"]


class IsnadGradeConstraint:
    """Fail-closed constraint: the argument must carry a valid, grade-qualifying
    ISNAD attestation.

    Args:
        min_grade: plain grade name ("sound"/"good"/"weak"/"very weak"/
            "fabricated") or a ChainGrade value ("sahih"/"hasan"/...). The
            attestation's grade must rank >= this (normalized via
            ``plain_grade``).
        trusted_public_key: the ISNAD issuer's public key — an
            ``Ed25519PublicKey`` or its raw 32-byte ``bytes`` form. Only the
            public half is held here.
    """

    def __init__(self, min_grade: str, trusted_public_key: Any) -> None:
        self.min_grade = plain_grade(min_grade)
        if isinstance(trusted_public_key, (bytes, bytearray, memoryview)):
            try:
                trusted_public_key = ed25519_public_key_from_bytes(bytes(trusted_public_key))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    "trusted_public_key bytes must be a 32-byte Ed25519 public key"
                ) from exc
        self.trusted_public_key = trusted_public_key

    def satisfies(self, value: Any) -> bool:
        """Verify the value against its attached attestation. Never raises."""
        if not isinstance(value, dict):
            return False
        attestation = value.get("attestation")
        inner = value.get("value")
        if attestation is None or inner is None:
            return False
        return verify_grade_attestation(
            inner,
            attestation,
            self.trusted_public_key,
            min_grade=self.min_grade,
        )

    def __repr__(self) -> str:
        return f"IsnadGradeConstraint(min_grade={self.min_grade!r})"
