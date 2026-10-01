"""Generic signed-JSON SIEM export for ISNAD audit records.

One JSON-line format that a SIEM (Splunk HEC, Datadog logs, Snowflake) can
ingest: an ``audit`` payload (the canonical record) plus the provenance fields
(``record_hash``, ``detached_signature``, ``chain_head``, RFC 3339 ``timestamp``).

**Honesty:** this emits *evidence artifacts* in a SIEM-ingestable shape. It is
not, and must never be read as, a compliance attestation (EU AI Act, ISO/IEC
42001, NIST AI RMF, SOC 2, or otherwise). ``claim_text`` is redacted by default.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

from isnad.audit.schema import AuditRecord

_REDACTED = "<redacted>"


def siem_dict(
    record: AuditRecord,
    *,
    redact: bool = True,
    chain_head: str | None = None,
) -> dict[str, object]:
    """One SIEM-ingestable dict for a single record.

    ``chain_head`` is the current head of the hash/Merkle chain; when omitted it
    falls back to the record's own hash (the record is then its own head).

    **Redaction honesty:** ``redact=True`` rewrites ``claim_text`` AFTER the record
    was hashed, so the emitted ``record_hash`` commits to the UNREDACTED form - a
    consumer recomputing the hash over the emitted (redacted) payload will NOT
    match. For a self-verifying redacted record, redact BEFORE hashing via
    ``build_audit_record(redact_fn=...)`` (the CLI's ``export --format siem`` does
    this). ``siem_dict``'s ``redact`` is therefore display-only PII scrubbing, not
    a verification-preserving transform.
    """
    payload = record.to_dict(include_integrity=False)
    if redact:
        payload["claim_text"] = _REDACTED
    return {
        "timestamp": record.generated_at,  # already ISO 8601 / RFC 3339
        "record_hash": record.integrity.record_hash,
        "detached_signature": record.integrity.detached_signature,
        "chain_head": chain_head or record.integrity.record_hash,
        "audit": payload,
    }


def siem_jsonl(
    records: Iterable[AuditRecord],
    *,
    redact: bool = True,
    chain_head: str | None = None,
) -> Iterator[str]:
    """Yield one signed-JSON object per record (SIEM JSONL).

    ``claim_text`` is redacted by default (PII); pass ``redact=False`` to opt
    into full content. Signed JSON for SIEM ingestion — not a compliance
    attestation.
    """
    for record in records:
        yield json.dumps(
            siem_dict(record, redact=redact, chain_head=chain_head),
            ensure_ascii=False,
            separators=(",", ":"),
        )
