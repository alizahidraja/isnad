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
    """

    verified: bool
    status: str
    domain: str
    payload: dict | None = None
    error: str | None = None


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


def verify_claim(
    raw_text: str,
    *,
    metadata: dict | None = None,
    timeout: float = 10.0,
) -> VerificationResult:
    """Verify a claim's text against its issuer endpoint.

    Full pipeline, mirroring the canonical client:
      extract verify: URL → extract cert text → normalize → hash →
      GET the endpoint → interpret status.

    Args:
        raw_text: The claim text INCLUDING the verify:/vfy: line.
        metadata: Optional verification-meta.json (or None to auto-fetch).
        timeout: HTTP timeout in seconds.

    Returns:
        A VerificationResult.  `verified` is the machine-readable verdict.
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
            return VerificationResult(verified=True, status=status, domain=domain, payload=payload)
        # Custom affirming statuses from metadata responseTypes.
        if metadata and "responseTypes" in metadata:
            rt = metadata["responseTypes"].get(status)
            if rt and rt.get("class") == "affirming":
                return VerificationResult(
                    verified=True, status=status, domain=domain, payload=payload
                )
        return VerificationResult(verified=False, status=status, domain=domain, payload=payload)

    # No JSON status — not verified.
    return VerificationResult(
        verified=False,
        status="no-status",
        domain=domain,
        error=body[:50] or "empty response",
    )
