"""The ISNAD audit record — a machine-readable, tamper-evident evidence artifact.

An ``AuditRecord`` is what ISNAD *emits* for governance record-keeping.  It is
an **evidence artifact, not a certificate of conformity**: it records what the
framework graded and why, so a human auditor can re-derive the same conclusion.
It does not, and must never be read to, assert compliance with any regulation.

The integrity model is deliberately boring: SHA-256 over RFC 8785-canonical
JSON, an optional detached-signature slot left reserved, and (optionally) a
tamper-evident hash chain — no blockchain, no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

RECORD_VERSION = "1"
SCHEMA_VERSION = "audit-record-v1"


@dataclass
class ChainNodeAudit:
    """One hand in the transmission chain."""

    narrator_id: str
    narrator_type: str  # human | model | scraper | tool | dataset
    grade: str
    grade_rationale: str
    model_identifier: str | None = None
    model_version: str | None = None
    invocation_timestamp: str | None = None
    input_hash: str | None = None  # SHA-256 of the claim entering the link
    output_hash: str | None = None  # SHA-256 of the claim leaving the link

    def to_dict(self) -> dict[str, object]:
        return {
            "narrator_id": self.narrator_id,
            "narrator_type": self.narrator_type,
            "grade": self.grade,
            "grade_rationale": self.grade_rationale,
            "model_identifier": self.model_identifier,
            "model_version": self.model_version,
            "invocation_timestamp": self.invocation_timestamp,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
        }


@dataclass
class WeakestLink:
    """The link that caps the chain, and why."""

    narrator_id: str
    why: str

    def to_dict(self) -> dict[str, object]:
        return {"narrator_id": self.narrator_id, "why": self.why}


@dataclass
class SourceDocument:
    """A document the chain consumed, identified but content-redacted."""

    uri: str
    retrieved_at: str | None = None
    content_hash: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "uri": self.uri,
            "retrieved_at": self.retrieved_at,
            "content_hash": self.content_hash,
        }


@dataclass
class Environment:
    """Where the record was produced, pseudonymised."""

    isnad_version: str
    python_version: str
    host_fingerprint: str  # hashed, not raw

    def to_dict(self) -> dict[str, object]:
        return {
            "isnad_version": self.isnad_version,
            "python_version": self.python_version,
            "host_fingerprint": self.host_fingerprint,
        }


@dataclass
class Integrity:
    """The record's self-integrity proof."""

    record_hash: str
    hash_algorithm: str = "sha256"
    detached_signature: str | None = None  # reserved — not implemented

    def to_dict(self) -> dict[str, object]:
        return {
            "record_hash": self.record_hash,
            "hash_algorithm": self.hash_algorithm,
            "detached_signature": self.detached_signature,
        }


@dataclass
class AuditRecord:
    """A complete audit record for one graded claim."""

    record_id: str
    record_version: str
    generated_at: str
    claim_id: str
    claim_text: str
    final_grade: str
    grading_strategy_name: str
    grading_strategy_version: str
    chain: list[ChainNodeAudit]
    weakest_link: WeakestLink
    source_documents: list[SourceDocument]
    environment: Environment
    integrity: Integrity = field(default_factory=lambda: Integrity(record_hash=""))

    def to_dict(self, *, include_integrity: bool = True) -> dict[str, object]:
        """Serialize to a plain dict.

        ``include_integrity=False`` yields the payload *before* the hash is
        computed — the exact object the ``record_hash`` is over.
        """
        d: dict[str, object] = {
            "record_id": self.record_id,
            "record_version": self.record_version,
            "generated_at": self.generated_at,
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "final_grade": self.final_grade,
            "grading_strategy_name": self.grading_strategy_name,
            "grading_strategy_version": self.grading_strategy_version,
            "chain": [n.to_dict() for n in self.chain],
            "weakest_link": self.weakest_link.to_dict(),
            "source_documents": [s.to_dict() for s in self.source_documents],
            "environment": self.environment.to_dict(),
        }
        if include_integrity:
            d["integrity"] = self.integrity.to_dict()
        return d


def new_record_id() -> str:
    """A fresh, collision-resistant record identifier."""
    return f"audit-{uuid4().hex}"


def utcnow_iso() -> str:
    """Current UTC instant as ISO 8601."""
    return datetime.now(UTC).isoformat()
