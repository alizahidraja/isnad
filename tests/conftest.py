"""Test environment setup.

Sets ISNAD_API_KEYS explicitly so API tests exercise the fail-closed auth path
against a known key set, rather than relying on the now-removed hardcoded
default credential (issue #93).
"""

from __future__ import annotations

import os

os.environ.setdefault("ISNAD_API_KEYS", "isnad-admin:admin,isnad-reader:reader")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _dispose_global_engine() -> None:
    """Close the global SQLAlchemy engine at session teardown.

    Without this, sqlite connections pooled in the module-level engine leak
    and pytest emits ~200 ``ResourceWarning: unclosed database`` messages.
    """
    yield
    from isnad.storage.sqlalchemy import reset_engine

    reset_engine()
