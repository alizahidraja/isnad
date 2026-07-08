"""API endpoints — health check and Prometheus metrics."""

from __future__ import annotations

import time

from fastapi.routing import APIRouter

from isnad.api.dependencies import _metrics_counters
from isnad.api.endpoints.claims import get_state

router = APIRouter(prefix="/v1", tags=["health"])
metrics_router = APIRouter(tags=["observability"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.0.0"}


@router.get("/metrics")
async def metrics() -> dict:
    """JSON metrics — human-readable."""
    state = get_state()
    return {
        "claims_total": len(state.claims),
        "timestamp": time.time(),
        "corroboration_fires_total": _metrics_counters["corroboration_fires_total"],
        "bayesian_grade_changes_total": _metrics_counters["bayesian_grade_changes_total"],
        "claims_submitted_total": _metrics_counters["claims_submitted_total"],
    }


@metrics_router.get("/metrics")
async def metrics_prometheus() -> str:
    """Prometheus exposition format — scraped by prometheus."""
    state = get_state()
    return (
        f"# HELP isnad_claims_total Total claims in app state\n"
        f"# TYPE isnad_claims_total gauge\n"
        f"isnad_claims_total {len(state.claims)}\n"
        f"# HELP isnad_corroboration_fires_total Corroboration engine upgrade fires\n"
        f"# TYPE isnad_corroboration_fires_total counter\n"
        f"isnad_corroboration_fires_total {_metrics_counters['corroboration_fires_total']}\n"
        f"# HELP isnad_bayesian_grade_changes_total Bayesian policy grade transitions\n"
        f"# TYPE isnad_bayesian_grade_changes_total counter\n"
        f"isnad_bayesian_grade_changes_total {_metrics_counters['bayesian_grade_changes_total']}\n"
        f"# HELP isnad_claims_submitted_total Total claims submitted\n"
        f"# TYPE isnad_claims_submitted_total counter\n"
        f"isnad_claims_submitted_total {_metrics_counters['claims_submitted_total']}\n"
    )
