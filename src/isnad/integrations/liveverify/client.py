"""Live Verify protocol client — normalize → hash → GET, in Python.

Implements the verification half of the Live Verify protocol so ISNAD can
consume a `verify:` seal as a narrator-grade input.  Mirrors the canonical
`app-logic.js` functions:

- extract_verification_url  — find the `verify:`/`vfy:` line in claim text
- build_verification_url    — verify: URL → https:// URL + hash
- build_meta_url            — verify: URL → https:// URL to verification-meta.json
- verify_hash               — GET the endpoint, interpret the status

The trust model is unchanged from Live Verify: the issuer's domain (DNS/TLS)
is the anchor.  This client is deliberately dependency-light — stdlib `urllib`
only, so it runs anywhere ISNAD runs.

Honest limit, stated up front: Live Verify proves *authenticity* (the issuer
stands behind this exact text, unaltered) — NOT *truth* of the underlying
claim.  This module returns the raw verification result; the mapping of that
result onto ISNAD's trust axes is the job of `adapter.py`, which respects the
authenticity ≠ truth distinction.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from isnad.integrations.liveverify.normalize import normalize_text, sha256_hex

_VERIFY_RE = re.compile(r"(^|\s)(verify|vfy)\s*:\s*", re.IGNORECASE)


@dataclass
class VerificationResult:
    """The outcome of a Live Verify lookup.

    `verified` is True only when the endpoint returned HTTP 200 with
    `{"status": "verified"}` (or an affirming custom status).  `status` is
    the raw status string.  `domain` is the authority domain from the
    verify: line — never the hosting host.  `payload` is the full JSON body
    when the endpoint returned JSON (may include `tx`, `allowedDomains`,
    etc.).

    Authority-chain fields (populated from verification-meta.json):

    - `authorized_by` — the issuer's ``authorizedBy`` value if declared,
      else None.  Presence means the issuer *claims* an independent endorser.
    - `authority_basis` — the issuer's one-line ``authorityBasis`` statement
      if declared, else None.  This is the issuer describing itself, not an
      endorsement.
    - `self_verified` — True when no independent ``authorizedBy`` endorser is
      present.  A self-verified seal proves tamper-evidence and origin, NOT
      integrity — the domain confirming the claim is the domain making it
      (Live Verify renders this amber, not green).

    NOTE: the authority chain is now *walked* (issuer → endorser(s) → root)
    via ``walk_authority_chain``; ``self_verified`` is True only when that walk
    fails to confirm a real authority.  A self-declared ``authorizedBy`` that
    does not resolve to an authority file is treated as self-verified (amber),
    never endorsed (green).
    """

    verified: bool
    status: str
    domain: str
    payload: dict | None = None
    error: str | None = None
    authorized_by: str | None = None
    authority_basis: str | None = None
    self_verified: bool = True
    authority_chain: AuthorityChain | None = None


@dataclass
class AuthorityChainEntry:
    """One level of the walked authority chain."""

    domain: str
    issuer: str | None
    role: str | None


@dataclass
class AuthorityChain:
    """The result of walking an issuer's ``authorizedBy`` up toward a root.

    ``confirmed`` is True only when the chain resolves to at least one real
    authority (``role`` is ``endorser`` or ``root-authority``).  An
    ``authorizedBy`` that does not resolve to an authority file — or that 404s
    — is a *self-attested* claim, not an endorsement.  This is the gap issue
    #37 closes: presence of ``authorizedBy`` is no longer treated as proof.
    """

    entries: list[AuthorityChainEntry]
    reached_root: bool
    confirmed: bool
    error: str | None = None


def walk_authority_chain(
    authorized_by: str | None,
    *,
    max_depth: int = 3,
    timeout: float = 10.0,
    fetch_meta=None,
) -> AuthorityChain:
    """Walk an issuer's ``authorizedBy`` up toward a sovereign root.

    Fetches each authority's ``verification-meta.json`` and checks its ``role``
    (``endorser`` or ``root-authority``).  Recurses on the endorser's own
    ``authorizedBy`` until a root is reached, the chain ends, or a failure is
    hit (bounded by ``max_depth`` and cycle detection).

    Honest semantics:
    - ``confirmed=True`` → the ``authorizedBy`` actually resolves to a real
      authority; the endorsement is not merely self-declared.
    - ``confirmed=False`` → the ``authorizedBy`` could not be confirmed (no
      ``authorizedBy``, non-authority target, or fetch failure) — treat as
      self-verified (amber), never green.
    """
    fetch_meta = fetch_meta or fetch_verification_meta
    entries: list[AuthorityChainEntry] = []
    if not authorized_by:
        return AuthorityChain(entries, reached_root=False, confirmed=False, error="no authorizedBy")
    current = authorized_by
    seen: set[str] = set()
    for _ in range(max_depth):
        if current in seen:
            # A cycle never reaches a sovereign root: two (or more) issuers
            # mutually endorsing each other with no root-authority is
            # self-referential, not independently confirmed. Treat it as
            # self-verified (amber), never green — otherwise an issuer
            # controlling two domains could manufacture an endorsement pair.
            return AuthorityChain(entries, reached_root=False, confirmed=False, error="cycle")
        seen.add(current)
        meta = fetch_meta(current, timeout=timeout)
        if meta is None:
            return AuthorityChain(
                entries, reached_root=False, confirmed=False, error=f"unreachable: {current}"
            )
        role = meta.get("role")
        if role not in ("endorser", "root-authority"):
            return AuthorityChain(
                entries, reached_root=False, confirmed=False, error=f"not an authority: {current}"
            )
        entries.append(AuthorityChainEntry(extract_domain(current), meta.get("issuer"), role))
        if role == "root-authority":
            return AuthorityChain(entries, reached_root=True, confirmed=True)
        current = meta.get("authorizedBy")
        if not current:
            return AuthorityChain(
                entries, reached_root=False, confirmed=True, error="endorser has no parent"
            )
    return AuthorityChain(entries, reached_root=False, confirmed=True, error="max depth reached")


# ---------------------------------------------------------------------------
# URL extraction (canonical app-logic.js logic)
# ---------------------------------------------------------------------------


def extract_verification_url(raw_text: str) -> tuple[str | None, int]:
    """Find the verify:/vfy: line, scanning bottom-to-top.

    Returns (base_url, line_index).  base_url is the normalized "verify:…"
    or "vfy:…" string (no scheme, no hash).  line_index is the 0-based line
    of the URL within raw_text, or -1 if not found.

    Mirrors `extractVerificationUrl()`: scans from the bottom, because
    OCR garbage tends to collect *below* the verify: line.
    """
    lines = [ln.strip() for ln in raw_text.split("\n")]
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if not line:
            continue
        match = _VERIFY_RE.search(line)
        if not match:
            continue
        url_part = line[match.end() :].strip()
        # Strip trailing garbage (anything after a space in the URL).
        space = url_part.find(" ")
        if space != -1:
            url_part = url_part[:space]
        if url_part:
            prefix = "vfy:" if match.group(2).lower() == "vfy" else "verify:"
            return prefix + url_part, i
    return None, -1


def extract_cert_text(raw_text: str, url_line_index: int) -> str:
    """Return the certification text (everything before the URL line).

    The verify:/vfy: line is NOT hashed.  Mirrors `extractCertText()`.
    """
    lines = [ln.strip() for ln in raw_text.split("\n")]
    cert_lines = lines[:url_line_index]
    while cert_lines and cert_lines[-1].strip() == "":
        cert_lines.pop()
    return "\n".join(cert_lines)


# ---------------------------------------------------------------------------
# URL building (canonical app-logic.js logic)
# ---------------------------------------------------------------------------


def _to_https(base_url: str) -> str:
    """Convert a verify:/vfy: base to a bare https:// URL (no hash)."""
    lower = base_url.lower()
    if lower.startswith("verify:"):
        without = base_url[7:]
    elif lower.startswith("vfy:"):
        without = base_url[4:]
    else:
        without = base_url
    protocol = "http" if ("localhost" in without or "127.0.0.1" in without) else "https"
    return f"{protocol}://{without}"


