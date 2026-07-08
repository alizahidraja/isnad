"""ISNAD API v3 — FastAPI service with SQLAlchemy persistence, Bayesian policy,
corroboration engine, and semantic NLI critic.

Wire-up from paper §8 feedback:
- BayesianTransitionPolicy as default (with ISNAD_POLICY env override)
- CorroborationEngine active on every claim submission
- SQLAlchemy-backed RegistryDB per request (no global singleton)
- HybridCritic (MiniLM → NLI) as default with TF-IDF fallback
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Generator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from isnad.chain import Chain, ChainLinkSpec
from isnad.corroboration_engine import CorroborationEngine
from isnad.critics.embedding import EmbeddingCritic
from isnad.critics.nli import HybridCritic
from isnad.db import get_session_factory, init_db
from isnad.grading import grade_chain
from isnad.grading_bayesian import BayesianTransitionPolicy
from isnad.matrix import decide, describe_action
from isnad.registry import RegistryDB, ThresholdTransitionPolicy
from isnad.types import (
    Action,
    ChainGrade,
    ContentVerdict,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    TransformType,
    TransitionPolicy,
)

logger = logging.getLogger("isnad.api")

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


# ── Policy selection via env var ─────────────────────────────────


def _build_policy() -> TransitionPolicy:
    """Build TransitionPolicy from ISNAD_POLICY env var.

    ISNAD_POLICY=bayesian  → BayesianTransitionPolicy (default)
    ISNAD_POLICY=threshold → ThresholdTransitionPolicy
    """
    policy_name = os.environ.get("ISNAD_POLICY", "bayesian").lower()
    if policy_name == "threshold":
        logger.info("Using ThresholdTransitionPolicy")
        return ThresholdTransitionPolicy()
    else:
        logger.info("Using BayesianTransitionPolicy")
        return BayesianTransitionPolicy()


# ── Critic selection with graceful fallback ──────────────────────


def _build_critic():
    """Build content critic with graceful fallback.

    Tries HybridCritic (MiniLM → NLI) first.
    Falls back to EmbeddingCritic (TF-IDF) if sentence-transformers
    or the NLI model is not available.
    """
    try:
        critic = HybridCritic(
            embed_model="all-MiniLM-L6-v2",
            nli_model="cross-encoder/nli-deberta-v3-small",
            top_k=10,
        )
        # Probe: try loading the embed model to detect if deps are installed
        emb = critic._load_embed_model()
        if emb is None:
            logger.info(
                "HybridCritic: sentence-transformers not installed; "
                "falling back to EmbeddingCritic (TF-IDF)"
            )
            return EmbeddingCritic()
        logger.info("Using HybridCritic (MiniLM → NLI)")
        return critic
    except Exception:
        logger.info(
            "HybridCritic unavailable; falling back to EmbeddingCritic (TF-IDF)"
        )
        return EmbeddingCritic()


# ── Dependency Injection ─────────────────────────────────────────

# Warm-start seeds (reliable sources from §8 experiment)
_WARM_START_SEEDS: list[tuple[str, str, NarratorGrade]] = [
    ("source:openstax", "physics", NarratorGrade.RELIABLE),
    ("source:crowell", "physics", NarratorGrade.RELIABLE),
    ("pdf-scraper@1.2", "physics", NarratorGrade.RELIABLE),
]


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: per-request SQLAlchemy session."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_registry(session: Session = Depends(get_db)) -> RegistryDB:
    """Per-request RegistryDB backed by SQLAlchemy.

    Loads from the database on first call per session and seeds
    warm-start narrators if they don't exist yet.
    """
    policy = _build_policy()
    reg = RegistryDB(session=session, transition_policy=policy)
    reg.load()
    # Seed warm-start narrators on first access
    for nid, dom, grade in _WARM_START_SEEDS:
        if reg.registry.get(nid, dom) is None:
            reg.registry.register(nid, dom, grade=grade)
    return reg


# Shared critic (init once, thread-safe reads)
_shared_critic = _build_critic()


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
    # Initialize database tables on startup
    try:
        init_db()
        logger.info("Database tables initialized")
    except Exception as exc:
        logger.warning(f"DB init skipped (non-fatal): {exc}")
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
    reg: RegistryDB = Depends(get_registry),
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

    link_narrator_ids = [l.narrator_id for l in chain.links]
    link_grades = [reg.registry.get_grade(l.narrator_id, l.domain) for l in chain.links]
    cg = grade_chain(
        link_grades, [l.transform_type for l in chain.links],
        is_complete=chain.is_complete,
    )

    normalized = body.normalized_text or body.claim_text.lower().strip()

    # ── Corroboration Engine (Step 2) ──────────────────────────
    # Collect all claims in the app state as corroboration candidates
    all_claim_records = list(state.claims.values())
    # Build chain dicts for the corroboration engine
    all_chain_dicts: list[dict] = []
    for rec in all_claim_records:
        all_chain_dicts.append({
            "claim_text": rec.get("normalized_text", ""),
            "chain_grade": rec.get("chain_grade", "daif"),
            "narrator_ids": rec.get("narrator_ids", []),
            "source": rec.get("page_slug", ""),
        })

    # Narrator metadata for correlation detection
    narrator_metadata: dict[str, dict] = {}
    for nid in link_narrator_ids:
        narrator_metadata[nid] = reg.registry.get_metadata(nid, body.domain)

    corroboration_engine = CorroborationEngine()
    corr_result = corroboration_engine.evaluate(
        claim_text=normalized,
        base_chain_grade=cg,
        base_narrators=link_narrator_ids,
        all_chains=all_chain_dicts,
        narrator_metadata=narrator_metadata,
    )

    # Use upgraded grade if corroboration fired
    effective_grade: ChainGrade = corr_result.upgraded_grade if corr_result.upgraded else cg

    # ── Content verdict — pluggable critic (HybridCritic / TF-IDF fallback) ──
    existing_texts = [c.get("normalized_text", "") for c in state.claims.values()]
    cv = critic.evaluate(
        body.claim_text, normalized, existing_texts, body.domain,
    ) if critic else ContentVerdict.UNVERIFIABLE
    action = decide(effective_grade, cv)

    claim_id = str(uuid.uuid4())

    # Index for corroboration (O(1) lookup)
    state.index_claim(claim_id, normalized)
    corroborating = state.find_corroborating(normalized, claim_id)

    record = {
        "claim_id": claim_id,
        "claim_text": body.claim_text,
        "normalized_text": normalized,
        "chain_grade": effective_grade.value,
        "content_verdict": cv.value,
        "action": action.value,
        "description": describe_action(effective_grade, cv),
        "chain": chain.to_jsonb(),
        "served": action in (Action.SERVE, Action.SERVE_WITH_CAVEAT),
        "quarantined": action in (Action.QUARANTINE, Action.REJECT_AND_QUARANTINE_NARRATOR),
        "domain": body.domain,
        "page_slug": body.page_slug,
        "corroborating_claims": len(corroborating),
        "narrator_ids": link_narrator_ids,
        "corroboration_result": {
            "upgraded": corr_result.upgraded,
            "base_grade": cg.value,
            "upgraded_grade": corr_result.upgraded_grade.value,
            "corroborating_chains": corr_result.corroborating_chains,
            "independent_chains": corr_result.independent_chains,
            "effective_weight": corr_result.effective_weight,
            "reason": corr_result.reason,
        },
    }
    state.claims[claim_id] = record

    # Persist to database
    try:
        from isnad.chain import store_claim
        store_claim(
            session=reg.session,
            claim_text=body.claim_text,
            page_slug=body.page_slug,
            chain=chain,
            chain_grade=effective_grade.value,
        )
    except Exception as exc:
        logger.warning(f"Failed to persist claim to DB: {exc}")

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
async def register_narrator(body: NarratorSubmit, reg: RegistryDB = Depends(get_registry), role: str = Depends(require_admin)) -> dict:
    grade_map = {
        "reliable": NarratorGrade.RELIABLE, "acceptable": NarratorGrade.ACCEPTABLE,
        "weak": NarratorGrade.WEAK, "rejected": NarratorGrade.REJECTED, "ungraded": NarratorGrade.UNGRADED,
    }
    grade = grade_map.get(body.grade, NarratorGrade.UNGRADED)
    reg.registry.register(body.narrator_id, body.domain, grade=grade)
    reg.flush()
    return {"narrator_id": body.narrator_id, "domain": body.domain, "grade": grade.value}


@app.get("/v1/narrators/{narrator_id}")
async def get_narrator(narrator_id: str, domain: str = "general", reg: RegistryDB = Depends(get_registry)) -> dict:
    narrator = reg.registry.get(narrator_id, domain)
    if not narrator:
        raise HTTPException(404)
    return {
        "narrator_id": narrator.narrator_id, "domain_tag": narrator.domain_tag,
        "grade": narrator.grade.value, "adalah": narrator.adalah_grade.value,
        "dabt": narrator.dabt_grade.value, "is_active": narrator.is_active,
    }


@app.post("/v1/evidence")
async def submit_evidence(body: EvidenceSubmit, reg: RegistryDB = Depends(get_registry), role: str = Depends(require_admin)) -> dict:
    try:
        ev_type = EvidenceType(body.evidence_type)
        ev_action = EvidenceAction(body.action)
    except ValueError as e:
        raise HTTPException(400, f"Invalid type: {e}")
    new_grade = reg.registry.record_evidence(body.narrator_id, body.domain, ev_type, ev_action, body.description)
    reg.flush()
    return {"narrator_id": body.narrator_id, "domain": body.domain, "new_grade": new_grade.value}
