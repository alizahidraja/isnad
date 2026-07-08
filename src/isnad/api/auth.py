"""API authentication — API key validation."""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

_API_KEYS = {
    k: r for k, r in [
        kv.split(":") for kv in
        os.environ.get("ISNAD_API_KEYS", "isnad-admin:admin,isnad-reader:reader").split(",")
        if ":" in kv
    ]
} or {"isnad-admin": "admin"}

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_auth(api_key: str | None = Security(api_key_header)) -> str:
    if not api_key or api_key not in _API_KEYS:
        raise HTTPException(401, "Invalid or missing API key")
    return _API_KEYS[api_key]


def require_admin(role: str = Depends(require_auth)) -> str:
    if role != "admin":
        raise HTTPException(403, "Admin role required")
    return role
