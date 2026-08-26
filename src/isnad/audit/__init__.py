"""ISNAD audit — tamper-evident evidence artifacts for AI governance.

This package exports graded claims as ``AuditRecord`` objects whose integrity
is provable (SHA-256 over RFC 8785-canonical JSON, optional hash-chaining).

**Important:** ISNAD produces *evidence artifacts*. It does not confer
conformity with, or certify compliance with, any regulation (the EU AI Act,
ISO/IEC 42001, NIST AI RMF, or any other).  See ``docs/evidence-mapping.md``
for an informational field-by-field mapping — which is not legal advice.
"""

from isnad.audit.canonical import MalformedLogError
from isnad.audit.chainlog import ChainBreak, ChainEntry, append_record, verify_chain
from isnad.audit.exporter import build_audit_record, build_audit_record_from_nodes
from isnad.audit.merkle_log import (
    BatchBreak,
    InclusionProof,
    MerkleBatch,
    build_batch,
    prove_inclusion,
    read_batch_log,
    record_to_leaf,
    seal_batches,
    verify_batches,
    verify_inclusion,
    write_batch_log,
)
from isnad.audit.schema import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    GradingStrategy,
    HumanOversight,
    Integrity,
    RedactFn,
    SourceDocument,
    WeakestLink,
    apply_redact,
)
from isnad.audit.sign import (
    ed25519_keypair,
    ed25519_signer,
    ed25519_verifier,
    hmac_signer,
    hmac_verifier,
    sign_detached,
    verify_detached,
)

__all__ = [
    "AuditRecord",
    "BatchBreak",
    "ChainBreak",
    "ChainEntry",
    "ChainNodeAudit",
    "Environment",
    "GradingStrategy",
    "HumanOversight",
    "InclusionProof",
    "Integrity",
    "MalformedLogError",
    "MerkleBatch",
    "RedactFn",
    "SourceDocument",
    "WeakestLink",
    "append_record",
    "apply_redact",
    "build_audit_record",
    "build_audit_record_from_nodes",
    "build_batch",
    "ed25519_keypair",
    "ed25519_signer",
    "ed25519_verifier",
    "hmac_signer",
    "hmac_verifier",
    "prove_inclusion",
    "read_batch_log",
    "record_to_leaf",
    "seal_batches",
    "sign_detached",
    "verify_batches",
    "verify_chain",
    "verify_detached",
    "verify_inclusion",
    "write_batch_log",
]
