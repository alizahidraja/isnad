"""Database session management for the Isnād–Rijāl framework.

Supports PostgreSQL (production) and SQLite (testing / pure-logic tests).
The SQLite fallback ensures grading/corroboration tests need no DB server.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from isnad.models import Base

DATABASE_URL = os.environ.get(
    "ISNAD_DATABASE_URL",
    "sqlite:///isnad.db",  # SQLite fallback for quickstart
)


def _get_db_url() -> str:
    """Re-read DATABASE_URL from env var (allows test overrides)."""
    return os.environ.get("ISNAD_DATABASE_URL", DATABASE_URL)


def create_engine_from_url(url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine from the given URL or env var."""
    db_url = url or _get_db_url()
    connect_args: dict[str, object] = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, echo=False, connect_args=connect_args)


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the global engine, creating it if needed."""
    global _engine
    if _engine is None:
        _engine = create_engine_from_url()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the global session factory, creating it if needed."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager yielding a SQLAlchemy session."""
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


def init_db(url: str | None = None) -> None:
    """Create all tables.  Use in tests / bootstrapping."""
    engine = create_engine_from_url(url) if url else get_engine()
    Base.metadata.create_all(engine)


def drop_db(url: str | None = None) -> None:
    """Drop all tables.  Use only in tests."""
    engine = create_engine_from_url(url) if url else get_engine()
    Base.metadata.drop_all(engine)


def reset_engine() -> None:
    """Reset global engine (useful in tests switching URLs)."""
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
