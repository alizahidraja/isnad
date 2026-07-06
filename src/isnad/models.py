"""Pydantic DTOs and SQLAlchemy ORM models for the Isnād–Rijāl framework.

Implements the paper's normative schema (§5):
- rijal_claims: one row per claim with full transmission chain
- narrator_registry: one row per (narrator, domain)

Plus the normalized additions the paper notes as correct at scale:
- chain_links: normalized link table with FKs
- narrator_evidence: append-only jarḥ–taʿdīl event log
- review_queue: claims awaiting human adjudication
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from isnad.types import (
    Action,
    AdalahGrade,
    ChainGrade,
    ChainStatus,
    ContentVerdict,
    DabtGrade,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    NarratorType,
    TransformType,
)

# ===========================================================================
# SQLAlchemy base
# ===========================================================================


class Base(DeclarativeBase):
    pass


# ===========================================================================
# Pydantic DTOs — wire format / validation boundary
# ===========================================================================


class ChainLinkDTO(BaseModel):
    """A single link in a claim's transmission chain."""

    model_config = ConfigDict(use_enum_values=True)

    step: int = Field(..., ge=0, description="Zero-indexed position in chain")
    narrator_id: str = Field(..., description="e.g. 'pdf-scraper', 'ingest:M@v'")
    version: str = Field(default="unknown")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    trace_id: str = Field(default="")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    transform_type: TransformType = Field(
        default=TransformType.PASS_THROUGH,
        description="Destructive vs generative vs pass-through",
    )
    domain: str = Field(default="general")


class NarratorDTO(BaseModel):
    """A narrator entry from the registry."""

    model_config = ConfigDict(use_enum_values=True)

    narrator_id: str
    domain_tag: str
    narrator_type: NarratorType
    grade: NarratorGrade = NarratorGrade.UNGRADED
    adalah_grade: AdalahGrade = AdalahGrade.UNASSESSED
    dabt_grade: DabtGrade = DabtGrade.UNASSESSED
    known_error_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    model_version: str | None = None
    model_family: str | None = Field(
        default=None, description="Shared model family for correlation detection"
    )
    upstream_source: str | None = Field(
        default=None, description="Upstream origin for madār detection"
    )
    is_active: bool = True


class EvidenceDTO(BaseModel):
    """An immutable evidence log entry (jarḥ–taʿdīl event)."""

    model_config = ConfigDict(use_enum_values=True)

    narrator_id: str
    domain_tag: str
    evidence_type: EvidenceType
    action: EvidenceAction = EvidenceAction.NEUTRAL
    description: str = ""
    metadata_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReviewQueueItemDTO(BaseModel):
    """An item in the human review queue."""

    model_config = ConfigDict(use_enum_values=True)

    claim_id: str
    page_slug: str
    claim_text: str
    chain_grade: ChainGrade
    content_verdict: ContentVerdict
    matrix_action: Action
    conflicting_claim_ids: list[str] = Field(default_factory=list)
    notes: str = ""


# ===========================================================================
# SQLAlchemy ORM models — persistence layer
# ===========================================================================


class RijalClaim(Base):
    """A claim with its full transmission chain (paper's normative schema)."""

    __tablename__ = "rijal_claims"

    claim_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    page_slug: Mapped[str] = mapped_column(String(256), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    narrator_chain: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=list, comment="Denormalized audit copy"
    )
    chain_grade: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="ChainGrade enum value; NULL until graded"
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Lifecycle: supersession, not deletion",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="claim_id of superseding claim"
    )
    chain_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ChainStatus.ACTIVE.value,
    )

    # Relationships
    links: Mapped[list[ChainLink]] = relationship(
        "ChainLink",
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="ChainLink.step",
    )

    __table_args__ = (
        Index("ix_rijal_claims_page_slug", "page_slug"),
        Index("ix_rijal_claims_chain_status", "chain_status"),
    )


class ChainLink(Base):
    """Normalized chain link (paper notes this as correct at scale)."""

    __tablename__ = "chain_links"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    claim_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("rijal_claims.claim_id", ondelete="CASCADE"),
        nullable=False,
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    narrator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(128), default="unknown")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(256), default="")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    transform_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TransformType.PASS_THROUGH.value,
    )
    domain: Mapped[str] = mapped_column(String(128), default="general")

    # Relationship
    claim: Mapped[RijalClaim] = relationship("RijalClaim", back_populates="links")

    __table_args__ = (
        Index("ix_chain_links_claim_step", "claim_id", "step", unique=True),
        Index("ix_chain_links_narrator", "narrator_id"),
    )


class NarratorRegistry(Base):
    """Narrator registry: one row per (narrator, domain)."""

    __tablename__ = "narrator_registry"

    narrator_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    domain_tag: Mapped[str] = mapped_column(String(128), primary_key=True)
    narrator_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=NarratorType.MODEL.value,
    )
    grade: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=NarratorGrade.UNGRADED.value,
    )
    adalah_grade: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AdalahGrade.UNASSESSED.value,
    )
    dabt_grade: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DabtGrade.UNASSESSED.value,
    )
    known_error_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="NULL = uncalibrated; ordinal grade leads"
    )
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_family: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="For correlation (madār) detection"
    )
    upstream_source: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="Upstream source for correlation detection"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    evidence_log: Mapped[list[NarratorEvidence]] = relationship(
        "NarratorEvidence",
        back_populates="narrator",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_narrator_registry_grade", "grade"),
        Index("ix_narrator_registry_is_active", "is_active"),
    )


class NarratorEvidence(Base):
    """Append-only jarḥ–taʿdīl event log."""

    __tablename__ = "narrator_evidence"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    narrator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    domain_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=EvidenceType.EVAL_HARNESS.value,
    )
    action: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=EvidenceAction.NEUTRAL.value,
    )
    description: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    # Composite FK to narrator_registry
    __table_args__ = (
        ForeignKeyConstraint(
            ["narrator_id", "domain_tag"],
            ["narrator_registry.narrator_id", "narrator_registry.domain_tag"],
            ondelete="CASCADE",
        ),
        Index("ix_narrator_evidence_narrator", "narrator_id", "domain_tag"),
        Index("ix_narrator_evidence_created", "created_at"),
    )

    narrator: Mapped[NarratorRegistry] = relationship(
        "NarratorRegistry",
        back_populates="evidence_log",
    )


class ReviewQueue(Base):
    """Claims awaiting human adjudication."""

    __tablename__ = "review_queue"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    claim_id: Mapped[str] = mapped_column(String(128), nullable=False)
    page_slug: Mapped[str] = mapped_column(String(256), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    chain_grade: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="ChainGrade enum value"
    )
    content_verdict: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="ContentVerdict enum value"
    )
    matrix_action: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Action enum value"
    )
    conflicting_claim_ids: Mapped[dict[str, object]] = mapped_column(
        JSON, default=list, comment="List of conflicting claim IDs"
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_review_queue_claim", "claim_id"),
        Index("ix_review_queue_created", "created_at"),
    )
