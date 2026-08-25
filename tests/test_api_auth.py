"""Auth fail-closed behavior (issue #93)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import isnad.api.auth as auth


def test_no_configured_keys_fails_closed() -> None:
    """With no ISNAD_API_KEYS, require_auth must reject with 503, not fall back
    to a hardcoded default credential."""
    original = auth._API_KEYS
    auth._API_KEYS = {}
    try:
        with pytest.raises(HTTPException) as exc:
            auth.require_auth("anything")
        assert exc.value.status_code == 503
    finally:
        auth._API_KEYS = original


def test_unknown_key_rejected_with_401() -> None:
    original = auth._API_KEYS
    auth._API_KEYS = {"known": "admin"}
    try:
        with pytest.raises(HTTPException) as exc:
            auth.require_auth("wrong")
        assert exc.value.status_code == 401
    finally:
        auth._API_KEYS = original


def test_known_key_resolves_role() -> None:
    original = auth._API_KEYS
    auth._API_KEYS = {"known": "admin"}
    try:
        assert auth.require_auth("known") == "admin"
    finally:
        auth._API_KEYS = original
