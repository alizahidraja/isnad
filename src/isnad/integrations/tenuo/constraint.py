"""A Tenuo Tier-1 constraint that enforces a signed ISNAD grade attestation.

Tenuo's constraints all expose a unified ``.satisfies(value) -> bool`` method
(see Tenuo's ``tenuo/core.py``: "All tenuo_core constraint objects expose a
unified ``.satisfies(value)`` method... returns False, never True"). This
class implements exactly that protocol, so an operator can drop it onto a
high-risk warrant field:

.. code-block:: python

    Capability(
        "pay_vendor",
        iban=IsnadGradeConstraint(min_grade="good", trusted_public_key=pub),
    )

The constraint is pure Python (stdlib + ``cryptography``) and does NOT import
``tenuo``, so it works standalone and as a Tenuo constraint.

**Attested-argument shape.** An attested argument is a JSON object carrying
both the value and its attestation:

.. code-block:: python

    {"value": "DE89 3704 0044 0532 0130 00", "attestation": "<signed JSON>"}

``satisfies()`` verifies ``value`` against ``attestation`` using the fixed
trusted public key and minimum grade. A missing attestation is denied when
``required=True`` (the default), so high-risk fields fail closed.
"""

from __future__ import annotations

from typing import Any

from isnad.integrations.tenuo.attestation import (
    verify_grade_attestation,
)


def attest(value: Any, attestation: str) -> dict[str, Any]:
    """Wrap a value + its attestation into the attested-argument shape."""
    return {"value": value, "attestation": attestation}


class IsnadGradeConstraint:
    """Fail-closed constraint: the argument must carry a valid, grade-qualifying
    ISNAD attestation.

    Args:
        min_grade: plain grade name ("sound"/"good"/"weak"/"very weak"/
            "fabricated"); the attestation's grade must rank >= this.
        trusted_public_key: an ``Ed25519PublicKey`` (from ``cryptography``) —
            the ISNAD issuer's public key. Only its public half is held here.
        required: when True (default), a missing attestation is denied.
    """

    def __init__(self, min_grade: str, trusted_public_key: Any, *, required: bool = True) -> None:
        self.min_grade = min_grade
        self.trusted_public_key = trusted_public_key
        self.required = required

    def satisfies(self, value: Any) -> bool:
        """Verify the value against its attached attestation. Never raises."""
        if not isinstance(value, dict):
            return not self.required
        attestation = value.get("attestation")
        inner = value.get("value")
        if attestation is None or inner is None:
            return not self.required
        return verify_grade_attestation(
            inner,
            attestation,
            self.trusted_public_key,
            min_grade=self.min_grade,
        )

    def __repr__(self) -> str:
        return f"IsnadGradeConstraint(min_grade={self.min_grade!r}, required={self.required!r})"
