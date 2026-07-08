"""ISNAD API — FastAPI service for claim-level provenance.

Deployable REST API wrapping the ISNAD framework.
Submit claims with chains, retrieve graded decisions,
manage narrators, and submit evidence.

Usage:
    uvicorn isnad.api.main:app --reload
    # or
    docker compose up
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from isnad.chain import Chain, ChainLinkSpec
from isnad.grading import grade_chain
from isnad.matrix import decide, describe_action
from isnad.registry import Registry
from isnad.types import (
    Action,
    ChainGrade,
    ContentVerdict,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    TransformType,
)

# ── API Key auth ───────────────────────────────────────────────

API_KEYS = {
    k: r
    for k, r in [
        kv.split(":")
        for kv in os.environ.get("ISNAD_API_KEYS", "isnad-admin:admin,isnad-reader:reader").split(
            ","
        )
        if ":" in kv
    ]
} or {"isnad-admin": "admin"}

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_auth(api_key: str | None = Security(api_key_header)) -> str:
    if not api_key or api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return API_KEYS[api_key]


def require_admin(role: str = Depends(require_auth)) -> str:
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return role


# ── App state ──────────────────────────────────────────────────

@dataclass
class AppState:
    registry: Registry
    claims: dict[str, dict] = field(default_factory=dict)


# ── Lifespan ───────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.isnad = AppState(registry=Registry())
    yield


app = FastAPI(
    title="ISNAD — Claim-Level Provenance API",
    version="2.0.0",
    description="Submit claims with transmission chains and get graded trust decisions.",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Models ─────────────────────────────────────────────────────


class ClaimSubmit(BaseModel):
    claim_text: str = Field(..., description="The claim text")
    page_slug: str = Field(default="default", description="Source page identifier")
    domain: str = Field(default="general", description="Domain tag for grading")
    chain: list[dict] = Field(
        default_factory=list,
        description="Transmission chain: [{'narrator_id': ..., 'version': ..., 'transform_type': ...}]",
    )


class ClaimResponse(BaseModel):
    claim_id: str
    claim_text: str
    chain_grade: str
    content_verdict: str
    action: str
    description: str
    chain: list[dict]
    served: bool
    quarantined: bool


class NarratorSubmit(BaseModel):
    narrator_id: str
    domain: str = "general"
    narrator_type: str = "model"
    grade: str = "ungraded"


class EvidenceSubmit(BaseModel):
    narrator_id: str
    domain: str = "general"
    evidence_type: str = "post_hoc_audit"
    action: str = "tadil"
    description: str = ""
    claim_id: str | None = None


# ── Endpoints ──────────────────────────────────────────────────


@app.get("/v1/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.0.0", "claims_tracked": len(app.state.isnad.claims)}


@app.get("/v1/metrics")
async def metrics(request: Request) -> dict:
    reg = app.state.isnad.registry
    return {
        "claims_total": len(app.state.isnad.claims),
        "narrators_total": len(reg),
        "timestamp": time.time(),
    }


@app.post("/v1/claims", response_model=ClaimResponse)
async def submit_claim(
    body: ClaimSubmit,
    role: str = Depends(require_auth),
) -> dict:
    state: AppState = app.state.isnad
    reg = state.registry

    # Build chain
    specs = []
    for i, link in enumerate(body.chain):
        specs.append(
            ChainLinkSpec(
                narrator_id=link.get("narrator_id", f"step-{i}"),
                step=i,
                version=link.get("version", "unknown"),
                transform_type=TransformType(
                    link.get("transform_type", "pass_through")
                ),
                domain=body.domain,
                trace_id=link.get("trace_id", str(uuid.uuid4())[:8]),
            )
        )
    chain = Chain(specs)

    # Grade
    link_grades = [reg.get_grade(link.narrator_id, link.domain) for link in chain.links]
    link_transforms = [link.transform_type for link in chain.links]
    cg = grade_chain(link_grades, link_transforms, is_complete=chain.is_complete)

    # Content verdict (default: UNVERIFIABLE — caller supplies real critic)
    cv = ContentVerdict.UNVERIFIABLE

    # Decision
    action = decide(cg, cv)
    desc = describe_action(cg, cv)

    claim_id = str(uuid.uuid4())[:16]
    record = {
        "claim_id": claim_id,
        "claim_text": body.claim_text,
        "chain_grade": cg.value,
        "content_verdict": cv.value,
        "action": action.value,
        "description": desc,
        "chain": chain.to_jsonb(),
        "served": action in (Action.SERVE, Action.SERVE_WITH_CAVEAT),
        "quarantined": action in (
            Action.QUARANTINE,
            Action.REJECT_AND_QUARANTINE_NARRATOR,
        ),
        "domain": body.domain,
        "page_slug": body.page_slug,
    }
    state.claims[claim_id] = record

    return record


@app.get("/v1/claims/{claim_id}")
async def get_claim(claim_id: str) -> dict:
    state: AppState = app.state.isnad
    if claim_id not in state.claims:
        raise HTTPException(404, "Claim not found")
    return state.claims[claim_id]


@app.get("/v1/claims/{claim_id}/chain")
async def get_claim_chain(claim_id: str) -> dict:
    state: AppState = app.state.isnad
    if claim_id not in state.claims:
        raise HTTPException(404, "Claim not found")
    record = state.claims[claim_id]
    return {
        "claim_id": claim_id,
        "chain": record["chain"],
        "chain_grade": record["chain_grade"],
        "action": record["action"],
    }


@app.post("/v1/narrators")
async def register_narrator(
    body: NarratorSubmit,
    role: str = Depends(require_admin),
) -> dict:
    reg = app.state.isnad.registry
    grade_map = {
        "reliable": NarratorGrade.RELIABLE,
        "acceptable": NarratorGrade.ACCEPTABLE,
        "weak": NarratorGrade.WEAK,
        "rejected": NarratorGrade.REJECTED,
        "ungraded": NarratorGrade.UNGRADED,
    }
    grade = grade_map.get(body.grade, NarratorGrade.UNGRADED)
    reg.register(body.narrator_id, body.domain, grade=grade)
    return {"narrator_id": body.narrator_id, "domain": body.domain, "grade": grade.value}


@app.get("/v1/narrators/{narrator_id}")
async def get_narrator(narrator_id: str, domain: str = "general") -> dict:
    reg = app.state.isnad.registry
    narrator = reg.get(narrator_id, domain)
    if not narrator:
        raise HTTPException(404, "Narrator not found")
    return {
        "narrator_id": narrator.narrator_id,
        "domain_tag": narrator.domain_tag,
        "grade": narrator.grade.value,
        "adalah": narrator.adalah_grade.value,
        "dabt": narrator.dabt_grade.value,
        "is_active": narrator.is_active,
    }


@app.post("/v1/evidence")
async def submit_evidence(
    body: EvidenceSubmit,
    role: str = Depends(require_admin),
) -> dict:
    reg = app.state.isnad.registry
    try:
        ev_type = EvidenceType(body.evidence_type)
        ev_action = EvidenceAction(body.action)
    except ValueError as e:
        raise HTTPException(400, f"Invalid evidence type or action: {e}")

    new_grade = reg.record_evidence(
        body.narrator_id, body.domain, ev_type, ev_action, body.description
    )
    return {
        "narrator_id": body.narrator_id,
        "domain": body.domain,
        "new_grade": new_grade.value,
    }


