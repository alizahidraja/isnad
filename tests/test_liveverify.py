"""Tests for the Live Verify integration.

Three layers, each proving a different thing:

1. Normalization byte-compatibility — the Python port must hash identically
   to the canonical JavaScript on Live Verify's own cross-platform fixtures.
   This is the critical interop contract: if it drifts, every verification
   fails.

2. Protocol client — URL extraction, verification-URL building, and status
   interpretation against a local mock issuer endpoint.

3. Adapter — mapping a verification result onto ISNAD's two trust axes
   (ʿadālah integrity vs. origin strength), respecting "authenticity ≠ truth".
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from isnad.integrations.liveverify.client import (
    build_meta_url,
    build_verification_url,
    extract_cert_text,
    extract_domain,
    extract_verification_url,
    verify_claim,
)
from isnad.integrations.liveverify.normalize import normalize_text, sha256_hex
from isnad.integrations.liveverify.adapter import (
    register_sealed_source,
    seal_to_narrator,
)
from isnad.integrations.liveverify.client import VerificationResult
from isnad.core.registry import Registry
from isnad.types import AdalahGrade, DabtGrade, NarratorGrade

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "liveverify"

TEXT_FIXTURES = [
    "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e.md",
    "30c6d7a77f52f4e31ff95a293722480eebd6059c8e6834c769a996b285a301a5.md",
    "50093137b7cced3cb846b6ae2ab53bda01a006f583351b90d38caf34362c0d69.md",
    "eb4108396033b081436f6e2ba05309696ed2ca2f211f7a726c9b9570412148ec.md",
    "ea98378016315477918bd65ff14a8e7027481648e621737bceae2f9f7c42500d.md",
    "1cddfbb2adfa13e4562d274b59e56b946f174a0feb566622dd67a4880cf0b223.md",
    "6725b845dcdf2490adf8d5f62e09e5f2055cb80c6200e5ccf58875c8190f4a80.md",
]


def _parse_markdown_fixture(path: Path) -> tuple[str, dict]:
    """Parse a fixture: (body_text, metadata). Mirrors the upstream harness."""
    raw = path.read_text()
    parts = raw.split("---")
    body = "---".join(parts[2:]).lstrip("\n").rstrip("\n")
    meta: dict = {}
    fm = parts[1] if len(parts) > 1 else ""
    m = re.search(r'charNormalization:\s*"([^"]*)"', fm)
    if m:
        meta["charNormalization"] = m.group(1)
    return body, meta


# ---------------------------------------------------------------------------
# 1. Normalization byte-compatibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", TEXT_FIXTURES)
def test_normalization_matches_canonical_fixtures(filename: str):
    """The Python port hashes identically to Live Verify's own fixtures."""
    body, meta = _parse_markdown_fixture(FIXTURES / filename)
    expected = filename.replace(".md", "")
    assert sha256_hex(normalize_text(body, meta)) == expected


