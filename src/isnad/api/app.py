"""API application factory — create_app() for FastAPI with dependency injection."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from isnad import __version__
from isnad.api.endpoints.claims import router as claims_router
from isnad.api.endpoints.health import metrics_router
from isnad.api.endpoints.health import router as health_router
from isnad.api.endpoints.narrators import router as narrators_router
from isnad.api.endpoints.review import router as review_router
from isnad.storage.sqlalchemy import init_db

logger = logging.getLogger("isnad.api")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        init_db()
        logger.info("Database tables initialized")
    except Exception as exc:
        logger.warning(f"DB init skipped (non-fatal): {exc}")
    yield


def create_app() -> FastAPI:
    """Create and configure the ISNAD FastAPI application.

    Returns a fully configured app with all routers mounted.
    Override dependencies via app.dependency_overrides for testing.
    """
    app = FastAPI(
        title="ISNAD - Claim-Level Provenance API",
        version=__version__,
        lifespan=_lifespan,
    )
    # CORS is opt-in (issue #93): no wildcard by default. Set ISNAD_CORS_ORIGINS
    # to a comma-separated allowlist to enable cross-origin access.
    cors_origins = [
        o.strip() for o in os.environ.get("ISNAD_CORS_ORIGINS", "").split(",") if o.strip()
    ]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health_router)
    app.include_router(metrics_router)  # /metrics (Prometheus scrape target)
    app.include_router(claims_router)
    app.include_router(narrators_router)
    app.include_router(review_router)

    return app


# Module-level app instance for uvicorn
app = create_app()
