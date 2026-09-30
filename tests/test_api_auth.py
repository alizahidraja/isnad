"""Auth fail-closed behavior + constant-time comparison + lazy key reload."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import isnad.api.auth as auth


def test_no_configured_keys_fails_closed(monkeypatch) -> None:
    """With no ISNAD_API_KEYS, require_auth must reject with 503, not fall back
    to a hardcoded default credential."""
    monkeypatch.delenv("ISNAD_API_KEYS", raising=False)
    with pytest.raises(HTTPException) as exc:
        auth.require_auth("anything")
    assert exc.value.status_code == 503


def test_unknown_key_rejected_with_401(monkeypatch) -> None:
    monkeypatch.setenv("ISNAD_API_KEYS", "known:admin")
    with pytest.raises(HTTPException) as exc:
        auth.require_auth("wrong")
    assert exc.value.status_code == 401


def test_known_key_resolves_role(monkeypatch) -> None:
    monkeypatch.setenv("ISNAD_API_KEYS", "known:admin")
    assert auth.require_auth("known") == "admin"


def test_keys_reload_without_restart(monkeypatch) -> None:
    """Rotating ISNAD_API_KEYS takes effect on the next request (no import freeze)."""
    monkeypatch.setenv("ISNAD_API_KEYS", "old:admin")
    with pytest.raises(HTTPException) as exc:
        auth.require_auth("new")
    assert exc.value.status_code == 401
    monkeypatch.setenv("ISNAD_API_KEYS", "new:admin")
    assert auth.require_auth("new") == "admin"
