"""Keyed claim-text commitment for erasure honesty (GDPR Art 17).

A plain SHA-256 of claim text is a *deduplication* identifier, not erasure:
low-entropy text (names, dates, small IDs) is invertible by brute force, which
is *pseudonymization* (GDPR Art 4(5)), not erasure (Art 17). A keyed
HMAC-SHA256 commitment is irreversible once the per-record secret is destroyed.

Use ``commit_claim_text`` when a deployment promises erasure: store only the
digest, keep the secret ephemeral (or per-record), and destroy it on erasure —
never persist the secret alongside the digest.
"""

from __future__ import annotations

import hashlib
import hmac


def commit_claim_text(claim_text: str, secret: str) -> str:
    """HMAC-SHA256 keyed commitment of claim text (hex digest).

    Irreversible once ``secret`` is destroyed and never stored. The returned
    digest is a *commitment*: without the secret it cannot be inverted to the
    original claim text (unlike a plain SHA-256 of low-entropy text).
    """
    return hmac.new(secret.encode("utf-8"), claim_text.encode("utf-8"), hashlib.sha256).hexdigest()
