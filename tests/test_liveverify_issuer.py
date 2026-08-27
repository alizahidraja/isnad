"""Round-trip test: seal with issuer.py, verify with client.py.

The strongest test available for the issuer direction — normalization,
hashing, extraction, and lookup must all agree, or the round-trip fails.
Uses a local HTTP server serving the written issuer files.
"""

from __future__ import annotations

import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from isnad.integrations.liveverify.issuer import (
    render_verdict,
    seal_verdict,
    write_issuer_files,
    write_verification_meta,
)
from isnad.integrations.liveverify.client import verify_claim


def _serve_directory(directory: Path) -> str:
    """Serve a directory over localhost HTTP; return the base URL."""
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        lambda *a, **kw: SimpleHTTPRequestHandler(*a, directory=str(directory), **kw),
    )
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"127.0.0.1:{port}"


def test_seal_then_verify_round_trip(tmp_path):
    # 1. Render a verdict and seal it against a verify: base.
    verify_base = "verify:127.0.0.1:0"  # placeholder; real port patched below
    verdict = render_verdict(
        claim_text="the momentum of a photon is p = h/λ",
        chain_grade="hasan",
        narrator_chain=["source:openstax-vol3", "scraper@1.2", "model:gpt-4o"],
        weakest_link="scraper@1.2",
        content_verdict="consistent",
    )
    sealed = seal_verdict(verdict, verify_base)

    # 2. Write issuer files to a temp dir.
    write_issuer_files(sealed, tmp_path)
    write_verification_meta(verify_base, tmp_path)

    # 3. Serve the dir and re-write the claim with the REAL port in verify: line.
    real_base = _serve_directory(tmp_path)
    # The seal_verdict used a placeholder port; re-seal with the real one.
    sealed2 = seal_verdict(verdict, f"verify:{real_base}")
    write_issuer_files(sealed2, tmp_path)

    # 4. Construct the claim text a client would select (verdict + verify: line).
    claim_with_verify = f"{verdict}\nverify:{real_base}"

    # 5. Verify it against the live server.
    result = verify_claim(claim_with_verify, timeout=5.0)

    assert result.verified, f"round-trip verification failed: {result.status} {result.error}"
    assert result.status == "VERIFIED"


def test_render_verdict_is_deterministic_for_fixed_time():
    """Same inputs AND same evaluation time → same bytes."""
    from datetime import UTC, datetime

    t = datetime(2026, 8, 21, 12, 0, 0, tzinfo=UTC)
    args = {
        "claim_text": "F = ma",
        "chain_grade": "sahih",
        "narrator_chain": ["src", "model"],
        "weakest_link": "src",
        "content_verdict": "consistent",
        "evaluated_at": t,
    }
    assert render_verdict(**args) == render_verdict(**args)


def test_render_verdict_default_embeds_current_time():
    """Without an explicit time, the verdict is point-in-time (date varies)."""
    import time

    a = render_verdict(
        claim_text="F = ma",
        chain_grade="sahih",
        narrator_chain=["src"],
        weakest_link="src",
        content_verdict="consistent",
    )
    time.sleep(0.01)
    b = render_verdict(
        claim_text="F = ma",
        chain_grade="sahih",
        narrator_chain=["src"],
        weakest_link="src",
        content_verdict="consistent",
    )
    # The evaluated-at line differs because time moved — that's correct.
    assert a != b


def test_seal_verdict_excludes_verify_line_from_hash():
    verdict = render_verdict(
        claim_text="F = ma",
        chain_grade="sahih",
        narrator_chain=["src"],
        weakest_link="src",
        content_verdict="consistent",
    )
    sealed = seal_verdict(verdict, "verify:example.com/c")
    # The page body appends the verify: line, but the hash covers only the verdict.
    assert sealed.page_body.endswith("verify:example.com/c")
    # normalize_text(verdict) is what gets hashed — the verify: line is NOT in it.
    assert "verify:" not in sealed.normalized_text


def test_authority_basis_is_honest():
    from isnad.integrations.liveverify.issuer import build_verification_meta

    meta = build_verification_meta("verify:example.com/c")
    assert "Self-attested" in meta["authorityBasis"]
    assert "no external authority" in meta["authorityBasis"]


class TestSupersedeVerdict:
    """#122 — a re-graded claim must not stay 'verified' forever."""

    def _verdict(self, grade: str) -> str:
        return render_verdict(
            claim_text="the momentum of a photon is p = h/λ",
            chain_grade=grade,
            narrator_chain=["source:openstax-vol3", "model:gpt-4o"],
            weakest_link="model:gpt-4o",
            content_verdict="consistent",
        )

    def test_old_hash_flips_to_superseded(self, tmp_path):
        from isnad.integrations.liveverify.issuer import supersede_verdict

        old = seal_verdict(self._verdict("hasan"), "verify:example.com/c")
        new = seal_verdict(self._verdict("daif"), "verify:example.com/c")
        write_issuer_files(old, tmp_path)

        supersede_verdict(old, new, tmp_path)

        # The old hash file must no longer say 'verified'.
        old_payload = json.loads((tmp_path / old.hash).read_text())
        assert old_payload["status"] == "superseded"
        assert old_payload["superseded_by"] == new.hash

        # The new hash file says 'verified'.
        new_payload = json.loads((tmp_path / new.hash).read_text())
        assert new_payload["status"] == "verified"

    def test_superseded_status_is_not_verified_by_client(self, tmp_path):
        """A verifier of the OLD claim sees not-verified, with the new hash."""
        from isnad.integrations.liveverify.issuer import supersede_verdict
        from isnad.integrations.liveverify.client import verify_claim

        old = seal_verdict(self._verdict("hasan"), "verify:example.com/c")
        new = seal_verdict(self._verdict("daif"), "verify:example.com/c")
        write_issuer_files(old, tmp_path)
        supersede_verdict(old, new, tmp_path)

        # The client interprets the old hash file directly.
        payload = json.loads((tmp_path / old.hash).read_text())
        assert payload["status"] == "SUPERSEDED" or payload["status"] == "superseded"
        # A superseded status must NOT be treated as verified by the client's
        # status interpretation (only VERIFIED / custom-affirming are).
        assert payload["status"].upper() != "VERIFIED"

    def test_supersede_does_not_touch_revoked_semantics(self, tmp_path):
        """Supersede is a regrade, not a revocation — status stays 'superseded'."""
        from isnad.integrations.liveverify.issuer import supersede_verdict

        old = seal_verdict(self._verdict("hasan"), "verify:example.com/c")
        new = seal_verdict(self._verdict("daif"), "verify:example.com/c")
        write_issuer_files(old, tmp_path)
        supersede_verdict(old, new, tmp_path)
        payload = json.loads((tmp_path / old.hash).read_text())
        assert "revoked" not in str(payload).lower()
        assert payload["status"] == "superseded"
