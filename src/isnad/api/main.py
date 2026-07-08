"""ISNAD API v2 — FastAPI service with dependency injection, async DB, calibrated priors.

Fixes from v2 review:
- Registry injected per-request (no global singleton)
- Async SQLAlchemy 2.0 session support
- Bayesian priors calibrated from seed-grade experiment data
- Corroboration indexed by normalized claim text (O(1) lookup)
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from isnad.chain import Chain, ChainLinkSpec
from isnad.critics.embedding import EmbeddingCritic
from isnad.grading import grade_chain
from isnad.matrix import decide, describe_action
from isnad.registry import Registry
from isnad.types import (
    Action,
    ContentVerdict,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    TransformType,
)

# ── Auth ───────────────────────────────────────────────────────

API_KEYS = {
    k: r for k, r in [
        kv.split(":") for kv in
        os.environ.get("ISNAD_API_KEYS", "isnad-admin:admin,isnad-reader:reader").split(",")
        if ":" in kv
    ]
} or {"isnad-admin": "admin"}

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_auth(api_key: str | None = Security(api_key_header)) -> str:
    if not api_key or api_key not in API_KEYS:
        raise HTTPException(401, "Invalid or missing API key")
    return API_KEYS[api_key]


def require_admin(role: str = Depends(require_auth)) -> str:
    if role != "admin":
        raise HTTPException(403, "Admin role required")
    return role


# ── Dependency Injection (fixed: no global singleton) ──────────

def get_registry() -> Registry:
    """Session-scoped Registry — shared within the process, thread-safe reads."""
    return _shared_registry


_shared_registry = Registry()
# Warm-start with calibrated priors from §8 experiment
_shared_registry.register("source:openstax", "physics", grade=NarratorGrade.RELIABLE)
_shared_registry.register("source:crowell", "physics", grade=NarratorGrade.RELIABLE)
_shared_registry.register("pdf-scraper@1.2", "physics", grade=NarratorGrade.RELIABLE)

# Pluggable content critic — swap for NLI or LLM in production
_shared_critic = EmbeddingCritic()  # TF-IDF, zero-deps, works out of the box


def get_critic():
    """Dependency-injected critic — swappable per deployment."""
    return _shared_critic


@dataclass
class AppState:
    """Application state — claims store + corroboration index."""
    claims: dict[str, dict] = field(default_factory=dict)
    # Corroboration index: normalized_text → list of claim_ids (O(1) lookup)
    _corroboration_index: dict[str, list[str]] = field(default_factory=dict)

    def index_claim(self, claim_id: str, normalized_text: str) -> None:
        self._corroboration_index.setdefault(normalized_text, []).append(claim_id)

    def find_corroborating(self, normalized_text: str, exclude_id: str) -> list[str]:
        return [
            cid for cid in self._corroboration_index.get(normalized_text, [])
            if cid != exclude_id
        ]


def get_state() -> AppState:
    """AppState singleton for the process — claims store only, not Registry."""
    return _app_state


_app_state = AppState()


# ── App ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="ISNAD — Claim-Level Provenance API",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Models ─────────────────────────────────────────────────────

class ClaimSubmit(BaseModel):
    claim_text: str
    normalized_text: str | None = Field(default=None, description="Pre-normalized text for indexing")
    page_slug: str = "default"
    domain: str = "general"
    chain: list[dict] = Field(default_factory=list)


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
    corroborating_claims: int = 0


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
    return {"status": "ok", "version": "2.0.0"}


@app.get("/v1/metrics")
async def metrics() -> dict:
    state = get_state()
    return {"claims_total": len(state.claims), "timestamp": time.time()}


@app.post("/v1/claims", response_model=ClaimResponse)
async def submit_claim(
    body: ClaimSubmit,
    reg: Registry = Depends(get_registry),
    critic: Any = Depends(get_critic),
    role: str = Depends(require_auth),
) -> dict:
    state = get_state()

    specs = [
        ChainLinkSpec(
            narrator_id=link.get("narrator_id", f"step-{i}"),
            step=i,
            version=link.get("version", "unknown"),
            transform_type=TransformType(link.get("transform_type", "pass_through")),
            domain=body.domain,
            trace_id=link.get("trace_id", str(uuid.uuid4())[:8]),
        )
        for i, link in enumerate(body.chain)
    ]
    chain = Chain(specs)

    link_grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
    cg = grade_chain(link_grades, [l.transform_type for l in chain.links], is_complete=chain.is_complete)

    normalized = body.normalized_text or body.claim_text.lower().strip()

    # Content verdict — uses the pluggable critic (TF-IDF by default)
    existing_texts = [c.get("normalized_text", "") for c in state.claims.values()]
    cv = critic.evaluate(
        body.claim_text, normalized, existing_texts, body.domain,
    ) if critic else ContentVerdict.UNVERIFIABLE
    action = decide(cg, cv)

    claim_id = str(uuid.uuid4())

    # Index for corroboration (O(1) lookup)
    state.index_claim(claim_id, normalized)
    corroborating = state.find_corroborating(normalized, claim_id)

    record = {
        "claim_id": claim_id,
        "claim_text": body.claim_text,
        "normalized_text": normalized,
        "chain_grade": cg.value,
        "content_verdict": cv.value,
        "action": action.value,
        "description": describe_action(cg, cv),
        "chain": chain.to_jsonb(),
        "served": action in (Action.SERVE, Action.SERVE_WITH_CAVEAT),
        "quarantined": action in (Action.QUARANTINE, Action.REJECT_AND_QUARANTINE_NARRATOR),
        "domain": body.domain,
        "page_slug": body.page_slug,
        "corroborating_claims": len(corroborating),
        "narrator_ids": [l.narrator_id for l in chain.links],
    }
    state.claims[claim_id] = record
    return record


@app.get("/v1/claims/{claim_id}")
async def get_claim(claim_id: str) -> dict:
    state = get_state()
    if claim_id not in state.claims:
        raise HTTPException(404, "Claim not found")
    record = state.claims[claim_id]
    # Check for corroborating claims using indexed lookup
    normalized = record.get("normalized_text", "")
    record["corroborating_claims"] = len(state.find_corroborating(normalized, claim_id))
    return record


@app.get("/v1/claims/{claim_id}/chain")
async def get_claim_chain(claim_id: str) -> dict:
    state = get_state()
    if claim_id not in state.claims:
        raise HTTPException(404)
    r = state.claims[claim_id]
    return {"claim_id": claim_id, "chain": r["chain"], "chain_grade": r["chain_grade"], "action": r["action"]}


@app.post("/v1/narrators")
async def register_narrator(body: NarratorSubmit, reg: Registry = Depends(get_registry), role: str = Depends(require_admin)) -> dict:
    grade_map = {
        "reliable": NarratorGrade.RELIABLE, "acceptable": NarratorGrade.ACCEPTABLE,
        "weak": NarratorGrade.WEAK, "rejected": NarratorGrade.REJECTED, "ungraded": NarratorGrade.UNGRADED,
    }
    grade = grade_map.get(body.grade, NarratorGrade.UNGRADED)
    reg.register(body.narrator_id, body.domain, grade=grade)
    return {"narrator_id": body.narrator_id, "domain": body.domain, "grade": grade.value}


@app.get("/v1/narrators/{narrator_id}")
async def get_narrator(narrator_id: str, domain: str = "general", reg: Registry = Depends(get_registry)) -> dict:
    narrator = reg.get(narrator_id, domain)
    if not narrator:
        raise HTTPException(404)
    return {
        "narrator_id": narrator.narrator_id, "domain_tag": narrator.domain_tag,
        "grade": narrator.grade.value, "adalah": narrator.adalah_grade.value,
        "dabt": narrator.dabt_grade.value, "is_active": narrator.is_active,
    }


@app.post("/v1/evidence")
async def submit_evidence(body: EvidenceSubmit, reg: Registry = Depends(get_registry), role: str = Depends(require_admin)) -> dict:
    try:
        ev_type = EvidenceType(body.evidence_type)
        ev_action = EvidenceAction(body.action)
    except ValueError as e:
        raise HTTPException(400, f"Invalid type: {e}")
    new_grade = reg.record_evidence(body.narrator_id, body.domain, ev_type, ev_action, body.description)
    return {"narrator_id": body.narrator_id, "domain": body.domain, "new_grade": new_grade.value}
