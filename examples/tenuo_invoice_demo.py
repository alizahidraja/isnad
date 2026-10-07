"""ISNAD × Tenuo — three-act invoice-fraud demo (offline, no API keys).

Simulates a Tenuo warrant + guard WITHOUT importing the real ``tenuo`` package,
so the demo runs with zero network and zero external dependencies (stdlib +
``cryptography`` only). The simulated guard mirrors Tenuo's contract: each
warrant field constrains the matching argument, checked before the tool runs.

  Act 1 (baseline)  — a tight warrant (payee pinned to the vendor master,
    €5k cap) passes a legitimate payment. Tenuo works as designed.
  Act 2 (attack)    — a poisoned "update vendor details" payload swaps the IBAN
    through legitimate authority; the payment clears the warrant alone. This is
    the in-policy gap: Tenuo never checks whether the *data behind an allowed
    argument* is true.
  Act 3 (with ISNAD) — the pay tool's ``iban`` must satisfy
    ``IsnadGradeConstraint(min_grade="good")``. A properly-sourced IBAN (sound
    attestation) passes; the swapped IBAN (weak attestation) is denied and the
    denial prints its trace; a retyped IBAN (valid attestation, wrong value) is
    also denied.

Run:  uv run python examples/tenuo_invoice_demo.py
"""

from __future__ import annotations

from isnad.integrations.tenuo import (
    IsnadGradeConstraint,
    attest,
    ed25519_public_bytes,
    ed25519_public_key_from_bytes,
    ed25519_signing_key,
    mint_grade_attestation,
)

# --------------------------------------------------------------------------- #
# Simulated Tenuo warrant + guard (no tenuo import)
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Scenario fixtures
# --------------------------------------------------------------------------- #

MASTER_PAYEE = "ACME GmbH"
MASTER_IBAN = "DE89 3704 0044 0532 0130 00"  # properly sourced
POISONED_IBAN = "DE44 5001 0517 5407 3249 31"  # swapped via poisoned email
RETYPED_IBAN = "DE89 3704 0044 0532 0130 0O"  # look-alike (letter O, not 0)

# The ISNAD issuer signs attestations for argument values.
issuer = ed25519_signing_key()
issuer_pub = ed25519_public_key_from_bytes(ed25519_public_bytes(issuer))

# The claim's isnad digest is the trace: where the value came from.
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


# --------------------------------------------------------------------------- #
# Act 1 — baseline: Tenuo alone, tight warrant, legitimate payment
# --------------------------------------------------------------------------- #
print("=== Act 1: baseline (Tenuo alone, tight warrant) ===")
warrant1 = {
    "payee": MASTER_PAYEE,
    "amount": _amount_cap(5000),
    "iban": lambda v: isinstance(v, str),  # any IBAN — Tenuo doesn't check provenance
}
ok, reason = guard(
    "pay_vendor", {"payee": MASTER_PAYEE, "amount": 2500, "iban": MASTER_IBAN}, warrant1
)
record("Act 1", ok, f"legitimate payment allowed ({reason})")

# --------------------------------------------------------------------------- #
# Act 2 — attack: poisoned IBAN swaps through legitimate authority
# --------------------------------------------------------------------------- #
print("=== Act 2: attack (poisoned IBAN, Tenuo alone) ===")
ok, reason = guard(
    "pay_vendor", {"payee": MASTER_PAYEE, "amount": 2500, "iban": POISONED_IBAN}, warrant1
)
# The warrant pins payee + amount but NOT the IBAN's provenance, so it clears.
record("Act 2", ok, f"poisoned IBAN cleared Tenuo alone ({reason}) — the in-policy gap")

# --------------------------------------------------------------------------- #
# Act 3 — with ISNAD: the iban argument must carry a valid grade attestation
# --------------------------------------------------------------------------- #
print("=== Act 3: with ISNAD (iban must satisfy IsnadGradeConstraint) ===")
warrant3 = {
    "payee": MASTER_PAYEE,
    "amount": _amount_cap(5000),
    "iban": constraint,
}

# 3a — properly sourced IBAN (sound attestation) passes
ok, reason = guard(
    "pay_vendor",
    {"payee": MASTER_PAYEE, "amount": 2500, "iban": attest(MASTER_IBAN, sound_att)},
    warrant3,
)
record("Act 3a", ok, f"properly-sourced IBAN allowed ({reason})")

# 3b — swapped IBAN (weak attestation, below min_grade=good) is denied + trace
ok, reason = guard(
    "pay_vendor",
    {"payee": MASTER_PAYEE, "amount": 2500, "iban": attest(POISONED_IBAN, weak_att)},
    warrant3,
)
record(
    "Act 3b",
    (not ok),
    f"swapped IBAN denied ({reason}) — trace: {poisoned_trace}",
)

# 3c — retyped IBAN (valid sound attestation, wrong value_hash) is denied
ok, reason = guard(
    "pay_vendor",
    {"payee": MASTER_PAYEE, "amount": 2500, "iban": attest(RETYPED_IBAN, sound_att)},
    warrant3,
)
record("Act 3c", (not ok), f"retyped IBAN denied ({reason}) — value_hash mismatch")

# 3d — bare IBAN (no attestation) is denied (required=True fail-closed)
ok, reason = guard(
    "pay_vendor",
    {"payee": MASTER_PAYEE, "amount": 2500, "iban": MASTER_IBAN},
    warrant3,
)
record("Act 3d", (not ok), f"bare IBAN denied ({reason}) — fail closed")

# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
print("\n=== summary ===")
all_ok = all(p for _, p, _ in results)
for act, passed, detail in results:
    print(f"  {'PASS' if passed else 'FAIL'}  {act}: {detail}")
print(f"\nRESULT: {'ALL ACTS PASS' if all_ok else 'SOME ACTS FAILED'}")

# Hard assertions so the demo fails loudly if the invariants regress.
assert results[0][1] is True, "Act 1 must pass"
assert results[1][1] is True, "Act 2 must show Tenuo alone clears the poisoned IBAN"
assert results[2][1] is True, "Act 3a must pass"
assert results[3][1] is True, "Act 3b must deny the weak IBAN"
assert results[4][1] is True, "Act 3c must deny the retyped IBAN"
assert results[5][1] is True, "Act 3d must deny the bare IBAN"
