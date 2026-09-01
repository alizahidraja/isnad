"""Serving-path audit trail tests (issue #189)."""

from isnad.api.endpoints.claims import _emit_audit_trail
from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.registry import Registry
from isnad.types import NarratorGrade, TransformType


def _chain_and_registry() -> tuple[Registry, Chain]:
    reg = Registry()
    reg.register("src", "physics", grade=NarratorGrade.RELIABLE)
    chain = Chain(
        [
            ChainLinkSpec(
                narrator_id="src",
                step=0,
                version="1",
                transform_type=TransformType.PASS_THROUGH,
                domain="physics",
            )
        ]
    )
    return reg, chain


def test_emit_audit_trail_produces_self_hash():
    reg, chain = _chain_and_registry()
    h, sig = _emit_audit_trail(
        chain=chain,
        link_grades=[NarratorGrade.RELIABLE],
        claim_id="c1",
        claim_text="p = mv",
        final_grade="sahih",
        registry=reg,
        domain="physics",
    )
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    assert sig is None  # no HMAC secret configured -> self-hash only


def test_emit_audit_trail_signs_and_appends_to_log(tmp_path, monkeypatch):
    reg, chain = _chain_and_registry()
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("ISNAD_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("ISNAD_AUDIT_LOG", str(log))

    h, sig = _emit_audit_trail(
        chain=chain,
        link_grades=[NarratorGrade.RELIABLE],
        claim_id="c1",
        claim_text="p = mv",
        final_grade="sahih",
        registry=reg,
        domain="physics",
    )
    assert len(h) == 64
    assert sig is not None and len(sig) == 64  # HMAC-SHA256 hex
    assert log.exists()
    assert h in log.read_text()