def build_verification_url(base_url: str, hash_: str, meta: dict | None = None) -> str:
    """Build the full HTTPS verification URL with the hash appended.

    Mirrors `buildVerificationUrl()`.  Respects `hashesHostedAt` and the
    hash-resource suffix from verification-meta.json.
    """
    suffix = ""
    if meta:
        suffix = meta.get("appendToHashResourceName") or meta.get("appendToHashFileName") or ""
    if meta and meta.get("hashesHostedAt"):
        hosted = str(meta["hashesHostedAt"]).rstrip("/")
        return f"{hosted}/{hash_}{suffix}"
    return f"{_to_https(base_url).rstrip('/')}/{hash_}{suffix}"


def build_meta_url(base_url: str) -> str:
    """Build the https:// URL of verification-meta.json for a base URL."""
    return f"{_to_https(base_url).rstrip('/')}/verification-meta.json"


def extract_domain(base_url: str) -> str:
    """Extract the authority domain from a verify:/vfy:/https:// base."""
    url_part = _to_https(base_url) if base_url.lower().startswith(("verify:", "vfy:")) else base_url
    url_part = url_part.split("://", 1)[-1]
    return url_part.split("/", 1)[0]


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def fetch_verification_meta(base_url: str, timeout: float = 10.0) -> dict | None:
    """Fetch verification-meta.json, returning None if absent/unreachable."""
    url = build_meta_url(base_url)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return None
    return None


