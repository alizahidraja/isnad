"""Tenuo bridge (3.1.3) — a provenance check for in-policy arguments, designed to sit next to Tenuo.

This package mints and verifies compact Ed25519-signed **grade attestations**
that bind a single argument value to its ISNAD chain grade. It is the
provenance check for in-policy arguments, designed to sit next to Tenuo
(Tenuo authorizes *what* an agent may call; ISNAD checks whether the *data
behind an allowed argument* is sound).

``IsnadGradeConstraint`` implements Tenuo's unified ``.satisfies(value)``
protocol. It checks a high-risk argument (IBAN, payee, account)
**whose value is an ISNAD-attested envelope** — the operator wraps the
argument with :func:`attest`, the constraint verifies it, and the guarded tool
unwraps it with :func:`unwrap`. It is dependency-light (stdlib +
``cryptography``) and does not import ``tenuo``, so it works standalone and
inside a real Tenuo warrant.

This is a **showcase integration in ISNAD's repository**, not a Tenuo-core PR.
The Tenuo-core path (a docs/example page in their integration guide) is
issue-first per their CONTRIBUTING.md, and only comes after engagement.

See ``examples/tenuo_invoice_demo.py`` for the three-act invoice-fraud demo.
"""

from isnad.integrations.tenuo.attestation import (
    CHAIN_GRADE_PLAIN,
    GRADE_ORDER,
    GradeAttestation,
    ed25519_public_bytes,
    ed25519_public_key_from_bytes,
    ed25519_signing_key,
    mint_grade_attestation,
    plain_grade,
    value_hash,
    verify_grade_attestation,
)
from isnad.integrations.tenuo.constraint import IsnadGradeConstraint, attest, unwrap

__all__ = [
    "CHAIN_GRADE_PLAIN",
    "GRADE_ORDER",
    "GradeAttestation",
    "IsnadGradeConstraint",
    "attest",
    "unwrap",
    "ed25519_public_bytes",
    "ed25519_public_key_from_bytes",
    "ed25519_signing_key",
    "mint_grade_attestation",
    "plain_grade",
    "value_hash",
    "verify_grade_attestation",
]
