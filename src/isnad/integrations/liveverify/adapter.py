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


@dataclass
class SealedSource:
    """A Live Verify-sealed source, ready to register as an ISNAD narrator.

    `adalah` is anchored by cryptography only when the seal is independently
    endorsed; `dabt` is deliberately UNASSESSED.  `origin_strength` reflects
    the seal, not the content.
    """

    narrator_id: str  # e.g. "verify:degrees.ed.ac.uk"
    grade: NarratorGrade
    adalah: AdalahGrade
    dabt: DabtGrade
    origin_strength: str  # "verified-attested" | "self-attested" | "revoked" | ...
    domain: str
    verified: bool
    self_verified: bool
    authority_basis: str | None = None
    payload: dict | None = None


def seal_to_narrator(result: VerificationResult) -> SealedSource:
    """Map a Live Verify result onto an ISNAD narrator grade.

    The narrator_id is the authority domain, namespaced under `verify:` so
    a Live Verify source is distinguishable from a plain source.  The domain
    is the one the document named, never the hosting host.

    **Self-verification (tazkiyah).**  Classical rijāl is explicit that
    declaring a narrator reliable (tazkiyah) must come from an *independent*
    critic — self-testimony establishes nothing.  Live Verify encodes the same
    principle: a self-verified seal (no independent ``authorizedBy`` endorser)
    proves tamper-evidence and origin, but NOT integrity — the domain
    confirming the claim is the domain making it.  Live Verify renders it
    amber, not green.

    So the mapping splits:

    - ``VERIFIED`` **with** an independent endorser → ʿadālah HIGH,
      grade RELIABLE, origin ``verified-attested``.  Integrity IS seeded.
    - ``VERIFIED`` **self-verified** → ʿadālah UNASSESSED, grade UNGRADED,
      origin ``self-attested``.  Integrity is NOT seeded — a self-verified
      seal is a strong *origin* signal and nothing more.

    Honest limit: even an endorsed seal anchors ʿadālah and origin, but sets
    ḍabṭ (precision) to UNASSESSED and leaves content to the matn critic.
    A verified document can still be a genuine, domain-attested lie.
    """
    domain = result.domain
    narrator_id = f"verify:{domain}" if domain else "verify:unknown"
    status = result.status.upper()

    origin_strength = "unknown"

    # Verified with an independent endorser: integrity IS anchored.
    if result.verified and not result.self_verified:
        grade = NarratorGrade.RELIABLE
        adalah = AdalahGrade.HIGH
        origin_strength = "verified-attested"
    # Verified but self-verified: tamper-evidence + origin only.  No integrity.
    elif result.verified:
        grade = NarratorGrade.UNGRADED
        adalah = AdalahGrade.UNASSESSED
        origin_strength = "self-attested"
    # Revoked / suspended → COMPROMISED (issuer withdrew; punitive).
    elif status in ("REVOKED", "SUSPENDED"):
        grade = NarratorGrade.REJECTED
        adalah = AdalahGrade.COMPROMISED
        origin_strength = "compromised"
    # Expired / superseded / administrative → ACCEPTABLE (authentic, not current).
    elif status in ("EXPIRED", "SUPERSEDED", "LAPSED"):
        grade = NarratorGrade.ACCEPTABLE
        adalah = AdalahGrade.ACCEPTABLE
        origin_strength = "attested"
    # Everything else (not-found, network error, no status) → unassessed.
    else:
        grade = NarratorGrade.UNGRADED
        adalah = AdalahGrade.UNASSESSED

    return SealedSource(
        narrator_id=narrator_id,
        grade=grade,
        adalah=adalah,
        dabt=DabtGrade.UNASSESSED,  # integrity anchored, precision NOT
        origin_strength=origin_strength,
        domain=domain,
        verified=result.verified,
        self_verified=result.self_verified,
        authority_basis=result.authority_basis,
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
