"""API endpoints — narrator registration, retrieval, evidence submission."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter

from isnad.api.auth import require_admin
from isnad.api.dependencies import _metrics_counters, get_registry
from isnad.core.identity import resolve_narrator_id
from isnad.core.registry import RegistryDB
from isnad.types import EvidenceAction, EvidenceAxis, EvidenceType, NarratorGrade

router = APIRouter(prefix="/v1", tags=["narrators"])


def _parse_grade(raw: str) -> NarratorGrade:
    grade_map = {
        "reliable": NarratorGrade.RELIABLE,
        "acceptable": NarratorGrade.ACCEPTABLE,
        "weak": NarratorGrade.WEAK,
        "rejected": NarratorGrade.REJECTED,
        "ungraded": NarratorGrade.UNGRADED,
    }
    return grade_map.get(raw, NarratorGrade.UNGRADED)


def _resolve_from_body(body: dict) -> tuple[str, str, str | None]:
    narrator_id = body["narrator_id"]
    domain = body.get("domain", "general")
    version = body.get("model_version")
    resolved = resolve_narrator_id(narrator_id, version)
    return resolved, domain, version


@router.post("/narrators")
async def register_narrator(
    body: dict, reg: RegistryDB = Depends(get_registry), _: str = Depends(require_admin)
) -> dict:
    grade = _parse_grade(body.get("grade", "ungraded"))
    resolved, domain, version = _resolve_from_body(body)
    reg.registry.register_versioned(
        body["narrator_id"],
        domain,
        version,
        grade=grade,
    )
    reg.flush()
    return {
        "narrator_id": body["narrator_id"],
        "resolved_narrator_id": resolved,
        "model_version": version,
        "domain": domain,
        "grade": grade.value,
    }


@router.get("/narrators/{narrator_id}")
async def get_narrator(
    narrator_id: str,
    domain: str = "general",
    version: str | None = None,
    reg: RegistryDB = Depends(get_registry),
) -> dict:
    resolved = resolve_narrator_id(narrator_id, version)
    narrator = reg.registry.get(resolved, domain)
    if not narrator:
        raise HTTPException(404)
    return {
        "narrator_id": narrator.narrator_id,
        "domain_tag": narrator.domain_tag,
        "grade": narrator.grade.value,
        "adalah": narrator.adalah_grade.value,
        "dabt": narrator.dabt_grade.value,
        "model_version": narrator.model_version,
        "is_active": narrator.is_active,
    }


@router.post("/evidence")
async def submit_evidence(
    body: dict, reg: RegistryDB = Depends(get_registry), _: str = Depends(require_admin)
) -> dict:
    try:
        ev_type = EvidenceType(body.get("evidence_type", "post_hoc_audit"))
        ev_action = EvidenceAction(body.get("action", "tadil"))
        # Axis marks a jarḥ as bearing on integrity (ʿadālah, permanent) or
        # precision (ḍabṭ, windowed/recoverable). If the caller omits it,
        # record_evidence derives a safe default from the evidence type
        # (unambiguously-precision types → PRECISION, else UNSPECIFIED). See
        # EvidenceAxis / default_axis_for.
        ev_axis = EvidenceAxis(body["axis"]) if "axis" in body else None
    except ValueError as e:
        raise HTTPException(400, f"Invalid type: {e}")
    resolved, domain, version = _resolve_from_body(body)
    old_narrator = reg.registry.get(resolved, domain)
    old_grade = old_narrator.grade if old_narrator else None
    new_grade = reg.registry.record_evidence(
        resolved,
        domain,
        ev_type,
        ev_action,
        body.get("description", ""),
        axis=ev_axis,
    )
    reg.flush()
    if old_grade is not None and new_grade != old_grade:
        _metrics_counters["bayesian_grade_changes_total"] += 1
    return {
        "narrator_id": body["narrator_id"],
        "resolved_narrator_id": resolved,
        "model_version": version,
        "domain": domain,
        "new_grade": new_grade.value,
    }
