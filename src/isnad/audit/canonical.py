"""Canonical JSON serialization for integrity hashing.

RFC 8785 (JSON Canonicalization Scheme, JCS) specifies a deterministic JSON
serialization: object keys sorted lexicographically, no insignificant
whitespace, and minimal string escaping (only ``"``, ``\\``, and control
characters; non-ASCII is emitted as UTF-8).

ISNAD audit records contain only strings, integers, booleans, lists, and dicts
— never floats — so the JCS number-serialization rules (the only part of the
RFC that is genuinely fiddly) are trivially satisfied.  ``json.dumps`` with
``sort_keys``, the tightest separators, and ``ensure_ascii=False`` is therefore
byte-compatible with JCS for every object ISNAD emits.

This module is stdlib-only: ``hashlib`` + ``json``.
"""

from __future__ import annotations

import hashlib
import json


def canonical_json(obj: object) -> str:
    """Serialize an object to its RFC 8785-compatible canonical form."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    """Lowercase hex SHA-256 of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_hash(obj: object) -> str:
    """SHA-256 over the canonical JSON of ``obj`` (the audit record hash)."""
    return sha256_hex(canonical_json(obj))
