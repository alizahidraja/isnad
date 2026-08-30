"""API endpoints — claims submission, retrieval, listing, chain inspection."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, HTTPException, Query, Security
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from isnad.api.auth import _check_auth, api_key_header, require_auth
from isnad.api.dependencies import _metrics_counters, get_critic, get_fidelity_critic, get_registry
from isnad.core.chain import (
    Chain,
    ChainLinkSpec,
    adalah_grades_for_chain,
    grades_for_chain,
    resolved_narrator_ids_for_chain,
    store_claim,
)
from isnad.core.corroboration import CorroborationEngine
from isnad.core.decision import decide, describe_action, gate_serve, hold_unverifiable
from isnad.core.fidelity import compute_fidelity_verdicts
from isnad.core.grading import grade_chain
from isnad.core.identity import is_unknown_version, resolve_narrator_id
from isnad.core.registry import Registry, RegistryDB
from isnad.critics.embedding import TFIDFIndex
from isnad.models import ReviewQueue
from isnad.types import Action, ChainGrade, ContentVerdict, NarratorGrade, TransformType

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


class ChainLinkIn(BaseModel):
    """A single transmission-chain link in a claim-submission request."""

    narrator_id: str
    version: str = "unknown"
    transform_type: TransformType = TransformType.PASS_THROUGH
    trace_id: str = ""
    input_snapshot: str | None = None
    output_snapshot: str | None = None
    document_hashes: list[str] = Field(
        default_factory=list,
        description="Retrieved-document content hashes for the madār correlation check (#125)",
    )


class ClaimSubmitIn(BaseModel):
    """Validated claim-submission body (issue #93)."""

    claim_text: str = Field(min_length=1)
    domain: str = "general"
    page_slug: str = "default"
    normalized_text: str | None = None
    chain: list[ChainLinkIn] = Field(default_factory=list)
    # D1: optional operator-supplied KB corpus — the retrieved documents the
    # claim was grounded in. These are the actual evidence artifacts the
    # content critic checks against (vs prior claims, which are themselves
    # unverified assertions). An operator-supplied corpus is an ASSUMPTION
    # (a prior), not an observation — provenance is recorded, never hidden.
    corpus_docs: list[str] | None = Field(
        default=None,
        description="Optional operator-supplied KB documents the critic checks against",
    )


_app_state = AppState()


def get_state() -> AppState:
    return _app_state


def _serve_hold(domain: str) -> bool:
    """Whether a prior-only chain must downgrade serve to REVIEW (hard gate).

    Two knobs, both honest and operator-controlled:
    - ``ISNAD_SERVE_GATE=hold`` makes EVERY domain hold (strict mode).
    - ``ISNAD_SERVE_HOLD_DOMAINS=medical,legal`` holds only the named domains.

    Default is the soft gate (cap SERVE → SERVE_WITH_CAVEAT), which keeps a
    cold-start knowledge base useful while never plain-serving an unobserved
    narrator.
    """
    gate = os.environ.get("ISNAD_SERVE_GATE", "caveat").strip().lower()
    if gate == "hold":
        return True
    hold_domains = {
        d.strip().lower()
        for d in os.environ.get("ISNAD_SERVE_HOLD_DOMAINS", "").split(",")
        if d.strip()
    }
    return domain.lower() in hold_domains


def _hydrate_claims_from_db(session: Any) -> int:
    """Rebuild the in-memory claim index from the DB (issue #93 follow-up).

    The serving index (``_app_state.claims`` + the corroboration index) was
    previously memory-only, so a process restart silently dropped every claim
    even though each one had been persisted via ``store_claim``. This loads
    persisted claims back into memory so the read surface survives restarts.

    ``content_verdict`` and ``action`` are now persisted, so rehydration is
    FAITHFUL: a claim that was held (SAHIH × CONTRADICTION → REVIEW) stays
    held, instead of being silently upgraded to SERVE_WITH_CAVEAT by
    re-deriving from UNVERIFIABLE. Legacy rows without these columns fall back
    to the conservative re-derivation (never a serve).

    Returns the number of claims hydrated.
    """
    from isnad.core.decision import decide
    from isnad.models import RijalClaim

    rows = session.query(RijalClaim).order_by(RijalClaim.valid_from).all()
    hydrated = 0
    for row in rows:
        if row.claim_id in _app_state.claims:
            continue
        chain = row.narrator_chain or []
        narrator_ids = [link.get("narrator_id", "") for link in chain if isinstance(link, dict)]
        domain = "general"
        for link in chain:
            if isinstance(link, dict) and link.get("domain"):
                domain = link["domain"]
                break
        cg = row.chain_grade or "daif"
        # Faithful rehydration: use the persisted verdict/action when present;
        # otherwise (legacy rows) fall back to the conservative re-derivation
        # from (chain_grade, UNVERIFIABLE) — which never serves a SAHIH claim
        # with caveat, only routes it honestly.
        if row.content_verdict and row.action:
            cv_value = row.content_verdict
            action_value = row.action
        else:
            cv_value = ContentVerdict.UNVERIFIABLE.value
            action_value = decide(ChainGrade(cg), ContentVerdict.UNVERIFIABLE).value
        _app_state.claims[row.claim_id] = {
            "claim_id": row.claim_id,
            "claim_text": row.claim_text,
            "normalized_text": row.normalized_text,
            "chain_grade": cg,
            "content_verdict": cv_value,
            "action": action_value,
            "description": "rehydrated from DB",
            "chain": chain,
            "served": action_value in ("serve", "serve_with_caveat"),
            "quarantined": action_value in ("quarantine", "reject_and_quarantine_narrator"),
            "domain": domain,
            "page_slug": row.page_slug,
            "corroborating_claims": 0,
            "narrator_ids": narrator_ids,
            "resolved_narrator_ids": narrator_ids,
            "link_grades": [],
            "link_fidelity_verdicts": [],
            "version_drift_detected": False,
            "corroboration_result": None,
        }
        _app_state.index_claim(row.claim_id, row.normalized_text)
        hydrated += 1
    return hydrated


def _find_best_matching_claim_id(
    normalized: str, existing_texts: list[str], existing_claim_ids: list[str]
) -> str | None:
    """Locate the existing claim closest to `normalized`, for linking conflicts.

    Used only to populate ReviewQueue.conflicting_claim_ids when a
    CONTRADICTION verdict fires — deliberately independent of whichever
    ContentCritic produced that verdict (TF-IDF, NLI, or LLM-backed), so
    this doesn't touch the ContentCritic protocol at all. This is a locator,
    not a trust decision — the verdict itself still comes from the
    configured critic.
    """
    if not existing_texts:
        return None
    index = TFIDFIndex(existing_texts)
    claim_vec = index.tfidf_vector(normalized)
    vectors = [index.tfidf_vector(t) for t in existing_texts]
    best_sim = 0.0
    best_idx: int | None = None
    for i, vec in enumerate(vectors):
        sim = index.cosine_similarity(claim_vec, vec)
        if sim > best_sim:
            best_sim = sim
            best_idx = i
    if best_idx is None:
        return None
    return existing_claim_ids[best_idx]


def _extract_document_hashes(record: dict) -> list[str]:
    """Pull retrieved-document hashes from a stored claim record's chain.

    The chain is stored as JSONB (a list of link dicts, each with a
    ``document_hashes`` list after #125). Collect them all so a corroboration
    check can detect when two claims read the same document.
    """
    hashes: list[str] = []
    for link in record.get("chain", []) or []:
        for h in link.get("document_hashes", []) or []:
            if h:
                hashes.append(h)
    return hashes


def _version_drift_detected(registry: Registry, chain: Chain) -> bool:
    """True when a versioned link has no grade but a sibling alias/version does."""
    for link in chain.links:
        if is_unknown_version(link.version):
            continue
        resolved = resolve_narrator_id(link.narrator_id, link.version)
        if registry.get_grade(resolved, link.domain) != NarratorGrade.UNGRADED:
            continue
        if registry.get_grade(link.narrator_id, link.domain) != NarratorGrade.UNGRADED:
            return True
        if registry.has_graded_sibling_versions(link.narrator_id, link.domain, resolved):
            return True
    return False


@router.get("/claims")
async def list_claims(
    domain: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    served_only: bool = Query(default=True),
    api_key: str | None = Security(api_key_header),
) -> dict:
    if not served_only:
        # The audit view (served_only=false) exposes quarantined/rejected claim
        # text — that is containment metadata, not a public read surface, so it
        # is authenticated (security finding from the repo-health audit).
        _check_auth(api_key)
    state = get_state()
    all_claims = list(state.claims.values())
    if domain:
        all_claims = [c for c in all_claims if c.get("domain") == domain]
    if served_only:
        # Default: do not surface quarantined/rejected claims to a downstream
        # RAG — those are active containment, not a served surface. Pass
        # served_only=false to audit everything.
        all_claims = [c for c in all_claims if c.get("served", False)]
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
    body: ClaimSubmitIn,
    reg: RegistryDB = Depends(get_registry),
    critic: Any = Depends(get_critic),
    fidelity_critic: Any = Depends(get_fidelity_critic),
    _: str = Depends(require_auth),
) -> dict:
    state = get_state()
    chain_data = body.chain
    domain = body.domain
    claim_text = body.claim_text
    normalized = body.normalized_text or claim_text.lower().strip()
    page_slug = body.page_slug

    specs = [
        ChainLinkSpec(
            narrator_id=link.narrator_id,
            step=i,
            version=link.version,
            transform_type=link.transform_type,
            domain=domain,
            trace_id=link.trace_id or str(uuid.uuid4())[:8],
            input_snapshot=link.input_snapshot,
            output_snapshot=link.output_snapshot,
            document_hashes=link.document_hashes,
            # The moment ISNAD observed this chain — not a per-link
            # transmission clock (the client does not supply one). The DB
            # chain_links.timestamp records the same observed instant.
            timestamp=datetime.now(UTC).isoformat(),
        )
        for i, link in enumerate(chain_data)
    ]
    chain = Chain(specs)

    # Base chain's retrieved-document hashes (madār check against corroborators).
    base_document_hashes: set[str] = {h for link in chain.links for h in link.document_hashes if h}

    resolved_narrator_ids = resolved_narrator_ids_for_chain(chain)
    link_grades = grades_for_chain(reg.registry, chain)
    link_adalah_grades = adalah_grades_for_chain(reg.registry, chain)
    link_fidelity_verdicts = compute_fidelity_verdicts(chain, fidelity_critic)
    cg = grade_chain(
        link_grades,
        [l.transform_type for l in chain.links],
        is_complete=chain.is_complete,
        link_adalah_grades=link_adalah_grades,
        link_fidelity_verdicts=link_fidelity_verdicts,
    )

    # Content verdict — computed BEFORE corroboration (issue #11: corroboration
    # must be able to see a live contradiction before it decides to upgrade).
    existing_records = list(state.claims.values())
    existing_texts = [c.get("normalized_text", "") for c in existing_records]
    existing_claim_ids = [c.get("claim_id", "") for c in existing_records]
    # D1: the critic corpus is operator KB docs (when supplied) + prior claims.
    # Docs are the evidence artifacts the claim was grounded in; prior claims
    # are kept for contradiction-linking. Without docs, fall back to
    # claims-only (honest cold-start: everything UNVERIFIABLE).
    critic_corpus = list(body.corpus_docs or []) + existing_texts
    cv = (
        critic.evaluate(claim_text, normalized, critic_corpus, domain)
        if critic
        else ContentVerdict.UNVERIFIABLE
    )
    has_live_contradiction = cv == ContentVerdict.CONTRADICTION
    matched_claim_id = (
        _find_best_matching_claim_id(normalized, existing_texts, existing_claim_ids)
        if has_live_contradiction
        else None
    )

    # Corroboration
    all_claim_records = existing_records
    all_chain_dicts: list[dict] = [
        {
            "claim_text": rec.get("normalized_text", ""),
            "chain_grade": rec.get("chain_grade", "daif"),
            "narrator_ids": rec.get("resolved_narrator_ids", rec.get("narrator_ids", [])),
            "source": rec.get("page_slug", ""),
            "document_hashes": _extract_document_hashes(rec),
            # Each stored claim's content verdict, so the corroboration engine
            # can detect content-level madār (a corroborator repeating the same
            # error) — issue #54.
            "content_verdict": rec.get("content_verdict", "unverifiable"),
        }
        for rec in all_claim_records
    ]
    narrator_metadata = {
        nid: reg.registry.get_metadata(nid, domain) for nid in resolved_narrator_ids
    }

    corr_engine = CorroborationEngine()
    corr_result = corr_engine.evaluate(
        claim_text=normalized,
        base_chain_grade=cg,
        base_narrators=resolved_narrator_ids,
        all_chains=all_chain_dicts,
        narrator_metadata=narrator_metadata,
        has_live_contradiction=has_live_contradiction,
        base_document_hashes=base_document_hashes,
        base_content_verdict=cv,
    )
    effective_grade = corr_result.upgraded_grade if corr_result.upgraded else cg
    if corr_result.upgraded:
        _metrics_counters["corroboration_fires_total"] += 1
    _metrics_counters["claims_submitted_total"] += 1

    action = decide(effective_grade, cv)

    # P0-B: gate SERVE on prior-only provenance. A narrator graded from a
    # population prior alone (seeded RELIABLE with zero observed instances) must
    # not be served as if its transmission had been observed. The gate caps the
    # action (never the chain grade): soft default caps SERVE →
    # SERVE_WITH_CAVEAT; a high-stakes domain (hold) downgrades any serve to
    # REVIEW.
    prior_only_narrators = [
        nid
        for nid in resolved_narrator_ids
        if reg.registry.evidence_provenance(nid, domain).prior_only
    ]
    hold = _serve_hold(domain)
    action = gate_serve(action, prior_only_narrators, hold=hold)
    # D3: in hold mode, unverifiable content never caveat-serves — held.
    action = hold_unverifiable(action, cv, hold=hold)

    claim_id = str(uuid.uuid4())
    state.index_claim(claim_id, normalized)
    corroborating = state.find_corroborating(normalized, claim_id)

    description = describe_action(effective_grade, cv)
    if prior_only_narrators and action == Action.SERVE_WITH_CAVEAT:
        description = (
            f"{description} Prior-only source(s) {', '.join(prior_only_narrators)}: "
            "grade rests on an operator prior (seed), not observed in-pipeline "
            "transmission — verify before relying."
        )

    record = {
        "claim_id": claim_id,
        "claim_text": claim_text,
        "normalized_text": normalized,
        "chain_grade": effective_grade.value,
        "content_verdict": cv.value,
        "action": action.value,
        "description": description,
        "chain": chain.to_jsonb(),
        "served": action.value in ("serve", "serve_with_caveat"),
        "quarantined": action.value in ("quarantine", "reject_and_quarantine_narrator"),
        "domain": domain,
        "page_slug": page_slug,
        "critic_corpus_operator_docs": len(body.corpus_docs or []),
        "corroborating_claims": len(corroborating),
        "narrator_ids": [l.narrator_id for l in chain.links],
        "resolved_narrator_ids": resolved_narrator_ids,
        "prior_only_narrators": prior_only_narrators,
        "link_grades": [g.value for g in link_grades],
        "link_fidelity_verdicts": [v.value for v in link_fidelity_verdicts],
        "version_drift_detected": _version_drift_detected(reg.registry, chain),
        "corroboration_result": {
            "upgraded": corr_result.upgraded,
            "base_grade": cg.value,
            "upgraded_grade": corr_result.upgraded_grade.value,
            "corroborating_chains": corr_result.corroborating_chains,
            "independent_chains": corr_result.independent_chains,
            # Structural corroboration metrics (witness counts / discount
            # factors), NOT claim-truth confidence. No numeric confidence here.
            "effective_weight": corr_result.effective_weight,
            "reason": corr_result.reason,
            "shared_error_detected": corr_result.shared_error_detected,
            "shared_blind_spot_prior": corr_result.shared_blind_spot_prior,
            "effective_witnesses": corr_result.effective_witnesses,
            "chain_independence": [
                {
                    # D5: NOT a confidence score — a structural independence
                    # measure (0.0 = shared lineage, 1.0 = fully independent).
                    "independence": a.score,
                    "shared_signals": list(a.shared_signals),
                }
                for a in corr_result.chain_independence
            ],
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
            claim_id=claim_id,
            content_verdict=cv.value,
            action=action.value,
        )
    except Exception as exc:
        logger.error(f"Failed to persist claim to DB (audit trail will diverge): {exc}")

    # Route to human review — including a link to the specific claim this one
    # contradicts (issue #11: contradiction should surface both sides to a
    # reviewer, not just gate the new claim in isolation).
    if action in (
        Action.REVIEW,
        Action.QUARANTINE,
        Action.REJECT_AND_QUARANTINE_NARRATOR,
    ):
        try:
            reg.session.add(
                ReviewQueue(
                    claim_id=claim_id,
                    page_slug=page_slug,
                    claim_text=claim_text,
                    chain_grade=effective_grade.value,
                    content_verdict=cv.value,
                    matrix_action=action.value,
                    conflicting_claim_ids=[matched_claim_id] if matched_claim_id else [],
                    notes=describe_action(effective_grade, cv),
                )
            )
            reg.session.flush()
        except Exception as exc:
            logger.warning(f"Failed to enqueue claim for review: {exc}")

    # Active containment (P0-C): a REJECT_AND_QUARANTINE_NARRATOR or QUARANTINE
    # verdict must actually quarantine the offending narrators — set ʿadālah
    # COMPROMISED + is_active False — not merely set a flag on the record. A
    # flagged-but-not-quarantined narrator would keep serving.
    if action in (Action.REJECT_AND_QUARANTINE_NARRATOR, Action.QUARANTINE):
        for narrator_id in resolved_narrator_ids:
            try:
                reg.registry.quarantine(narrator_id, domain, reason="matrix action quarantined")
            except Exception as exc:
                logger.warning(f"Failed to quarantine narrator {narrator_id}: {exc}")
        # Persist the quarantine: quarantine() mutates the in-memory Narrator;
        # without flush() the COMPROMISED + is_active=False state is lost when
        # the request's session commits only the previously-loaded rows.
        try:
            reg.flush()
        except Exception as exc:
            logger.error(f"Failed to persist quarantine: {exc}")

    # Re-grade loop closure (P1): the jarḥ–taʿdīl loop was computed but never
    # applied — a contradiction never downgraded a narrator, corroboration
    # never renewed a grade. Close both:
    #   - a live contradiction is jarh evidence against the NEW claim's
    #     narrators (a factual disagreement questions their ḍabṭ/precision),
    #     routed through the TransitionPolicy toward a downgrade;
    #   - a corroboration upgrade is a freshness signal (independent chains
    #     still agree → the world has not changed on this narrator).
    applied_re_grade = False
    if has_live_contradiction and action != Action.REJECT_AND_QUARANTINE_NARRATOR:
        for narrator_id in resolved_narrator_ids:
            try:
                reg.registry.flag_contradiction(
                    narrator_id,
                    domain,
                    description="claim contradicted an existing chain",
                )
                applied_re_grade = True
            except Exception as exc:
                logger.warning(f"Failed to flag contradiction on {narrator_id}: {exc}")
    elif corr_result.upgraded:
        for narrator_id in resolved_narrator_ids:
            try:
                reg.registry.renew_grade(narrator_id, domain, reason="corroboration")
                applied_re_grade = True
            except Exception as exc:
                logger.warning(f"Failed to renew grade on {narrator_id}: {exc}")
    if applied_re_grade:
        try:
            reg.flush()
        except Exception as exc:
            logger.error(f"Failed to persist re-grade evidence: {exc}")

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