def _authority_fields(metadata: dict | None) -> tuple[str | None, str | None]:
    """Extract the issuer's declared authority fields from verification-meta.json.

    Returns (authorized_by, authority_basis).  ``authorized_by`` is the
    issuer's *self-declared* endorser (or None) — it is NOT evidence of an
    endorsement; ``walk_authority_chain`` determines that.
    """
    if not metadata:
        return None, None
    return metadata.get("authorizedBy"), metadata.get("authorityBasis")


def verify_claim(
    raw_text: str,
    *,
    metadata: dict | None = None,
    timeout: float = 10.0,
    fetch_meta=None,
) -> VerificationResult:
    """Verify a claim's text against its issuer endpoint.

    Full pipeline, mirroring the canonical client:
      extract verify: URL → extract cert text → normalize → hash →
      GET the endpoint → interpret status.

    Args:
        raw_text: The claim text INCLUDING the verify:/vfy: line.
        metadata: Optional verification-meta.json (or None to auto-fetch).
        timeout: HTTP timeout in seconds.
        fetch_meta: Injectable meta-fetcher for the authority-chain walk
            (defaults to ``fetch_verification_meta``). Tests inject a stub here.

    Returns:
        A VerificationResult.  `verified` is the machine-readable verdict;
        ``self_verified`` is True only when the authority chain fails to
        confirm a real endorser.
    """
    base_url, url_index = extract_verification_url(raw_text)
    if base_url is None:
        return VerificationResult(
            verified=False, status="no-verify-line", domain="", error="no verify: line found"
        )

    cert_text = extract_cert_text(raw_text, url_index)
    if not cert_text.strip():
        return VerificationResult(
            verified=False,
            status="empty",
            domain=extract_domain(base_url),
            error="no claim text before verify: line",
        )

    domain = extract_domain(base_url)

    # Fetch meta if not supplied (for document-specific normalization).
    if metadata is None:
        metadata = fetch_verification_meta(base_url, timeout=timeout)

    # Authority chain (issue #37): a self-declared ``authorizedBy`` is NOT
    # endorsement — the chain must actually resolve to a real authority.
    authorized_by, authority_basis = _authority_fields(metadata)
    authority_chain = walk_authority_chain(authorized_by, timeout=timeout, fetch_meta=fetch_meta)
    self_verified = not authority_chain.confirmed

    normalized = normalize_text(cert_text, metadata)
    hash_ = sha256_hex(normalized)
    url = build_verification_url(base_url, hash_, metadata)

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8").strip()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return VerificationResult(
                verified=False,
                status="not-found",
                domain=domain,
                error=f"{domain} does not verify this claim (404)",
            )
        return VerificationResult(
            verified=False,
            status=f"http-{e.code}",
            domain=domain,
            error=f"HTTP {e.code}",
        )
    except (urllib.error.URLError, OSError) as e:
        return VerificationResult(
            verified=False,
            status="network-error",
            domain=domain,
            error=str(e),
        )

    # Interpret the body (mirrors verifyHash()).
    payload: dict | None = None
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            payload = parsed
    except json.JSONDecodeError:
        parsed = None

    if payload and "status" in payload:
        status = str(payload["status"]).upper()
        if status == "VERIFIED":
            return VerificationResult(
                verified=True,
                status=status,
                domain=domain,
                payload=payload,
                authorized_by=authorized_by,
                authority_basis=authority_basis,
                self_verified=self_verified,
                authority_chain=authority_chain,
            )
        # Custom affirming statuses from metadata responseTypes.
        if metadata and "responseTypes" in metadata:
            rt = metadata["responseTypes"].get(status)
            if rt and rt.get("class") == "affirming":
                return VerificationResult(
                    verified=True,
                    status=status,
                    domain=domain,
                    payload=payload,
                    authorized_by=authorized_by,
                    authority_basis=authority_basis,
                    self_verified=self_verified,
                    authority_chain=authority_chain,
                )
        return VerificationResult(
            verified=False,
            status=status,
            domain=domain,
            payload=payload,
            authorized_by=authorized_by,
            authority_basis=authority_basis,
            self_verified=self_verified,
            authority_chain=authority_chain,
        )

    # No JSON status — not verified.
    return VerificationResult(
        verified=False,
        status="no-status",
        domain=domain,
        error=body[:50] or "empty response",
    )
