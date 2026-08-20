"""Live Verify → ISNAD narrator adapter.

The strategic heart of the integration.  Takes a Live Verify verification
result and maps it onto ISNAD's two trust axes, respecting the line that
makes both projects honest:

    AUTHENTICITY ≠ TRUTH.

Live Verify proves the issuer stands behind this exact text, unaltered.
It does NOT prove the underlying claim is true.  So a verified seal anchors
the narrator's *integrity* (ʿadālah) and *origin strength* — but NOT its
*precision* (ḍabṭ) and NOT the *content* (matn).  Those still need evidence
and criticism respectively.

The mapping (from Paul Hammant's own comparison-to-isnad.md):

    "A Live Verify seal is an ideal high-trust narrator input to an Isnad
     chain. A cryptographically-anchored, authority-chained source is exactly
     the kind of link that deserves a top narrator grade. Its integrity axis
     (ʿadālah) is anchored by cryptography ... A Live Verify seal can thus
     bootstrap a narrator to a high grade on day one, before any evidence
     history exists."
"""

from __future__ import annotations

from dataclasses import dataclass

from isnad.core.registry import Registry
from isnad.integrations.liveverify.client import VerificationResult
from isnad.types import AdalahGrade, DabtGrade, NarratorGrade, NarratorType

# Status → ʿadālah (integrity) mapping.
# verified → HIGH (cryptographically anchored)
# revoked / suspended / punitive → COMPROMISED (issuer withdrew; holder failed)
# expired / superseded / administrative → ACCEPTABLE (still authentic, not current)
# not-found / network-error / anything else → UNASSESSED (cannot judge integrity)
_ADALAH_MAP = {
    "VERIFIED": AdalahGrade.HIGH,
    "REVOKED": AdalahGrade.COMPROMISED,
    "SUSPENDED": AdalahGrade.COMPROMISED,
    "EXPIRED": AdalahGrade.ACCEPTABLE,
    "SUPERSEDED": AdalahGrade.ACCEPTABLE,
    "LAPSED": AdalahGrade.ACCEPTABLE,
}

# Status → NarratorGrade (the composite ordinal used by chain grading).
# A verified seal bootstraps a SOURCE narrator to RELIABLE on day one —
# but only the *integrity* half.  ḍabṭ (precision) stays unassessed, so the
# narrator is not handed a top precision grade it hasn't earned.
_NARRATOR_GRADE_MAP = {
    "VERIFIED": NarratorGrade.RELIABLE,
    "REVOKED": NarratorGrade.REJECTED,
    "SUSPENDED": NarratorGrade.REJECTED,
    "EXPIRED": NarratorGrade.ACCEPTABLE,
    "SUPERSEDED": NarratorGrade.ACCEPTABLE,
    "LAPSED": NarratorGrade.ACCEPTABLE,
}


@dataclass
class SealedSource:
    """A Live Verify-sealed source, ready to register as an ISNAD narrator.

    `adalah` is anchored by cryptography; `dabt` is deliberately UNASSESSED.
    `origin_strength` reflects the seal, not the content.
    """

    narrator_id: str  # e.g. "verify:degrees.ed.ac.uk"
    grade: NarratorGrade
    adalah: AdalahGrade
    dabt: DabtGrade
    origin_strength: str  # "verified" | "revoked" | "unknown" ...
    domain: str
    verified: bool
    payload: dict | None = None


def seal_to_narrator(result: VerificationResult) -> SealedSource:
    """Map a Live Verify result onto an ISNAD narrator grade.

    The narrator_id is the authority domain, namespaced under `verify:` so
    a Live Verify source is distinguishable from a plain source.  The domain
    is the one the document named, never the hosting host.

    Honest limit: this anchors ʿadālah (integrity) and origin, but sets
    ḍabṭ (precision) to UNASSESSED.  A verified document is unaltered and
    issuer-attested; it can still be factually wrong.  The content critic
    still has to do its job.
    """
    domain = result.domain
    narrator_id = f"verify:{domain}" if domain else "verify:unknown"
    status = result.status.upper()

    grade = _NARRATOR_GRADE_MAP.get(status, NarratorGrade.UNGRADED)
    adalah = _ADALAH_MAP.get(status, AdalahGrade.UNASSESSED)

    origin_strength = "unknown"
    if result.verified:
        origin_strength = "verified"
    elif status in ("REVOKED", "SUSPENDED"):
        origin_strength = "compromised"
    elif status in ("EXPIRED", "SUPERSEDED", "LAPSED"):
        origin_strength = "attested"  # still issuer-attested, but not current

    return SealedSource(
        narrator_id=narrator_id,
        grade=grade,
        adalah=adalah,
        dabt=DabtGrade.UNASSESSED,  # integrity anchored, precision NOT
        origin_strength=origin_strength,
        domain=domain,
        verified=result.verified,
        payload=result.payload,
    )


def register_sealed_source(
    registry: Registry,
    result: VerificationResult,
    *,
    domain: str = "general",
) -> SealedSource:
    """Register a Live Verify-sealed source as a narrator and return it.

    Bootstraps the narrator to a high integrity grade on day one, before any
    evidence history — exactly the cold-start fix Paul's comparison doc
    describes.  Only the integrity half is seeded; precision stays unassessed.
    """
    sealed = seal_to_narrator(result)
    registry.register(
        sealed.narrator_id,
        domain,
        narrator_type=NarratorType.SOURCE,
        grade=sealed.grade,
        adalah=sealed.adalah,
        dabt=sealed.dabt,
        upstream_source=sealed.domain,
    )
    return sealed
