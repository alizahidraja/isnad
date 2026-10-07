# isnad[tenuo] — the ISNAD × Tenuo bridge

A **Tier-1 Tenuo constraint** that enforces a signed ISNAD grade attestation on
a tool argument, closing Tenuo's in-policy data-provenance gap.

## The problem it solves

Tenuo authorizes **what** an agent may call (signed warrants bound tools,
arguments and time). It never checks whether the **data behind an allowed
argument is true**. A poisoned IBAN that arrives through a legitimate
"update vendor details" authority is *in policy* — the warrant authorizes the
payment, so Tenuo lets it through. This bridge checks the data, not the action.

## What it does

- `mint_grade_attestation(value, grade, isnad_digest, ttl, key)` — signs a
  compact Ed25519 statement `{value_hash, isnad_digest, grade, issued_at,
  expires_at}`.
- `verify_grade_attestation(...)` — offline, pure, **fail-closed**, never
  raises (tamper, wrong value, expiry, grade-below-minimum, garbage, and
  pathological input all return `False`).
- `IsnadGradeConstraint(min_grade, trusted_public_key)` — a Tenuo
  `.satisfies(value)` constraint you drop onto a high-risk warrant field.
- `attest(value, attestation)` / `unwrap(envelope)` — wrap and unwrap the
  attested-argument envelope.

## Trust model

A verified attestation proves *"the holder of the issuer private key signed
grade G for value V"* — nothing more. **The issuer key IS the ISNAD grading
authority**: trusting the key means trusting that whoever holds it did the
isnād verification. `isnad_digest` is carried and signed but not resolved here
against any ledger; the production upgrade is a registry hook that resolves the
digest against ISNAD's trace store (out of scope for this showcase).

## Envelope convention

Tenuo delivers the *raw field value* to `satisfies()`. So the constrained
field's value must **be** the attested envelope:

```python
{"value": "DE89 3704 0044 0532 0130 00", "attestation": "<signed JSON>"}
```

The guard verifies the envelope; the tool unwraps `.value` and consumes the
real argument. Fail-closed: a bare value (a plain IBAN) or a missing
attestation is always denied. There is no fail-open `required=False` escape
hatch — an optional field is simply absent from the warrant.

## Wire it into a real Tenuo warrant

```python
from tenuo import Capability, Pattern, Range, SigningKey, configure, guard, mint_sync
from isnad.integrations.tenuo import IsnadGradeConstraint, attest, unwrap

configure(issuer_key=SigningKey.generate(), dev_mode=True)

# The ISNAD issuer's public key, out of band.
isnad_pub = ...  # 32 raw bytes

@guard(tool="pay_vendor")
def pay_vendor(iban: dict, payee: str, amount: int) -> str:
    real_iban = unwrap(iban)          # envelope passed the constraint
    return f"paid {amount} to {payee} via {real_iban}"

with mint_sync(Capability(
    "pay_vendor",
    iban=IsnadGradeConstraint(min_grade="good", trusted_public_key=isnad_pub),
    payee=Pattern("ACME*"),
    amount=Range.max_value(5000),
)):
    pay_vendor(attest(iban, signed_attestation), "ACME GmbH", 2500)
```

## What this is NOT (deliberately excluded)

- **Not a Tenuo-core PR.** This lives in ISNAD's repo as a showcase. The
  Tenuo-core path (a docs/example page in their integration guide) is
  **issue-first** per their CONTRIBUTING.md, and comes only after engagement.
- **Denials do NOT feed narrator grades.** Injected text could farm denials to
  smear honest agents (the bug class ISNAD 3.0.3 fixed).
- **Warrant proof-of-possession is NOT narrator identity.** Proving who held a
  key is not proving who wrote a claim.

## Run the demo

```bash
uv run python examples/tenuo_invoice_demo.py
```

Three acts: a steelmanned warrant passes a legitimate payment; a poisoned
"update vendor details" payload swaps the IBAN and clears Tenuo alone; with
ISNAD the swapped IBAN is denied with its own trace.
