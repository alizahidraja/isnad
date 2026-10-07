# isnad[tenuo] — the ISNAD × Tenuo bridge

A **provenance check for in-policy arguments**, designed to sit **next to**
Tenuo: Tenuo authorizes *what* an agent may call; ISNAD checks *whether the
data behind an allowed argument is sound*.

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
- `IsnadGradeConstraint(min_grade, trusted_public_key)` — a `.satisfies(value)`
  check for a high-risk argument. Shown in the simulated guard; the real Tenuo
  extension point is an open question (see the wiring section).
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

## Wiring (honest status)

**Proposed API — does NOT run against real Tenuo today.** Tenuo's
`Warrant.mint` only accepts its built-in constraint types
(`Pattern`/`Exact`/`OneOf`/`Range`/`CEL`/`Regex`), so the snippet below is the
*proposed* shape, not something that imports and runs against `tenuo` 0.3.x:

```python
# PROPOSED API (not runnable against real Tenuo today)
from tenuo import Capability, Pattern, Range, SigningKey, configure, guard, mint_sync
from isnad.integrations.tenuo import IsnadGradeConstraint, attest, unwrap

configure(issuer_key=SigningKey.generate(), dev_mode=True)
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

### What works today (real Tenuo)

The honest integration runs the ISNAD check **where Tenuo hands off to the
tool**: Tenuo's `@guard(tool=...)` enforces the warrant (authorization), and a
thin wrapper verifies the argument's grade (provenance) before the tool body
runs. See `examples/tenuo_real_wrapper.py` (imports the real `tenuo` package;
`pip install tenuo`). The wrapper:

```python
@guard(tool="pay_vendor")                     # Tenuo: authorization
def pay_vendor(iban: dict, payee: str, amount: int) -> str:
    grade = IsnadGradeConstraint(min_grade="good", trusted_public_key=isnad_pub)
    if not grade.satisfies(iban):              # ISNAD: provenance
        raise PermissionError("iban failed ISNAD grade check")
    real_iban = unwrap(iban)
    return f"paid {amount} to {payee} via {real_iban}"
```

The three-act demo (`examples/tenuo_invoice_demo.py`) **simulates** Tenuo's
guard (it does not import `tenuo`) and says so in its first lines; the wrapper
example is the one that runs against the real package.

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
