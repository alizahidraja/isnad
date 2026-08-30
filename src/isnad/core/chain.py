"""Isnād Engine — append-only construction and storage of claim transmission chains.

Implements paper §4.1:
- Every claim carries its full ordered, gap-checked transmission chain.
- Each link carries narrator ref, version, transform type, timestamp, trace id.
- Completeness (ittiṣāl) is an epistemic property: a chain with a gap is
  munqaṭiʿ and automatically capped at DAIF.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from isnad.core.identity import resolve_narrator_id
from isnad.models import ChainLink, RijalClaim
from isnad.types import AdalahGrade, ChainStatus, NarratorGrade, TransformType

if TYPE_CHECKING:
    from isnad.core.registry import Registry


def normalize_claim_text(text: str) -> str:
    """Normalize claim text for hashing and comparison.

    Normalization: lowercase, strip, collapse whitespace.
    This is deliberately simple — a production system would add
    domain-specific normalization (unit conversion, formula canonicalization).
    """
    return " ".join(text.lower().strip().split())


def hash_claim_text(normalized: str) -> str:
    """SHA-256 hash of normalized claim text → claim_id."""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def make_claim_id(text: str) -> str:
    """Normalize + hash claim text to produce a deterministic claim_id."""
    return hash_claim_text(normalize_claim_text(text))


class ChainLinkSpec:
    """Specification for a single chain link — used to build chains."""

    def __init__(
        self,
        narrator_id: str,
        step: int,
        *,
        version: str = "unknown",
        transform_type: TransformType = TransformType.PASS_THROUGH,
        trace_id: str = "",
        domain: str = "general",
        confidence: float | None = None,
        input_snapshot: str | None = None,
        output_snapshot: str | None = None,
        document_hashes: list[str] | None = None,
    ):
        self.narrator_id = narrator_id
        self.step = step
        self.version = version
        self.transform_type = transform_type
        self.trace_id = trace_id
        self.domain = domain
        self.confidence = confidence
        # Claim text entering/leaving this link's transformation — only
        # meaningful for GENERATIVE links, used by core/fidelity.py to check
        # whether the output actually follows from the input (issue #11,
        # direction 3: surface *where* a chain degraded, not just that it did).
        self.input_snapshot = input_snapshot
        self.output_snapshot = output_snapshot
        # Retrieved-document content hashes for this link — used by the
        # corroboration engine's madār check (issue #125): two chains that
        # retrieved the same document are one source, not two.
        self.document_hashes = document_hashes or []

    def to_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "narrator_id": self.narrator_id,
            "version": self.version,
            "transform_type": self.transform_type.value,
            "trace_id": self.trace_id,
            "domain": self.domain,
            "confidence": self.confidence,
            "input_snapshot": self.input_snapshot,
            "output_snapshot": self.output_snapshot,
            "document_hashes": list(self.document_hashes),
            "timestamp": datetime.now(UTC).isoformat(),
        }


class Chain:
    """An ordered, gap-checked transmission chain for a claim."""

    def __init__(self, links: list[ChainLinkSpec] | None = None):
        self._links: list[ChainLinkSpec] = []
        if links:
            for link in sorted(links, key=lambda ln: ln.step):
                self.add_link(link)

    @property
    def links(self) -> list[ChainLinkSpec]:
        return list(self._links)

    @property
    def is_complete(self) -> bool:
        """Check ittiṣāl: no gaps in the step sequence."""
        if not self._links:
            return False
        steps = {link.step for link in self._links}
        expected = set(range(len(self._links)))
        return steps == expected

    @property
    def chain_status(self) -> ChainStatus:
        return ChainStatus.COMPLETE if self.is_complete else ChainStatus.MUNQATI

    @property
    def narrator_ids(self) -> list[str]:
        return [link.narrator_id for link in self._links]

    @property
    def domains(self) -> list[str]:
        return [link.domain for link in self._links]

    def add_link(self, link: ChainLinkSpec) -> None:
        """Add a link.  Steps must be consecutive; gaps = munqaṭiʿ."""
        self._links.append(link)
        self._links.sort(key=lambda ln: ln.step)

    def to_jsonb(self) -> list[dict[str, object]]:
        """Serialize to the JSONB format for rijal_claims.narrator_chain."""
        return [link.to_dict() for link in self._links]

    def __len__(self) -> int:
        return len(self._links)

    def __repr__(self) -> str:
        ids = " → ".join(self.narrator_ids) if self._links else "(empty)"
        status = "complete" if self.is_complete else "munqaṭiʿ"
        return f"Chain({ids}) [{status}]"


def resolved_narrator_ids_for_chain(chain: Chain) -> list[str]:
    """Resolve alias@version ids for each link (grade lookup keys)."""
    return [resolve_narrator_id(link.narrator_id, link.version) for link in chain.links]


def grades_for_chain(registry: Registry, chain: Chain) -> list[NarratorGrade]:
    """Look up per-link narrator grades using version-aware registry keys."""
    return [
        registry.get_grade_for_link(link.narrator_id, link.domain, link.version)
        for link in chain.links
    ]


def adalah_grades_for_chain(registry: Registry, chain: Chain) -> list[AdalahGrade]:
    """Look up per-link ʿadālah (integrity) grades, mirroring grades_for_chain().

    Kept as a separate axis (issue #11) rather than folded into NarratorGrade —
    a narrator's precision/accuracy track record and its integrity status are
    distinct properties (paper §4.2) and should be checked independently.
    """
    return [registry.get_adalah_grade(link.narrator_id, link.domain) for link in chain.links]


# ===========================================================================
# Chain persistence
# ===========================================================================


def store_claim(
    session: Session,
    claim_text: str,
    page_slug: str,
    chain: Chain,
    *,
    chain_grade: str | None = None,
    claim_id: str | None = None,
    content_verdict: str | None = None,
    action: str | None = None,
) -> RijalClaim:
    """Store a claim with its chain in the database.

    ``claim_id`` defaults to the deterministic content hash
    (``hash_claim_text(normalized)``), which makes re-ingesting the same text
    update in-place (content-addressed knowledge base). A caller that wants
    event-level uniqueness — e.g. the API, which assigns each submission a
    fresh UUID so two claims with the same normalized text can corroborate —
    may pass its own ``claim_id``.

    ``content_verdict`` and ``action`` are persisted so that restart
    rehydration is faithful: without them, a held SAHIH × CONTRADICTION
    (REVIEW) would re-derive as SAHIH × UNVERIFIABLE (SERVE_WITH_CAVEAT),
    silently destroying the contradiction signal.

    Uses session.merge() to avoid identity-map conflicts when re-ingesting.

    Returns the RijalClaim ORM object.
    """
    normalized = normalize_claim_text(claim_text)
    claim_id = claim_id or hash_claim_text(normalized)

    # Check if claim already exists in this session or DB
    existing = session.query(RijalClaim).filter_by(claim_id=claim_id).first()

    if existing is not None:
        # Update in-place: same claim, refreshed chain + grade
        existing.page_slug = page_slug
        existing.claim_text = claim_text
        existing.narrator_chain = chain.to_jsonb()
        existing.chain_grade = chain_grade
        existing.content_verdict = content_verdict
        existing.action = action
        existing.chain_status = chain.chain_status.value
        existing.valid_from = datetime.now(UTC)
        # Delete old links via query to avoid ORM relationship staleness
        session.query(ChainLink).filter_by(claim_id=claim_id).delete()
        session.flush()
        claim = existing
    else:
        claim = RijalClaim(
            claim_id=claim_id,
            page_slug=page_slug,
            claim_text=claim_text,
            normalized_text=normalized,
            narrator_chain=chain.to_jsonb(),
            chain_grade=chain_grade,
            content_verdict=content_verdict,
            action=action,
            chain_status=chain.chain_status.value,
        )
        session.add(claim)

    # Normalized links
    for link_spec in chain.links:
        link = ChainLink(
            claim_id=claim_id,
            step=link_spec.step,
            narrator_id=link_spec.narrator_id,
            version=link_spec.version,
            transform_type=link_spec.transform_type.value,
            trace_id=link_spec.trace_id,
            domain=link_spec.domain,
            confidence=link_spec.confidence,
            input_snapshot=link_spec.input_snapshot,
            output_snapshot=link_spec.output_snapshot,
            document_hashes=list(link_spec.document_hashes),
        )
        session.add(link)

    session.flush()
    return claim


def get_chain_from_db(session: Session, claim_id: str) -> Chain | None:
    """Reconstruct a Chain from the normalized chain_links table."""
    links = session.query(ChainLink).filter_by(claim_id=claim_id).order_by(ChainLink.step).all()
    if not links:
        return None

    specs = [
        ChainLinkSpec(
            narrator_id=link.narrator_id,
            step=link.step,
            version=link.version,
            transform_type=TransformType(link.transform_type),
            trace_id=link.trace_id,
            domain=link.domain,
            confidence=link.confidence,
            input_snapshot=link.input_snapshot,
            output_snapshot=link.output_snapshot,
            document_hashes=list(link.document_hashes or []),
        )
        for link in links
    ]
    return Chain(specs)
