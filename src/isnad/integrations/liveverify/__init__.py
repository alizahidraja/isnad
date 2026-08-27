"""Live Verify integration for ISNAD.

Consume a Live Verify `verify:` seal (Paul Hammant's cryptographic
document-attestation protocol) as a high-trust narrator input to an ISNAD
chain.

Components:
- `normalize.py` — byte-compatible port of Live Verify's canonical text
  normalization, so hashes match every other client.
- `client.py`   — the protocol client: extract verify: URL → normalize →
  hash → GET → interpret status.
- `adapter.py`  — map a verification result onto ISNAD's two trust axes.

The strategic point (see Live Verify's own comparison-to-isnad.md): a
hash-verified, authority-chained source is an *ideal high-trust narrator* —
its ʿadālah (integrity) is anchored by cryptography, bootstrapping it to a
high grade on day one without waiting for an evidence history.

HONEST LIMIT: Live Verify proves authenticity (issuer-attested, unaltered),
NOT truth.  The adapter anchors integrity + origin, but leaves precision
(ḍabṭ) unassessed and leaves content (matn) to the content critic.
"""

from isnad.integrations.liveverify.adapter import (
    SealedSource,
    register_sealed_source,
    seal_to_narrator,
)
from isnad.integrations.liveverify.client import (
    AuthorityChain,
    AuthorityChainEntry,
    VerificationResult,
    verify_claim,
    walk_authority_chain,
)
from isnad.integrations.liveverify.issuer import (
    SealedVerdict,
    build_verification_meta,
    render_verdict,
    seal_verdict,
    supersede_verdict,
    write_issuer_files,
    write_verification_meta,
)
from isnad.integrations.liveverify.normalize import normalize_text, sha256_hex

__all__ = [
    "AuthorityChain",
    "AuthorityChainEntry",
    "SealedSource",
    "SealedVerdict",
    "VerificationResult",
    "build_verification_meta",
    "normalize_text",
    "register_sealed_source",
    "render_verdict",
    "seal_to_narrator",
    "seal_verdict",
    "sha256_hex",
    "supersede_verdict",
    "verify_claim",
    "walk_authority_chain",
    "write_issuer_files",
    "write_verification_meta",
]
