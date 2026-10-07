"""ISNAD × Tenuo — three-act invoice-fraud demo (offline, no API keys).

Simulates a Tenuo warrant + guard WITHOUT importing the real ``tenuo`` package,
so the demo runs with zero network and zero external dependencies (stdlib +
``cryptography`` only). The simulated guard mirrors Tenuo's contract: each
warrant field constrains the matching argument, checked before the tool runs.

  Act 1 (baseline)  — a steelmanned warrant (payee pinned to the vendor master,
    €5k cap, iban pinned to the vendor master record) passes a legitimate
    payment. Tenuo works as designed.
  Act 2 (attack)    — a poisoned "update vendor details" payload swaps the IBAN
    through the agent's *legitimate* vendor-master authority. The payment then
    clears the warrant alone, because the warrant follows the (now-poisoned)
    master record. This is the in-policy gap: Tenuo checks *whether the action
    is authorized*, never whether the *data behind the argument* was tampered.
  Act 3 (with ISNAD) — the pay tool's ``iban`` must satisfy
    ``IsnadGradeConstraint(min_grade="good")``. A properly-sourced IBAN passes;
    the swapped IBAN (weak provenance) is denied and the denial prints the
    trace carried in its own attestation; a retyped IBAN is denied on a value
    mismatch; a bare IBAN is denied (fail closed).

The envelope convention: the constrained field's value is
``{"value": ..., "attestation": ...}``. The guard verifies the envelope, then
the tool unwraps ``.value`` and consumes the real argument.

Run:  uv run python examples/tenuo_invoice_demo.py
"""

from __future__ import annotations

import json

from isnad.integrations.tenuo import (
    IsnadGradeConstraint,
    attest,
    ed25519_public_bytes,
    ed25519_public_key_from_bytes,
    ed25519_signing_key,
    mint_grade_attestation,
    unwrap,
)


def guard(tool: str, args: dict, warrant: dict) -> tuple[bool, str]:
    """Simulate Tenuo's before-effect check: each warrant field constrains the
    matching argument. Returns (allowed, reason)."""
    for field, constraint in warrant.items():
        value = args.get(field)
        if isinstance(constraint, IsnadGradeConstraint):
            if not constraint.satisfies(value):
                return False, f"{tool}: {field} failed ISNAD grade check"
        elif callable(constraint):
            if not constraint(value):
                return (
                    False,
                    f"{tool}: {field} failed {getattr(constraint, '__name__', constraint)}",
                )
        else:
            if value != constraint:
                return False, f"{tool}: {field} must equal {constraint!r}"
    return True, "ok"


def pay_vendor(iban: str, payee: str, amount: int) -> str:
    """The payment tool. In a real deployment this would be @guard'd."""
    return f"paid {amount} EUR to {payee} via {iban}"


def _amount_cap(cap: int):
    def check(amount):
        return amount <= cap

    return check


def _pinned_to_master(field: str):
    """The steelmanned warrant pins a field to the *vendor master record*.

    A careful customer does not hardcode the IBAN; they pin it to the registry
    ("pay the vendor at their registered account"). That is the right thing to
    do — and it is exactly why a poisoned registry entry flows straight through
    a warrant that only checks authorization, never data provenance.
    """

    def check(v):
        return v == VENDOR_MASTER[field]

    return check


MASTER_PAYEE = "ACME GmbH"
MASTER_IBAN = "DE89 3704 0044 0532 0130 00"
POISONED_IBAN = "DE44 5001 0517 5407 3249 31"
RETYPED_IBAN = "DE89 3704 0044 0532 0130 0O"

# The vendor master record (the registry the warrant pins against).
VENDOR_MASTER = {"payee": MASTER_PAYEE, "iban": MASTER_IBAN}


def update_vendor_details(authority: str, field: str, value: str) -> str:
    """The legitimate "update vendor details" tool.

    An agent with the ``vendor-master-admin`` authority may update the vendor
    master. A poisoned email that lands in a shared data source can drive this
    *in-policy* call — the authority is real, only the data is malicious.
    """
    if authority != "vendor-master-admin":
        return "denied: no authority"
    VENDOR_MASTER[field] = value
    return f"updated {field}"


issuer = ed25519_signing_key()
issuer_pub = ed25519_public_key_from_bytes(ed25519_public_bytes(issuer))

master_trace = "vendor-master@registry/acme/iban (2 corroborating chains)"
poisoned_trace = "poisoned-email:update-vendor-details@2026-10-07 (1 unverified source)"

