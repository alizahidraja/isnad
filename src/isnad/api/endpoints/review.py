"""API endpoints — human review queue for gated/quarantined/contradicted claims.

Wires up the previously-unused ReviewQueue table (issue #11): claims routed to
REVIEW/QUARANTINE/REJECT_AND_QUARANTINE_NARRATOR are inserted here by
submit_claim() (see api/endpoints/claims.py), including conflicting_claim_ids
when the routing was triggered by a content contradiction — so a reviewer can
pull up both sides of a contradiction together, rather than only ever seeing
the newly-submitted claim in isolation.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter
from sqlalchemy.orm import Session

from isnad.api.auth import require_auth
from isnad.api.dependencies import get_db
from isnad.models import ReviewQueue

router = APIRouter(prefix="/v1", tags=["review"])


def _serialize(row: ReviewQueue) -> dict:
    return {
        "id": str(row.id),
        "claim_id": row.claim_id,
        "page_slug": row.page_slug,
        "claim_text": row.claim_text,
        "chain_grade": row.chain_grade,
        "content_verdict": row.content_verdict,
        "matrix_action": row.matrix_action,
        "conflicting_claim_ids": row.conflicting_claim_ids or [],
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolution": row.resolution,
        "reviewer_id": row.reviewer_id,
    }


@router.get("/review-queue")
async def list_review_queue(
    session: Session = Depends(get_db), _: str = Depends(require_auth)
) -> dict:
    """List unresolved review-queue items, most recent first.

    Requires auth: this is the internal human-review surface, exposing claim
    text and contradiction links — unlike the public claim/narrator read
    endpoints, which are the verification surface.
    """
    rows = (
        session
        .query(ReviewQueue)
        .filter(ReviewQueue.resolved_at.is_(None))
        .order_by(ReviewQueue.created_at.desc())
        .all()
    )
    return {"total": len(rows), "items": [_serialize(r) for r in rows]}


@router.get("/review-queue/{item_id}")
async def get_review_queue_item(
    item_id: str, session: Session = Depends(get_db), _: str = Depends(require_auth)
) -> dict:
    try:
        parsed_id = UUID(item_id)
    except ValueError:
        raise HTTPException(404, "Review queue item not found") from None
    row = session.query(ReviewQueue).filter_by(id=parsed_id).first()
    if row is None:
        raise HTTPException(404, "Review queue item not found")
    return _serialize(row)
