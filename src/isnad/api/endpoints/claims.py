"""API endpoints — claims submission, retrieval, listing, chain inspection."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, HTTPException, Query
from fastapi.routing import APIRouter

from isnad.api.auth import require_auth
from isnad.api.dependencies import _metrics_counters, get_critic, get_registry
from isnad.core.chain import Chain, ChainLinkSpec, store_claim
from isnad.core.corroboration import CorroborationEngine
from isnad.core.decision import decide, describe_action
from isnad.core.grading import grade_chain
from isnad.core.registry import RegistryDB
from isnad.types import ContentVerdict, TransformType

logger = logging.getLogger("isnad.api")
router = APIRouter(prefix="/v1", tags=["claims"])


@dataclass
class AppState:
    claims: dict[str, dict] = field(default_factory=dict)
    _corroboration_index: dict[str, list[str]] = field(default_factory=dict)

    def index_claim(self, claim_id: str, normalized_text: str) -> None:
        self._corroboration_index.setdefault(normalized_text, []).append(claim_id)

    def find_corroborating(self, normalized_text: str, exclude_id: str) -> list[str]:
        return [
            cid for cid in self._corroboration_index.get(normalized_text, []) if cid != exclude_id
        ]


_app_state = AppState()


def get_state() -> AppState:
    return _app_state


@router.get("/claims")
async def list_claims(
    domain: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    state = get_state()
    all_claims = list(state.claims.values())
    if domain:
        all_claims = [c for c in all_claims if c.get("domain") == domain]
    total = len(all_claims)
    page = all_claims[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "claims": [
            {
                "claim_id": c["claim_id"],
                "claim_text": c["claim_text"][:200],
                "chain_grade": c["chain_grade"],
                "action": c["action"],
                "domain": c.get("domain", "general"),
                "corroborating_claims": c.get("corroborating_claims", 0),
            }
            for c in page
        ],
    }


@router.post("/claims")
async def submit_claim(
    body: dict,
    reg: RegistryDB = Depends(get_registry),
    critic: Any = Depends(get_critic),
    _: str = Depends(require_auth),
) -> dict:
    state = get_state()
    chain_data = body.get("chain", [])
    domain = body.get("domain", "general")
    claim_text = body.get("claim_text", "")
    normalized = body.get("normalized_text") or claim_text.lower().strip()
    page_slug = body.get("page_slug", "default")

    specs = [
        ChainLinkSpec(
            narrator_id=link.get("narrator_id", f"step-{i}"),
            step=i,
            version=link.get("version", "unknown"),
            transform_type=TransformType(link.get("transform_type", "pass_through")),
            domain=domain,
            trace_id=link.get("trace_id", str(uuid.uuid4())[:8]),
        )
        for i, link in enumerate(chain_data)
    ]
    chain = Chain(specs)

    link_narrator_ids = [l.narrator_id for l in chain.links]
    link_grades = [reg.registry.get_grade(l.narrator_id, l.domain) for l in chain.links]
    cg = grade_chain(
        link_grades, [l.transform_type for l in chain.links], is_complete=chain.is_complete
    )

    # Corroboration
    all_claim_records = list(state.claims.values())
    all_chain_dicts: list[dict] = [
        {
            "claim_text": rec.get("normalized_text", ""),
            "chain_grade": rec.get("chain_grade", "daif"),
            "narrator_ids": rec.get("narrator_ids", []),
            "source": rec.get("page_slug", ""),
        }
        for rec in all_claim_records
    ]
    narrator_metadata = {nid: reg.registry.get_metadata(nid, domain) for nid in link_narrator_ids}

    corr_engine = CorroborationEngine()
    corr_result = corr_engine.evaluate(
        claim_text=normalized,
        base_chain_grade=cg,
        base_narrators=link_narrator_ids,
        all_chains=all_chain_dicts,
        narrator_metadata=narrator_metadata,
    )
    effective_grade = corr_result.upgraded_grade if corr_result.upgraded else cg
    if corr_result.upgraded:
        _metrics_counters["corroboration_fires_total"] += 1
    _metrics_counters["claims_submitted_total"] += 1

    # Content verdict
    existing_texts = [c.get("normalized_text", "") for c in state.claims.values()]
    cv = (
        critic.evaluate(claim_text, normalized, existing_texts, domain)
        if critic
        else ContentVerdict.UNVERIFIABLE
    )
    action = decide(effective_grade, cv)

    claim_id = str(uuid.uuid4())
    state.index_claim(claim_id, normalized)
    corroborating = state.find_corroborating(normalized, claim_id)

    record = {
        "claim_id": claim_id,
        "claim_text": claim_text,
        "normalized_text": normalized,
        "chain_grade": effective_grade.value,
        "content_verdict": cv.value,
        "action": action.value,
        "description": describe_action(effective_grade, cv),
        "chain": chain.to_jsonb(),
        "served": action.value in ("serve", "serve_with_caveat"),
        "quarantined": action.value in ("quarantine", "reject_and_quarantine_narrator"),
        "domain": domain,
        "page_slug": page_slug,
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

    try:
        store_claim(
            session=reg.session,
            claim_text=claim_text,
            page_slug=page_slug,
            chain=chain,
            chain_grade=effective_grade.value,
        )
    except Exception as exc:
        logger.warning(f"Failed to persist claim to DB: {exc}")

    return record


@router.get("/claims/{claim_id}")
async def get_claim(claim_id: str) -> dict:
    state = get_state()
    if claim_id not in state.claims:
        raise HTTPException(404, "Claim not found")
    record = dict(state.claims[claim_id])
    normalized = record.get("normalized_text", "")
    record["corroborating_claims"] = len(state.find_corroborating(normalized, claim_id))
    return record


@router.get("/claims/{claim_id}/chain")
async def get_claim_chain(claim_id: str) -> dict:
    state = get_state()
    if claim_id not in state.claims:
        raise HTTPException(404)
    r = state.claims[claim_id]
    return {
        "claim_id": claim_id,
        "chain": r["chain"],
        "chain_grade": r["chain_grade"],
        "action": r["action"],
    }
