"""ISNAD audit — tamper-evident evidence artifacts for AI governance.

This package exports graded claims as ``AuditRecord`` objects whose integrity
is provable (SHA-256 over RFC 8785-canonical JSON, optional hash-chaining).

**Important:** ISNAD produces *evidence artifacts*. It does not confer
conformity with, or certify compliance with, any regulation (the EU AI Act,
ISO/IEC 42001, NIST AI RMF, or any other).  See ``docs/evidence-mapping.md``
for an informational field-by-field mapping — which is not legal advice.
"""

from isnad.audit.chainlog import ChainBreak, ChainEntry, append_record, verify_chain
from isnad.audit.exporter import build_audit_record
from isnad.audit.schema import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    Integrity,
    SourceDocument,
    WeakestLink,
)

__all__ = [
    "AuditRecord",
    "ChainBreak",
    "ChainEntry",
    "ChainNodeAudit",
    "Environment",
    "Integrity",
    "SourceDocument",
    "WeakestLink",
    "append_record",
    "build_audit_record",
    "verify_chain",
]
