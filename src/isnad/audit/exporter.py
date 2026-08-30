"""Export a graded claim as a tamper-evident AuditRecord.

``build_audit_record`` reads a stored claim, its chain, and the registry's
grades, and emits an ``AuditRecord`` whose ``record_hash`` is a SHA-256 over the
RFC 8785-canonical form of its own payload.  The record is an **evidence
artifact** — it records what was graded and why, so a human auditor can
re-derive the conclusion.  It is not, and must never be read to assert,
compliance with any regulation.

The chain is an explicit **DAG** (``upstream_ids``), not just a list: the
database path builds a linear chain (each node's upstream is its predecessor),
and ``build_audit_record_from_nodes`` lets callers supply an arbitrary DAG.
"""

from __future__ import annotations

import platform

from sqlalchemy.orm import Session

from isnad import __version__
from isnad.audit.canonical import canonical_hash, sha256_hex
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
    new_record_id,
    utcnow_iso,
)
from isnad.core.chain import Chain, get_chain_from_db, grades_for_chain
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.models import RijalClaim
from isnad.types import NarratorGrade, NarratorType

# NarratorType → the governance-oriented taxonomy the audit record uses.
# "retriever" is a Role (per step), not a graded NarratorType; "tool" IS a
# graded NarratorType now (issue #59).
_NARRATOR_TYPE_MAP: dict[str, str] = {
    NarratorType.SOURCE.value: "dataset",
    NarratorType.SCRAPER.value: "scraper",
    NarratorType.MODEL.value: "model",
    NarratorType.HUMAN.value: "human",
    NarratorType.TOOL.value: "tool",
}


def _r(fn: RedactFn | None, field_name: str, value: object) -> object:
    return apply_redact(fn, field_name, value)


def _narrator_type_of(registry: Registry, narrator_id: str, domain: str) -> str:
    narrator = registry.get(narrator_id, domain)
    if narrator is None:
        return "model"
    return _NARRATOR_TYPE_MAP.get(narrator.narrator_type.value, "model")


def build_audit_record(
    claim_id: str,
    session: Session,
    registry: Registry,
    *,
    source_documents: list[SourceDocument] | None = None,
    human_oversight: list[HumanOversight] | None = None,
    grading_strategy: GradingStrategy | None = None,
    redact_fn: RedactFn | None = None,
) -> AuditRecord:
    """Build a tamper-evident audit record for a stored claim (linear chain)."""
    claim = session.query(RijalClaim).filter_by(claim_id=claim_id).first()
    if claim is None:
        raise KeyError(f"No stored claim with id {claim_id!r}")

    chain = get_chain_from_db(session, claim_id) or Chain([])
    grades = grades_for_chain(registry, chain)
    transforms = [link.transform_type for link in chain.links]
    final_grade = grade_chain(grades, transforms, is_complete=chain.is_complete)

    nodes: list[ChainNodeAudit] = []
    for i, (link, grade) in enumerate(zip(chain.links, grades, strict=True)):
        narrator = registry.get(link.narrator_id, link.domain)
        upstream = [chain.links[i - 1].narrator_id] if i > 0 else []
        nodes.append(
            ChainNodeAudit(
                narrator_id=str(_r(redact_fn, "narrator_id", link.narrator_id)),
                narrator_type=_narrator_type_of(registry, link.narrator_id, link.domain),
                grade=grade.value,
                grade_rationale=(
                    f"registry grade {grade.value} for {link.narrator_id} in domain {link.domain}"
                ),
                model_identifier=str(_r(redact_fn, "model_identifier", link.narrator_id)),
                model_version=(
                    narrator.model_version if narrator and narrator.model_version else link.version
                ),
                invocation_timestamp=link.timestamp,
                input_hash=sha256_hex(link.input_snapshot) if link.input_snapshot else None,
                output_hash=sha256_hex(link.output_snapshot) if link.output_snapshot else None,
                upstream_ids=upstream,
            )
        )

    weakest = _weakest_link(chain, grades)
    strategy = grading_strategy or GradingStrategy(name="RefinedWeakestLink", version="1")
    env = Environment(
        isnad_version=__version__,
        python_version=platform.python_version(),
        platform=platform.platform(),
    )

    return build_audit_record_from_nodes(
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        final_grade=final_grade.value,
        grading_strategy=strategy,
        nodes=nodes,
        weakest_link=weakest,
        source_documents=source_documents or [],
        human_oversight=human_oversight or [],
        environment=env,
        redact_fn=redact_fn,
    )


def build_audit_record_from_nodes(
    *,
    claim_id: str,
    claim_text: str,
    final_grade: str,
    grading_strategy: GradingStrategy,
    nodes: list[ChainNodeAudit],
    weakest_link: WeakestLink,
    source_documents: list[SourceDocument] | None = None,
    human_oversight: list[HumanOversight] | None = None,
    environment: Environment | None = None,
    redact_fn: RedactFn | None = None,
) -> AuditRecord:
    """Assemble + hash an audit record from explicit nodes (for DAGs).

    This is the lower-level entry point: callers build the ``nodes`` (with
    explicit ``upstream_ids`` for a DAG) and this function redacts, assembles,
    and self-hashes the record.
    """
    env = environment or Environment(
        isnad_version=__version__,
        python_version=platform.python_version(),
        platform=platform.platform(),
    )
    record = AuditRecord(
        record_id=new_record_id(),
        record_version="1.0",
        generated_at=utcnow_iso(),
        claim_id=str(_r(redact_fn, "claim_id", claim_id)),
        claim_text=str(_r(redact_fn, "claim_text", claim_text)),
        final_grade=final_grade,
        grading_strategy=grading_strategy,
        chain=nodes,
        weakest_link=weakest_link,
        source_documents=[
            SourceDocument(
                uri=str(_r(redact_fn, "uri", d.uri)),
                retrieved_at=d.retrieved_at,
                content_hash=d.content_hash,
                licence=d.licence,
            )
            for d in (source_documents or [])
        ],
        human_oversight=[
            HumanOversight(
                actor_ref=str(_r(redact_fn, "actor_ref", h.actor_ref)),
                action=h.action,
                timestamp=h.timestamp,
                note=str(_r(redact_fn, "note", h.note)),
            )
            for h in (human_oversight or [])
        ],
        environment=env,
    )
    record.integrity = Integrity(
        record_hash=canonical_hash(record.to_dict(include_integrity=False))
    )
    return record


def _weakest_link(chain: Chain, grades: list[NarratorGrade]) -> WeakestLink:
    """The narrator that caps the chain, its grade, and why."""
    if not chain.links or not grades:
        return WeakestLink(narrator_id="", grade="ungraded", why="empty chain")
    idx = min(range(len(grades)), key=lambda i: grades[i])
    return WeakestLink(
        narrator_id=chain.links[idx].narrator_id,
        grade=grades[idx].value,
        why=f"lowest narrator grade in the chain ({grades[idx].value})",
    )
