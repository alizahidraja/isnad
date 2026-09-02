"""API dependency injection — per-request Registry, Critic, DB session."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Generator
from typing import Any

from fastapi import Depends
from sqlalchemy.orm import Session

from isnad.core.registry import (
    BayesianTransitionPolicy,
    RegistryDB,
    ThresholdTransitionPolicy,
    default_seed_entries,
)
from isnad.critics.nli import LocalNLICritic
from isnad.storage.sqlalchemy import get_session_factory
from isnad.types import NarratorGrade, NarratorType, TransitionPolicy

logger = logging.getLogger("isnad.api")

# ── Metrics counters ───────────────────────────────────────────
_metrics_counters: dict[str, int] = {
    "corroboration_fires_total": 0,
    "bayesian_grade_changes_total": 0,
    "claims_submitted_total": 0,
}


# ── Seed config parser ─────────────────────────────────────────
def _parse_seed_config() -> list[tuple[str, str, NarratorGrade]]:
    raw = os.environ.get("ISNAD_SEED_CONFIG", "")
    if not raw:
        return []
    try:
        entries = json.loads(raw)
        seeds: list[tuple[str, str, NarratorGrade]] = []
        grade_map = {
            "reliable": NarratorGrade.RELIABLE,
            "acceptable": NarratorGrade.ACCEPTABLE,
            "weak": NarratorGrade.WEAK,
            "rejected": NarratorGrade.REJECTED,
            "ungraded": NarratorGrade.UNGRADED,
        }
        for e in entries:
            seeds.append((
                e["narrator_id"],
                e.get("domain", "general"),
                grade_map.get(e.get("grade", "ungraded"), NarratorGrade.UNGRADED),
            ))
        logger.info(f"Loaded {len(seeds)} seed narrators from ISNAD_SEED_CONFIG")
        return seeds
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning(f"Invalid ISNAD_SEED_CONFIG: {exc}")
        return []


# ── Warm-start seeds ───────────────────────────────────────────
def _seed_warm_registry(reg: RegistryDB) -> None:
    """Warm the registry from evidence-sourced defaults + operator config.

    The shipped defaults (issues #203/#204) are Estimated priors (BOOTSTRAP_SEED),
    never observations, so ``gate_serve`` still caps them to SERVE_WITH_CAVEAT /
    REVIEW. Operator seeds from ISNAD_SEED_CONFIG are applied after defaults.
    """
    for entry in default_seed_entries():
        if reg.registry.get(entry.narrator_id, entry.domain) is None:
            reg.registry.seed(
                entry.narrator_id,
                entry.domain,
                NarratorGrade(entry.grade),
                narrator_type=NarratorType(entry.narrator_type),
                source=entry.source,
                metadata=dict(entry.metadata),
                model_family=entry.model_family,
                upstream_source=entry.upstream_source,
            )
    for nid, dom, grade in _parse_seed_config():
        if reg.registry.get(nid, dom) is None:
            reg.registry.seed(nid, dom, grade, source="operator-config")


# ── Policy builder ─────────────────────────────────────────────
def _build_policy() -> TransitionPolicy:
    policy_name = os.environ.get("ISNAD_POLICY", "bayesian").lower()
    if policy_name == "threshold":
        logger.info("Using ThresholdTransitionPolicy")
        return ThresholdTransitionPolicy()
    logger.info("Using BayesianTransitionPolicy")
    return BayesianTransitionPolicy()


# ── Critic builder ─────────────────────────────────────────────
def _build_critic():
    """Build the serving critic: LLM if a key/local server is present, else NLI, else TF-IDF."""
    from isnad.critics import best_available_critic

    critic = best_available_critic()
    logger.info(f"Serving critic: {type(critic).__name__}")
    return critic


# ── FastAPI dependencies ───────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
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
    policy = _build_policy()
    reg = RegistryDB(session=session, transition_policy=policy)
    reg.load()
    if not getattr(get_registry, "_seeded", False):
        _seed_warm_registry(reg)
        reg.flush()
        get_registry._seeded = True  # type: ignore[attr-defined]
    return reg


_shared_critic: Any = None
_critic_built = False


def get_critic():
    """Return the (lazily built, cached) content critic.

    Built on first request rather than at import time so importing the API
    never eagerly imports sentence-transformers/torch (which dominates test
    collection time).
    """
    global _shared_critic, _critic_built
    if not _critic_built:
        _shared_critic = _build_critic()
        _critic_built = True
    return _shared_critic


def _build_fidelity_critic():
    """Build the critic used for per-link transformation-fidelity checks.

    Deliberately does NOT fall back to EmbeddingCritic: fidelity checking
    needs a directional entailment/contradiction judgment (does this link's
    output follow from its own input), which a symmetric-similarity critic
    like TF-IDF cannot meaningfully provide. Returns None when no NLI-capable
    critic is available — core/fidelity.py treats that as "skip, no
    penalty," matching the framework's existing "no data → no penalty"
    pattern.
    """
    try:
        critic = LocalNLICritic()
        if critic._load_model() is None:
            logger.info(
                "LocalNLICritic: sentence-transformers not installed; "
                "fidelity checking disabled (all links UNVERIFIABLE)"
            )
            return None
        logger.info("Using LocalNLICritic for transformation-fidelity checks")
        return critic
    except Exception:
        logger.info("LocalNLICritic unavailable; fidelity checking disabled")
        return None


_shared_fidelity_critic: Any = None
_fidelity_built = False


def get_fidelity_critic():
    """Return the (lazily built, cached) transformation-fidelity critic.

    ``None`` means "no NLI-capable critic available" — fidelity checking is
    skipped (all links UNVERIFIABLE), not penalized.
    """
    global _shared_fidelity_critic, _fidelity_built
    if not _fidelity_built:
        _shared_fidelity_critic = _build_fidelity_critic()
        _fidelity_built = True
    return _shared_fidelity_critic
