"""API authentication — API key validation (fail-closed).

There is NO default credential (issue #93). Operators must set
``ISNAD_API_KEYS`` (comma-separated ``name:role`` pairs, e.g.
``isnad-admin:admin,isnad-reader:reader``). When it is unset, authenticated
endpoints are rejected with 503 until keys are configured.
"""

from __future__ import annotations

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


_API_KEYS = _load_api_keys()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_auth(api_key: str | None = Security(api_key_header)) -> str:
    if not _API_KEYS:
        # Fail closed: no credentials configured → refuse to serve, rather than
        # shipping a hardcoded default password.
        raise HTTPException(503, "API keys not configured (set ISNAD_API_KEYS)")
    if not api_key or api_key not in _API_KEYS:
        raise HTTPException(401, "Invalid or missing API key")
    return _API_KEYS[api_key]


def require_admin(role: str = Depends(require_auth)) -> str:
    if role != "admin":
        raise HTTPException(403, "Admin role required")
    return role
