"""ISNAD as a Live Verify *issuer* — seal graded verdicts, not arbitrary text.

The inverse of `client.py`.  Instead of consuming a seal, this module produces
one: given a graded claim, render a canonical verdict statement, hash it, and
emit the publishable page + hash file a Live Verify client can check.

What gets sealed is an **ISNAD verdict** — the framework's own assessment of a
claim's transmission chain — NOT a claim of external truth.  The
`authorityBasis` therefore states, plainly, that this is self-attested:

    "ISNAD's own grading of a claim's transmission chain. Self-attested —
     no external authority endorses this assessment."

In Paul's client this renders **amber**, not green — and that is the correct
outcome.  A page never grades itself; ISNAD has no independent endorser, so a
green tick would be a lie.

Point-in-time: a verdict is a snapshot.  Grades drift as evidence accumulates.
The evaluation date is sealed into the text so staleness is visible.
Regrade lifecycle is implemented via ``supersede_verdict``: a re-graded claim
flips its old hash to ``{"status": "superseded", "superseded_by": ...}`` and
publishes the new one, so a published verdict never silently stays "verified"
after the underlying grade moved.

Stdlib only — reuses ``normalize_text`` and ``sha256_hex`` from the integration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from isnad import __version__
from isnad.integrations.liveverify.normalize import normalize_text, sha256_hex

# The honest authority basis — self-attested, no independent endorser.
_SELF_ATTESTED_BASIS = (
    "ISNAD's own grading of a claim's transmission chain. "
    "Self-attested — no external authority endorses this assessment."
)


@dataclass(frozen=True)
class SealedVerdict:
    """A sealed ISNAD verdict: the canonical text, its hash, and the artifacts."""

    verdict_text: str
    normalized_text: str
    hash: str
    page_body: str
    hash_file_json: str
    verify_line: str


def render_verdict(
    claim_text: str,
    chain_grade: str,
    narrator_chain: list[str],
    weakest_link: str,
    content_verdict: str,
    *,
    evaluated_at: datetime | None = None,
    isnad_version: str = __version__,
) -> str:
    """Render the canonical verdict statement as deterministic, fixed-order text.

    Same inputs → same bytes, always.  Field order is fixed; the date is
    ISO-8601 UTC; no locale-dependent formatting.  The `verify:` line is NOT
    part of this text — it is appended later by the caller (or page), because
    Live Verify excludes the `verify:` line from the hashed region.
    """
    evaluated_at = evaluated_at or datetime.now(UTC)
    date_str = evaluated_at.astimezone(UTC).isoformat()

    lines = [
        "ISNAD Claim Verdict",
        "=" * 40,
        f"Claim: {claim_text}",
        f"Chain grade: {chain_grade}",
        "Transmission chain:",
    ]
    lines.extend(f"  {n}" for n in narrator_chain)
    lines.append(f"Weakest link: {weakest_link}")
    lines.append(f"Content verdict: {content_verdict}")
    lines.append(f"Evaluated at: {date_str}")
    lines.append(f"ISNAD version: {isnad_version}")
    return "\n".join(lines)


def seal_verdict(
    verdict_text: str,
    verify_base: str,
    *,
    metadata: dict | None = None,
) -> SealedVerdict:
    """Normalize, hash, and package a verdict for publishing.

    Args:
        verdict_text: The canonical verdict from `render_verdict`.
        verify_base: The `verify:` base URL (no hash), e.g.
            `"verify:alizahidraja.com/verify"`.
        metadata: Optional document-specific normalization rules (mirrors
            verification-meta.json's charNormalization/ocrNormalizationRules).

    Returns a SealedVerdict holding the normalized text, SHA-256 hash, the
    publishable page body (verdict + `verify:` line), and the hash-file JSON.

    Point-in-time note: a verdict is a snapshot of one grading.  When a claim is
    re-graded (evidence changed, grade moved), call :func:`supersede_verdict` to
    flip the old hash to ``{"status": "superseded"}`` and publish the new one —
    otherwise the old hash stays "verified" forever and overstates its currency.
    """
    normalized = normalize_text(verdict_text, metadata)
    hash_ = sha256_hex(normalized)
    verify_line = f"verify:{verify_base.removeprefix('verify:').removeprefix('vfy:')}"
    page_body = f"{verdict_text}\n{verify_line}"
    hash_file_json = json.dumps({"status": "verified"}, indent=2) + "\n"
    return SealedVerdict(
        verdict_text=verdict_text,
        normalized_text=normalized,
        hash=hash_,
        page_body=page_body,
        hash_file_json=hash_file_json,
        verify_line=verify_line,
    )


def write_issuer_files(sealed: SealedVerdict, output_dir: str | Path) -> Path:
    """Write the hash file and the claim page into ``output_dir``.

    Layout (mirrors Live Verify's static-hosting convention):
        <output_dir>/<hash>          → `{"status": "verified"}`
        <output_dir>/<hash>.html     → the claim page (verdict + verify: line)

    Returns the output_dir Path.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / sealed.hash).write_text(sealed.hash_file_json)
    (out / f"{sealed.hash}.html").write_text(sealed.page_body)
    return out


def supersede_verdict(
    old_sealed: SealedVerdict,
    new_sealed: SealedVerdict,
    output_dir: str | Path,
) -> Path:
    """Publish a re-graded verdict and flip the old hash to ``superseded``.

    A verdict is point-in-time.  When a claim is re-graded (evidence changed,
    grade moved), the previously published hash must stop presenting as
    "verified" — otherwise it overstates its currency.  This function:

    1. rewrites ``<output_dir>/<old_hash>`` to
       ``{"status": "superseded", "superseded_by": "<new_hash>"}`` so any
       verifier of the old claim sees it is no longer current and can follow
       the link; and
    2. writes the new verdict's hash file and page (via :func:`write_issuer_files`).

    ``superseded`` is NOT ``revoked`` — revocation (a punitive integrity strike)
    is a distinct lifecycle the client maps to COMPROMISED; a regrade is a
    re-evaluation, which the client maps to ACCEPTABLE/attested.  Do not use
    this for revocation.

    Returns the output_dir Path.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    superseded_json = (
        json.dumps({"status": "superseded", "superseded_by": new_sealed.hash}, indent=2) + "\n"
    )
    (out / old_sealed.hash).write_text(superseded_json)
    # The old page remains (it is the historical record); only its hash file
    # flips status.  Publish the new one alongside.
    write_issuer_files(new_sealed, out)
    return out


def build_verification_meta(
    verify_base: str,
    *,
    issuer: str = "ISNAD",
    description: str = "Provenance grading for multi-agent AI claim pipelines",
) -> dict:
    """Generate an honest verification-meta.json for the issuer.

    `authorityBasis` states plainly that this is ISNAD's own self-attested
    assessment — no external authority endorses it.  This deliberately earns
    amber (not green) in any conforming client.
    """
    return {
        "issuer": issuer,
        "description": description,
        "claimType": "ISNADVerdict",
        "authorityBasis": _SELF_ATTESTED_BASIS,
    }


def write_verification_meta(verify_base: str, output_dir: str | Path) -> Path:
    """Write verification-meta.json into ``output_dir``."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "verification-meta.json").write_text(
        json.dumps(build_verification_meta(verify_base), indent=2) + "\n"
    )
    return out
