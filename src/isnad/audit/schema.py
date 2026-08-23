"""The ISNAD audit record — a machine-readable, tamper-evident evidence artifact.

An ``AuditRecord`` is what ISNAD *emits* for governance record-keeping.  It is
an **evidence artifact, not a certificate of conformity**: it records what the
framework graded and why, so a human auditor can re-derive the same conclusion.
It does not, and must never be read to, assert compliance with any regulation.

Design notes:

- **``upstream_ids``** makes the chain an explicit DAG, not just a list.  Linear
  chains are the easy case; real agent systems branch and merge.
- **``human_oversight``** exists because Article 14 and SDAIA's "human
  oversight" pillar require *evidence a human intervened*, not a claim that
  they could have.
- **No PII by default.**  Callers supply a ``redact_fn(field, value)`` to scrub
  fields before they are hashed, so the record hash commits to the redacted
  form.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

RECORD_VERSION = "1.0"
SCHEMA_VERSION = "audit-record-v1"

RedactFn = Callable[[str, object], object]

# Narrator taxonomy the audit record emits (a superset of ``NarratorType``;
# "tool" and "retriever" are roles, not graded identities, so they are carried
# only where a caller provides them).
NARRATOR_TYPES = ("human", "model", "scraper", "tool", "dataset", "retriever")


@dataclass
class GradingStrategy:
    """Which strategy graded the chain, and with what parameters."""

    name: str
    version: str
    parameters: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "version": self.version, "parameters": self.parameters}


@dataclass
class ChainNodeAudit:
    """One hand in the transmission chain (or DAG node)."""

    narrator_id: str
    narrator_type: str
    grade: str
    grade_rationale: str
    model_identifier: str | None = None
    model_version: str | None = None
    invocation_timestamp: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    upstream_ids: list[str] = field(default_factory=list)

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
            "upstream_ids": self.upstream_ids,
        }


@dataclass
class WeakestLink:
    """The link that caps the chain, its grade, and why."""

    narrator_id: str
    grade: str
    why: str

    def to_dict(self) -> dict[str, object]:
        return {"narrator_id": self.narrator_id, "grade": self.grade, "why": self.why}


@dataclass
class SourceDocument:
    """A document the chain consumed, identified but content-redacted."""

    uri: str
    retrieved_at: str | None = None
    content_hash: str | None = None
    licence: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "uri": self.uri,
            "retrieved_at": self.retrieved_at,
            "content_hash": self.content_hash,
            "licence": self.licence,
        }


@dataclass
class HumanOversight:
    """Evidence that a human intervened — not merely that they could have."""

    actor_ref: str
    action: str
    timestamp: str
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_ref": self.actor_ref,
            "action": self.action,
            "timestamp": self.timestamp,
            "note": self.note,
        }


@dataclass
class Environment:
    """Where the record was produced."""

    isnad_version: str
    python_version: str
    platform: str

    def to_dict(self) -> dict[str, object]:
        return {
            "isnad_version": self.isnad_version,
            "python_version": self.python_version,
            "platform": self.platform,
        }


@dataclass
class Integrity:
    """The record's self-integrity proof."""

    record_hash: str
    hash_algorithm: str = "SHA-256"
    canonicalisation: str = "RFC8785"
    detached_signature: str | None = None  # reserved — not implemented

    def to_dict(self) -> dict[str, object]:
        return {
            "record_hash": self.record_hash,
            "hash_algorithm": self.hash_algorithm,
            "canonicalisation": self.canonicalisation,
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
    grading_strategy: GradingStrategy
    chain: list[ChainNodeAudit]
    weakest_link: WeakestLink
    source_documents: list[SourceDocument]
    human_oversight: list[HumanOversight]
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
            "grading_strategy": self.grading_strategy.to_dict(),
            "chain": [n.to_dict() for n in self.chain],
            "weakest_link": self.weakest_link.to_dict(),
            "source_documents": [s.to_dict() for s in self.source_documents],
            "human_oversight": [h.to_dict() for h in self.human_oversight],
            "environment": self.environment.to_dict(),
        }
        if include_integrity:
            d["integrity"] = self.integrity.to_dict()
        return d


def new_record_id() -> str:
    """A fresh UUIDv4 record identifier."""
    return str(uuid4())


def utcnow_iso() -> str:
    """Current UTC instant as ISO 8601."""
    return datetime.now(UTC).isoformat()


def apply_redact(fn: RedactFn | None, field_name: str, value: object) -> object:
    """Apply a redaction hook to one field value, if one is supplied."""
    if fn is None:
        return value
    return fn(field_name, value)
