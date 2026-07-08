"""API dependency injection — per-request Registry, Critic, DB session."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from isnad.core.registry import BayesianTransitionPolicy, RegistryDB, ThresholdTransitionPolicy
from isnad.critics.embedding import EmbeddingCritic
from isnad.critics.nli import HybridCritic
from isnad.storage.sqlalchemy import get_session_factory
from isnad.types import NarratorGrade, TransitionPolicy

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
            seeds.append(
                (
                    e["narrator_id"],
                    e.get("domain", "general"),
                    grade_map.get(e.get("grade", "ungraded"), NarratorGrade.UNGRADED),
                )
            )
        logger.info(f"Loaded {len(seeds)} seed narrators from ISNAD_SEED_CONFIG")
        return seeds
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning(f"Invalid ISNAD_SEED_CONFIG: {exc}")
        return []


# ── Warm-start seeds ───────────────────────────────────────────
_WARM_START_SEEDS: list[tuple[str, str, NarratorGrade]] = [
    ("source:openstax", "physics", NarratorGrade.RELIABLE),
    ("source:crowell", "physics", NarratorGrade.RELIABLE),
    ("pdf-scraper@1.2", "physics", NarratorGrade.RELIABLE),
    ("openstax_v3", "physics", NarratorGrade.RELIABLE),
    ("wikisource", "physics", NarratorGrade.RELIABLE),
    ("pdf_scraper_a", "physics", NarratorGrade.ACCEPTABLE),
    ("pdf_scraper_b", "physics", NarratorGrade.ACCEPTABLE),
    ("ingest_model_a", "physics", NarratorGrade.ACCEPTABLE),
    ("ingest_model_b", "physics", NarratorGrade.ACCEPTABLE),
]
_WARM_START_SEEDS.extend(_parse_seed_config())


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
    try:
        critic = HybridCritic(
            embed_model="all-MiniLM-L6-v2",
            nli_model="cross-encoder/nli-deberta-v3-small",
            top_k=10,
        )
        emb = critic._load_embed_model()
        if emb is None:
            logger.info(
                "HybridCritic: sentence-transformers not installed; falling back to EmbeddingCritic"
            )
            return EmbeddingCritic()
        logger.info("Using HybridCritic (MiniLM -> NLI)")
        return critic
    except Exception:
        logger.info("HybridCritic unavailable; falling back to EmbeddingCritic (TF-IDF)")
        return EmbeddingCritic()


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
        for nid, dom, grade in _WARM_START_SEEDS:
            if reg.registry.get(nid, dom) is None:
                reg.registry.register(nid, dom, grade=grade)
        reg.flush()
        get_registry._seeded = True  # type: ignore[attr-defined]
    return reg


_shared_critic = _build_critic()


def get_critic():
    return _shared_critic
