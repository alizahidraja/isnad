"""Tests for the issuer CLI (`python -m isnad.integrations.liveverify.issue`)."""

from __future__ import annotations

import json

import pytest

from isnad.integrations.liveverify.issue import _main


def _write_claim(tmp_path, **overrides) -> str:
    """Write a claim JSON file and return its path."""
    data = {
        "claim_text": "the momentum of a photon is p = h/λ",
        "chain_grade": "hasan",
        "narrator_chain": ["source:openstax-vol3", "scraper@1.2", "model:gpt-4o"],
        "weakest_link": "scraper@1.2",
        "content_verdict": "consistent",
        "verify_base": "verify:example.com/verify",
    }
    data.update(overrides)
    path = tmp_path / "claim.json"
    path.write_text(json.dumps(data))
    return str(path)


def test_issue_writes_files(tmp_path, capsys):
    out = tmp_path / "out"
    rc = _main(["--claim-file", _write_claim(tmp_path), "--out", str(out)])
    assert rc == 0

    captured = capsys.readouterr().out
    assert "Sealed verdict" in captured

    # Hash file, claim page, and meta all written.
    files = list(out.iterdir())
    names = {f.name for f in files}
    assert "verification-meta.json" in names
    # Exactly one hash file (no extension) + one .html page.
    hashes = [n for n in names if not n.endswith((".html", ".json"))]
    assert len(hashes) == 1
    html_pages = [n for n in names if n.endswith(".html")]
    assert len(html_pages) == 1

    # Hash file contains the verified status.
    hash_file = out / hashes[0]
    assert json.loads(hash_file.read_text()) == {"status": "verified"}

    # Claim page contains the verdict text and the verify: line.
    page = (out / html_pages[0]).read_text()
    assert "ISNAD Claim Verdict" in page
    assert "verify:example.com/verify" in page

    # Meta has the honest authorityBasis.
    meta = json.loads((out / "verification-meta.json").read_text())
    assert "Self-attested" in meta["authorityBasis"]


def test_issue_is_point_in_time_not_deterministic(tmp_path):
    """The CLI embeds the evaluation timestamp, so two runs differ (point-in-time).

    This is the intended behaviour: a verdict is a snapshot.  Determinism of
    the *rendering* (fixed inputs + fixed time) is tested in
    test_liveverify_issuer.py; here we pin that the CLI wires in the real
    clock.
    """
    import time

    claim = _write_claim(tmp_path)
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    _main(["--claim-file", claim, "--out", str(out1)])
    time.sleep(0.01)
    _main(["--claim-file", claim, "--out", str(out2)])
    h1 = [f.name for f in out1.iterdir() if not f.name.endswith((".html", ".json"))]
    h2 = [f.name for f in out2.iterdir() if not f.name.endswith((".html", ".json"))]
    assert h1 != h2  # different timestamps → different hashes


def test_issue_missing_claim_file_errors():
    with pytest.raises(FileNotFoundError):
        _main(["--claim-file", "/nonexistent/claim.json", "--out", "/tmp/x"])
