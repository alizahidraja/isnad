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


class MalformedLogError(ValueError):
    """A tamper-evidence log line could not be parsed into a valid entry (#108).

    Raised by the on-disk readers (``chainlog._read_chain``,
    ``merkle_log.read_batch_log``) when a non-blank line is invalid/truncated
    JSON, is missing a required key, or has the wrong shape. ``index`` is the
    0-based position among non-blank lines. Verifiers catch this and surface a
    structured break, so a corrupted or partially-written log reports "broken"
    and the CLI exits 1 rather than crashing with a traceback — which is the
    whole point of a tamper-evidence verifier: malformed input is exactly what
    it must survive, not die on.
    """

    def __init__(self, index: int, detail: str):
        self.index = index
        self.detail = detail
        super().__init__(f"malformed entry {index}: {detail}")


def canonical_json(obj: object) -> str:
    """Serialize an object to its RFC 8785-compatible canonical form."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    """Lowercase hex SHA-256 of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_hash(obj: object) -> str:
    """SHA-256 over the canonical JSON of ``obj`` (the audit record hash)."""
    return sha256_hex(canonical_json(obj))
