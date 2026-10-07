"""ISNAD × Tenuo — the honest "works today" integration (imports real tenuo).

Unlike ``examples/tenuo_invoice_demo.py`` (which SIMULATES Tenuo's guard), this
imports the REAL ``tenuo`` package. Install it first::

    pip install tenuo

The pattern: Tenuo's ``@guard(tool=...)`` enforces the warrant (authorization —
*what* may run); then a thin wrapper runs ISNAD's grade check (provenance —
*whether the data behind an allowed argument is sound*) before the tool body.
The ``iban`` field is ``Wildcard()`` in the warrant (Tenuo authorizes the
payment; it does not judge the value), and the wrapper is where ISNAD denies a
weakly-sourced value.

Run::

    uv run python examples/tenuo_real_wrapper.py
"""

from __future__ import annotations

import sys

try:
    from tenuo import Capability, Pattern, Range, SigningKey, Wildcard, configure, guard, mint_sync
except ImportError:
    print("tenuo not installed — run `pip install tenuo` first.")
    sys.exit(0)

from isnad.integrations.tenuo import (
    IsnadGradeConstraint,
    attest,
    ed25519_public_bytes,
    ed25519_signing_key,
    mint_grade_attestation,
    unwrap,
)

GOOD_IBAN = "DE89 3704 0044 0532 0130 00"
SWAPPED_IBAN = "DE12 3456 7890 1234 5678 90"


def main() -> None:
    configure(issuer_key=SigningKey.generate(), dev_mode=True)

    # The ISNAD grading authority mints a signed grade attestation per value.
    isnad_key = ed25519_signing_key()
    isnad_pub = ed25519_public_bytes(isnad_key)
    good = attest(
        GOOD_IBAN,
        mint_grade_attestation(GOOD_IBAN, "good", "trace:vendor-master@verified", 3600, isnad_key),
    )
    swapped = attest(
        SWAPPED_IBAN,
        mint_grade_attestation(SWAPPED_IBAN, "very weak", "trace:poisoned-email", 3600, isnad_key),
    )

    grade_check = IsnadGradeConstraint(min_grade="good", trusted_public_key=isnad_pub)

    @guard(tool="pay_vendor")  # Tenuo: authorization (warrant enforced here)
    def pay_vendor(iban: dict, payee: str, amount: int) -> str:
        # ISNAD: provenance (the wrapper runs AFTER Tenuo allowed the call).
        if not grade_check.satisfies(iban):
            raise PermissionError("iban failed ISNAD grade check")
        real_iban = unwrap(iban)
        return f"paid {amount} EUR to {payee} via {real_iban}"

    with mint_sync(
        Capability(
            "pay_vendor",
            iban=Wildcard(),  # Tenuo authorizes "you may pay" — not "this value is true"
            payee=Pattern("ACME*"),
            amount=Range.max_value(5000),
        )
    ):
        print(pay_vendor(good, "ACME GmbH", 2500))
        try:
            pay_vendor(swapped, "ACME GmbH", 2500)
        except PermissionError:
            print("swapped IBAN denied by the ISNAD grade check")


if __name__ == "__main__":
    main()