sound_att = mint_grade_attestation(
    MASTER_IBAN, "sound", master_trace, ttl_seconds=600, signing_key=issuer
)
weak_att = mint_grade_attestation(
    POISONED_IBAN, "weak", poisoned_trace, ttl_seconds=600, signing_key=issuer
)

constraint = IsnadGradeConstraint(min_grade="good", trusted_public_key=issuer_pub)

results: list[tuple[str, bool, str]] = []


def record(act: str, passed: bool, detail: str) -> None:
    results.append((act, passed, detail))
    print(f"[{act}] {'PASS' if passed else 'FAIL'} — {detail}")


print("=== Act 1: baseline (steelmanned warrant, Tenuo alone) ===")
warrant1 = {
    "payee": MASTER_PAYEE,
    "amount": _amount_cap(5000),
    "iban": _pinned_to_master("iban"),
}
ok, reason = guard(
    "pay_vendor", {"payee": MASTER_PAYEE, "amount": 2500, "iban": MASTER_IBAN}, warrant1
)
record("Act 1", ok, f"legitimate payment allowed ({reason})")

print("\n=== Act 2: attack (poisoned master via legitimate update authority) ===")
print("  poisoned email drives: update_vendor_details(vendor-master-admin, iban, POISONED)")
update_vendor_details("vendor-master-admin", "iban", POISONED_IBAN)
ok, reason = guard(
    "pay_vendor", {"payee": MASTER_PAYEE, "amount": 2500, "iban": POISONED_IBAN}, warrant1
)
record(
    "Act 2",
    ok,
    f"poisoned IBAN cleared Tenuo alone ({reason}) — the in-policy data-provenance gap",
)

print("\n=== Act 3: with ISNAD (iban must satisfy IsnadGradeConstraint) ===")
warrant3 = {
    "payee": MASTER_PAYEE,
    "amount": _amount_cap(5000),
    "iban": constraint,
}


# The guarded tool: verify the envelope, then unwrap and call the real tool.
def guarded_pay_vendor(args: dict, warrant: dict) -> tuple[bool, str]:
    ok, reason = guard("pay_vendor", args, warrant)
    if not ok:
        return False, reason
    iban = unwrap(args["iban"]) if isinstance(args["iban"], dict) else args["iban"]
    return True, pay_vendor(iban=iban, payee=args["payee"], amount=args["amount"])


ok, detail = guarded_pay_vendor(
    {"payee": MASTER_PAYEE, "amount": 2500, "iban": attest(MASTER_IBAN, sound_att)}, warrant3
)
record("Act 3a", ok, f"properly-sourced IBAN allowed — tool ran: {detail!r}")

ok, detail = guarded_pay_vendor(
    {"payee": MASTER_PAYEE, "amount": 2500, "iban": attest(POISONED_IBAN, weak_att)}, warrant3
)
weak_trace = json.loads(weak_att)["isnad_digest"]
record(
    "Act 3b",
    (not ok),
    f"swapped IBAN denied ({detail}) — trace from its own attestation: {weak_trace}",
)

ok, detail = guarded_pay_vendor(
    {"payee": MASTER_PAYEE, "amount": 2500, "iban": attest(RETYPED_IBAN, sound_att)}, warrant3
)
record("Act 3c", (not ok), f"retyped IBAN denied ({detail}) — value_hash mismatch")

ok, detail = guarded_pay_vendor(
    {"payee": MASTER_PAYEE, "amount": 2500, "iban": MASTER_IBAN}, warrant3
)
record("Act 3d", (not ok), f"bare IBAN denied ({detail}) — fail closed")


print("\n=== summary ===")
all_ok = all(p for _, p, _ in results)
for act, passed, detail in results:
    print(f"  {'PASS' if passed else 'FAIL'}  {act}: {detail}")
print(f"\nRESULT: {'ALL ACTS PASS' if all_ok else 'SOME ACTS FAILED'}")

assert results[0][1] is True, "Act 1 must pass"
assert results[1][1] is True, "Act 2 must show Tenuo alone clears the poisoned IBAN"
assert results[2][1] is True, "Act 3a must pass"
assert results[3][1] is True, "Act 3b must deny the weak IBAN"
assert results[4][1] is True, "Act 3c must deny the retyped IBAN"
assert results[5][1] is True, "Act 3d must deny the bare IBAN"
