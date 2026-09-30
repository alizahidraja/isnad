"""API authentication — API key validation (fail-closed).

There is NO default credential (issue #40). Configure keys via
``ISNAD_API_KEYS`` (comma-separated ``name:role`` pairs, e.g.
``isnad-admin:admin,isnad-reader:reader``). When it is unset, authenticated
endpoints are rejected with 503 until keys are configured.

Keys are reloaded from the environment on every request (no import-time freeze),
and compared in constant time.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader


def _load_api_keys() -> dict[str, str]:
    """Parse ISNAD_API_KEYS into {key: role}. Returns {} when unset (fail closed)."""
    raw = os.environ.get("ISNAD_API_KEYS", "")
    keys: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            key, role = entry.split(":", 1)
            if key:
                keys[key] = role
    return keys


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _check_auth(api_key: str | None) -> str:
    """Validate an API key and return its role. Raises 503/401 when closed.

    Keys are re-read from the environment each call, so rotating
    ``ISNAD_API_KEYS`` takes effect without a process restart. Comparison is
    constant-time to avoid timing side channels.
    """
    keys = _load_api_keys()
    if not keys:
        raise HTTPException(503, "API keys not configured (set ISNAD_API_KEYS)")
    if not api_key:
        raise HTTPException(401, "Invalid or missing API key")
    for candidate, role in keys.items():
        if hmac.compare_digest(api_key, candidate):
            return role
    raise HTTPException(401, "Invalid or missing API key")


def require_auth(api_key: str | None = Security(api_key_header)) -> str:
    return _check_auth(api_key)


def require_admin(role: str = Depends(require_auth)) -> str:
    if role != "admin":
        raise HTTPException(403, "Admin role required")
    return role