@pytest.mark.parametrize("filename", TEXT_FIXTURES)
def test_python_port_matches_canonical_js(filename: str):
    """Cross-check: the Python port == the vendored canonical JS, run via node.

    Skips if node is unavailable (the fixture test above still guards the
    hashes; this one guards the JS↔Python equivalence directly).
    """
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    body, meta = _parse_markdown_fixture(FIXTURES / filename)
    js = (FIXTURES / "canonical-normalize.js").read_text()

    # Build a small node program that normalizes the body and prints the hash.
    import json as _json

    script = (
        js
        + "\n"
        + f"const body = {_json.dumps(body)};\n"
        + f"const meta = {_json.dumps(meta)};\n"
        + "console.log(sha256(normalizeText(body, meta)));\n"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    js_hash = result.stdout.strip()

    py_hash = sha256_hex(normalize_text(body, meta))
    assert py_hash == js_hash


# ---------------------------------------------------------------------------
# 2. Protocol client — URL logic (pure functions)
# ---------------------------------------------------------------------------


def test_extract_verification_url_scans_bottom_to_top():
    text = "Claim text\nverify:example.com/c\nOCR garbage below"
    base, idx = extract_verification_url(text)
    assert base == "verify:example.com/c"
    assert idx == 1


def test_extract_verification_url_accepts_vfy_and_spaces():
    assert extract_verification_url("x\nvfy: example.com/c ")[0] == "vfy:example.com/c"
    assert extract_verification_url("x\nverify : example.com/c")[0] == "verify:example.com/c"


def test_extract_verification_url_none_when_absent():
    base, idx = extract_verification_url("no verify line here")
    assert base is None
    assert idx == -1


def test_extract_cert_text_excludes_url_line():
    text = "Line one\nLine two\nverify:example.com/c"
    assert extract_cert_text(text, 2) == "Line one\nLine two"


def test_build_verification_url():
    assert (
        build_verification_url("verify:example.com/c", "abc123") == "https://example.com/c/abc123"
    )


def test_build_verification_url_respects_hash_suffix():
    meta = {"appendToHashResourceName": ".json"}
    assert (
        build_verification_url("verify:example.com/c", "abc123", meta)
        == "https://example.com/c/abc123.json"
    )


def test_build_verification_url_localhost_uses_http():
    assert (
        build_verification_url("verify:localhost:8000/c", "abc123")
        == "http://localhost:8000/c/abc123"
    )


def test_extract_domain():
    assert extract_domain("verify:example.com/c") == "example.com"
    assert extract_domain("verify:degrees.ed.ac.uk/c") == "degrees.ed.ac.uk"


def test_build_meta_url():
    assert build_meta_url("verify:example.com/c") == "https://example.com/c/verification-meta.json"


# ---------------------------------------------------------------------------
# 3. Protocol client — verification against a local mock issuer
# ---------------------------------------------------------------------------


class _MockIssuer(BaseHTTPRequestHandler):
    """A tiny issuer endpoint: serves verified / revoked / 404 by path."""

    def do_GET(self):
        if "/verified" in self.path:
            body = b'{"status": "verified"}'
            self.send_response(200)
        elif "/revoked" in self.path:
            body = b'{"status": "revoked"}'
            self.send_response(200)
        elif "/meta" in self.path:
            body = b'{"charNormalization": "\\u00e9\\u00e8\\u2192e"}'
            self.send_response(200)
        else:
            body = b"not found"
            self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # silence


@pytest.fixture()
def mock_issuer():
    server = HTTPServer(("127.0.0.1", 0), _MockIssuer)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"127.0.0.1:{port}"
    server.shutdown()


def _claim_with(base_url: str, text: str = "Some claim text") -> str:
    return f"{text}\n{base_url}"


def test_verify_claim_success(mock_issuer):
    base = f"verify:{mock_issuer}/verified"
    result = verify_claim(_claim_with(base))
    assert result.verified
    assert result.status == "VERIFIED"
    assert result.domain == mock_issuer


def test_verify_claim_revoked(mock_issuer):
    base = f"verify:{mock_issuer}/revoked"
    result = verify_claim(_claim_with(base))
    assert not result.verified
    assert result.status == "REVOKED"


def test_verify_claim_404(mock_issuer):
    base = f"verify:{mock_issuer}/nonexistent"
    result = verify_claim(_claim_with(base))
    assert not result.verified
    assert result.status == "not-found"


def test_verify_claim_no_verify_line():
    result = verify_claim("just some text, no verify line")
    assert not result.verified
    assert result.status == "no-verify-line"


def test_verify_claim_domain_comes_from_verify_line_not_host(mock_issuer):
    """The authority domain is the one the document names, never the host."""
    base = f"verify:{mock_issuer}/verified"
    result = verify_claim(_claim_with(base))
    # domain is the named authority, which in this test includes the port.
    assert result.domain == mock_issuer


# ---------------------------------------------------------------------------
# 4. Adapter — mapping verification onto ISNAD's two trust axes
# ---------------------------------------------------------------------------


def _verified_result(domain: str = "degrees.ed.ac.uk") -> VerificationResult:
    return VerificationResult(
        verified=True, status="VERIFIED", domain=domain, payload={"status": "verified"}
    )


def _endorsed_result(domain: str = "degrees.ed.ac.uk") -> VerificationResult:
    """A verified seal WITH an independent authorizedBy endorser."""
    return VerificationResult(
        verified=True,
        status="VERIFIED",
        domain=domain,
        payload={"status": "verified"},
        authorized_by="gov.uk/v1",
        authority_basis="Accredited by the UK Higher Education regulator",
        self_verified=False,
    )


class TestSealToNarrator:
    def test_endorsed_seal_bootstraps_reliable_with_high_integrity(self):
        """An INDEPENDENTLY-ENDORSED seal anchors integrity (tazkiyah satisfied)."""
        sealed = seal_to_narrator(_endorsed_result())
        assert sealed.grade == NarratorGrade.RELIABLE
        assert sealed.adalah == AdalahGrade.HIGH
        assert sealed.origin_strength == "verified-attested"
        assert sealed.self_verified is False

    def test_self_verified_seal_does_not_seed_integrity(self):
        """Self-verification proves tamper-evidence + origin, NOT integrity.

        The domain confirming the claim is the domain making it.  A
        self-verified seal must render UNASSESSED/UNGRADED — integrity is not
        seeded (classical tazkiyah requires an independent critic).
        """
        sealed = seal_to_narrator(_verified_result())
        assert sealed.self_verified is True
        assert sealed.adalah == AdalahGrade.UNASSESSED
        assert sealed.grade == NarratorGrade.UNGRADED
        assert sealed.origin_strength == "self-attested"

    def test_verified_seal_does_not_claim_precision(self):
        """Even an endorsed seal anchors integrity, NOT precision."""
        sealed = seal_to_narrator(_endorsed_result())
        assert sealed.dabt == DabtGrade.UNASSESSED

    def test_narrator_id_is_namespaced(self):
        sealed = seal_to_narrator(_endorsed_result("degrees.ed.ac.uk"))
        assert sealed.narrator_id == "verify:degrees.ed.ac.uk"

    def test_revoked_is_compromised(self):
        result = VerificationResult(verified=False, status="REVOKED", domain="x.com")
        sealed = seal_to_narrator(result)
        assert sealed.adalah == AdalahGrade.COMPROMISED
        assert sealed.grade == NarratorGrade.REJECTED
        assert sealed.origin_strength == "compromised"

    def test_expired_is_authentic_but_not_current(self):
        result = VerificationResult(verified=False, status="EXPIRED", domain="x.com")
        sealed = seal_to_narrator(result)
        assert sealed.adalah == AdalahGrade.ACCEPTABLE  # still authentic, just old
        assert sealed.origin_strength == "attested"

    def test_not_found_is_unassessed(self):
        result = VerificationResult(verified=False, status="not-found", domain="x.com")
        sealed = seal_to_narrator(result)
        assert sealed.adalah == AdalahGrade.UNASSESSED
        assert sealed.grade == NarratorGrade.UNGRADED


class TestRegisterSealedSource:
    def test_registers_and_lookupable(self):
        reg = Registry()
        sealed = register_sealed_source(reg, _endorsed_result(), domain="physics")
        narrator = reg.get(sealed.narrator_id, "physics")
        assert narrator is not None
        assert narrator.grade == NarratorGrade.RELIABLE
        assert narrator.adalah_grade == AdalahGrade.HIGH
        assert narrator.dabt_grade == DabtGrade.UNASSESSED

    def test_self_verified_registers_ungraded(self):
        """A self-verified seal registers UNGRADED/UNASSESSED — no integrity seed."""
        reg = Registry()
        sealed = register_sealed_source(reg, _verified_result(), domain="physics")
        narrator = reg.get(sealed.narrator_id, "physics")
        assert narrator is not None
        assert narrator.grade == NarratorGrade.UNGRADED
        assert narrator.adalah_grade == AdalahGrade.UNASSESSED

    def test_upstream_source_recorded_for_correlation_detection(self):
        reg = Registry()
        sealed = register_sealed_source(reg, _endorsed_result(), domain="physics")
        narrator = reg.get(sealed.narrator_id, "physics")
        assert narrator.upstream_source == "degrees.ed.ac.uk"


# ---------------------------------------------------------------------------
# Authority-chain fields (tazkiyah / self-verified) + remaining edge paths
# ---------------------------------------------------------------------------


class TestAuthorityFields:
    def test_no_metadata(self):
        from isnad.integrations.liveverify.client import _authority_fields

        assert _authority_fields(None) == (None, None)

    def test_extracts_authorized_by_and_basis(self):
        from isnad.integrations.liveverify.client import _authority_fields

        ab, basis = _authority_fields({"authorizedBy": "gov.uk/v1", "authorityBasis": "gov"})
        assert ab == "gov.uk/v1"
        assert basis == "gov"

    def test_no_authorized_by(self):
        from isnad.integrations.liveverify.client import _authority_fields

        ab, basis = _authority_fields({"authorityBasis": "self-described"})
        assert ab is None
        assert basis == "self-described"


class TestRemainingEdgePaths:
    def test_build_verification_url_hashes_hosted_at(self):
        from isnad.integrations.liveverify.client import build_verification_url

        url = build_verification_url(
            "verify:example.com/c", "abc123", {"hashesHostedAt": "https://host.example/"}
        )
        assert url == "https://host.example/abc123"

    def test_to_https_without_prefix(self):
        from isnad.integrations.liveverify.client import _to_https

        assert _to_https("example.com/c") == "https://example.com/c"

    def test_verify_claim_empty_cert_text(self):
        result = verify_claim("verify:example.com/c")
        assert not result.verified
        assert result.status == "empty"

    def test_verify_claim_network_error(self, monkeypatch):
        import urllib.error
        import urllib.request

        def _raise(*args, **kwargs):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", _raise)
        result = verify_claim("some claim\nverify:example.com/c")
        assert not result.verified
        assert result.status == "network-error"

    def test_verify_claim_custom_affirming_status(self, monkeypatch):
        import json
        import urllib.request

        meta = {"responseTypes": {"MATCH": {"class": "affirming"}}}

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"status": "match"}).encode()

        def _fake(*args, **kwargs):
            return _Resp()

        monkeypatch.setattr(urllib.request, "urlopen", _fake)
        result = verify_claim("some claim\nverify:example.com/c", metadata=meta)
        assert result.verified
        assert result.status == "MATCH"

    def test_verify_claim_non_json_body(self, monkeypatch):
        import urllib.request

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"<html>not json</html>"

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
        result = verify_claim("some claim\nverify:example.com/c")
        assert not result.verified
        assert result.status == "no-status"
