"""API endpoints — narrator registration, retrieval, evidence submission."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter

from isnad.api.auth import require_admin
from isnad.api.dependencies import _metrics_counters, get_registry
from isnad.core.registry import RegistryDB
from isnad.types import EvidenceAction, EvidenceType, NarratorGrade

router = APIRouter(prefix="/v1", tags=["narrators"])


@router.post("/narrators")
async def register_narrator(
    body: dict, reg: RegistryDB = Depends(get_registry), _: str = Depends(require_admin)
) -> dict:
    grade_map = {
        "reliable": NarratorGrade.RELIABLE,
        "acceptable": NarratorGrade.ACCEPTABLE,
        "weak": NarratorGrade.WEAK,
        "rejected": NarratorGrade.REJECTED,
        "ungraded": NarratorGrade.UNGRADED,
    }
    grade = grade_map.get(body.get("grade", "ungraded"), NarratorGrade.UNGRADED)
    reg.registry.register(body["narrator_id"], body.get("domain", "general"), grade=grade)
    reg.flush()
    return {
        "narrator_id": body["narrator_id"],
        "domain": body.get("domain", "general"),
        "grade": grade.value,
    }


@router.get("/narrators/{narrator_id}")
async def get_narrator(
    narrator_id: str, domain: str = "general", reg: RegistryDB = Depends(get_registry)
) -> dict:
    narrator = reg.registry.get(narrator_id, domain)
    if not narrator:
        raise HTTPException(404)
    return {
        "narrator_id": narrator.narrator_id,
        "domain_tag": narrator.domain_tag,
        "grade": narrator.grade.value,
        "adalah": narrator.adalah_grade.value,
        "dabt": narrator.dabt_grade.value,
        "is_active": narrator.is_active,
    }


@router.post("/evidence")
async def submit_evidence(
    body: dict, reg: RegistryDB = Depends(get_registry), _: str = Depends(require_admin)
) -> dict:
    try:
        ev_type = EvidenceType(body.get("evidence_type", "post_hoc_audit"))
        ev_action = EvidenceAction(body.get("action", "tadil"))
    except ValueError as e:
        raise HTTPException(400, f"Invalid type: {e}")
    old_narrator = reg.registry.get(body["narrator_id"], body.get("domain", "general"))
    old_grade = old_narrator.grade if old_narrator else None
    new_grade = reg.registry.record_evidence(
        body["narrator_id"],
        body.get("domain", "general"),
        ev_type,
        ev_action,
        body.get("description", ""),
    )
    reg.flush()
    if old_grade is not None and new_grade != old_grade:
        _metrics_counters["bayesian_grade_changes_total"] += 1
    return {
        "narrator_id": body["narrator_id"],
        "domain": body.get("domain", "general"),
        "new_grade": new_grade.value,
    }
