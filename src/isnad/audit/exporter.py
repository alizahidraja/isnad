"""Export a graded claim as a tamper-evident AuditRecord.

``build_audit_record`` reads a stored claim, its chain, and the registry's
grades, and emits an ``AuditRecord`` whose ``record_hash`` is a SHA-256 over the
RFC 8785-canonical form of its own payload.  The record is an **evidence
artifact** — it records what was graded and why, so a human auditor can
re-derive the conclusion.  It is not, and must never be read to assert,
compliance with any regulation.
"""

from __future__ import annotations

import hashlib
import os
import platform

from sqlalchemy.orm import Session

from isnad import __version__
from isnad.audit.canonical import canonical_hash, sha256_hex
from isnad.audit.schema import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    Integrity,
    SourceDocument,
    WeakestLink,
    new_record_id,
    utcnow_iso,
)
from isnad.core.chain import Chain, get_chain_from_db, grades_for_chain
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.models import RijalClaim
from isnad.types import NarratorGrade, NarratorType

# NarratorType → the governance-oriented taxonomy the audit record uses.
# "tool" is deliberately absent: ISNAD has no first-class TOOL narrator — a tool
# is a Role (per step), not a NarratorType (a graded identity).
_NARRATOR_TYPE_MAP: dict[str, str] = {
    NarratorType.SOURCE.value: "dataset",
    NarratorType.SCRAPER.value: "scraper",
    NarratorType.MODEL.value: "model",
    NarratorType.HUMAN.value: "human",
}


def _narrator_type_of(registry: Registry, narrator_id: str, domain: str) -> str:
    narrator = registry.get(narrator_id, domain)
    if narrator is None:
        return "model"
    return _NARRATOR_TYPE_MAP.get(narrator.narrator_type.value, "model")


def _host_fingerprint() -> str:
    """A pseudonymous host fingerprint — hashed, never raw."""
    raw = f"{platform.node()}|{platform.machine()}|{os.getenv('USER', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _weakest_link(chain: Chain, grades: list[NarratorGrade]) -> WeakestLink:
    """The narrator that caps the chain, and why."""
    if not chain.links or not grades:
        return WeakestLink(narrator_id="", why="empty chain")
    idx = min(range(len(grades)), key=lambda i: grades[i])
    return WeakestLink(
        narrator_id=chain.links[idx].narrator_id,
        why=f"lowest narrator grade in the chain ({grades[idx].value})",
    )


def build_audit_record(
    claim_id: str,
    session: Session,
    registry: Registry,
    *,
    source_documents: list[SourceDocument] | None = None,
    grading_strategy_name: str = "RefinedWeakestLink",
    grading_strategy_version: str = "1",
) -> AuditRecord:
    """Build a tamper-evident audit record for a stored claim.

    Args:
        claim_id: The stored claim's id.
        session: An active SQLAlchemy session with the claim loaded.
        registry: The graded-narrator registry.
        source_documents: Documents the chain consumed (optional — the exporter
            cannot recover them from the chain store; the caller supplies them).
        grading_strategy_name / _version: The chain-grading strategy in force.

    Returns:
        An ``AuditRecord`` whose ``record_hash`` is over its own payload.
    """
    claim = session.query(RijalClaim).filter_by(claim_id=claim_id).first()
    if claim is None:
        raise KeyError(f"No stored claim with id {claim_id!r}")

    chain = get_chain_from_db(session, claim_id) or Chain([])
    grades = grades_for_chain(registry, chain)
    transforms = [link.transform_type for link in chain.links]
    final_grade = grade_chain(grades, transforms, is_complete=chain.is_complete)

    nodes: list[ChainNodeAudit] = []
    for link, grade in zip(chain.links, grades, strict=True):
        narrator = registry.get(link.narrator_id, link.domain)
        nodes.append(
            ChainNodeAudit(
                narrator_id=link.narrator_id,
                narrator_type=_narrator_type_of(registry, link.narrator_id, link.domain),
                grade=grade.value,
                grade_rationale=(
                    f"registry grade {grade.value} for {link.narrator_id} in domain {link.domain}"
                ),
                model_identifier=link.narrator_id,
                model_version=(
                    narrator.model_version if narrator and narrator.model_version else link.version
                ),
                invocation_timestamp=None,
                input_hash=sha256_hex(link.input_snapshot) if link.input_snapshot else None,
                output_hash=sha256_hex(link.output_snapshot) if link.output_snapshot else None,
            )
        )

    record = AuditRecord(
        record_id=new_record_id(),
        record_version="1",
        generated_at=utcnow_iso(),
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        final_grade=final_grade.value,
        grading_strategy_name=grading_strategy_name,
        grading_strategy_version=grading_strategy_version,
        chain=nodes,
        weakest_link=_weakest_link(chain, grades),
        source_documents=source_documents or [],
        environment=Environment(
            isnad_version=__version__,
            python_version=platform.python_version(),
            host_fingerprint=_host_fingerprint(),
        ),
    )
    # The hash is over the payload *without* the integrity block, so the record
    # is self-authenticating: verify() recomputes it and compares.
    record.integrity = Integrity(
        record_hash=canonical_hash(record.to_dict(include_integrity=False))
    )
    return record
