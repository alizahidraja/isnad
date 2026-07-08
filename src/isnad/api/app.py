"""API application factory — create_app() for FastAPI with dependency injection."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from isnad.api.endpoints.claims import router as claims_router
from isnad.api.endpoints.health import metrics_router
from isnad.api.endpoints.health import router as health_router
from isnad.api.endpoints.narrators import router as narrators_router
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
        version="2.0.0",
        lifespan=_lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    app.include_router(health_router)
    app.include_router(metrics_router)  # /metrics (Prometheus scrape target)
    app.include_router(claims_router)
    app.include_router(narrators_router)

    return app


# Module-level app instance for uvicorn
app = create_app()
