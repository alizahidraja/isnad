"""Serving-path audit trail tests (issue #241 + P0-c verifiability)."""

from __future__ import annotations

from isnad.api.endpoints.claims import _emit_audit_trail
from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.registry import Registry
from isnad.types import NarratorGrade, TransformType


def _chain_and_registry() -> tuple[Registry, Chain]:
    reg = Registry()
    reg.register("src", "physics", grade=NarratorGrade.RELIABLE)
    chain = Chain([
        ChainLinkSpec(
            narrator_id="src",
            step=0,
            version="1",
            transform_type=TransformType.PASS_THROUGH,
            domain="physics",
        )
    ])
    return reg, chain


def test_emit_audit_trail_produces_self_hash_and_persistable_payload():
    reg, chain = _chain_and_registry()
    h, sig, payload = _emit_audit_trail(
        chain=chain,
        link_grades=[NarratorGrade.RELIABLE],
        claim_id="c1",
        claim_text="p = mv",
        final_grade="sahih",
        registry=reg,
        domain="physics",
    )
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    assert sig is None  # no secret set -> unsigned
    # The payload must be the non-integrity canonical dict, and it must recompute
    # to the stored hash — this is what makes the serving-path record verifiable.
    from isnad.audit.canonical import canonical_hash

    assert isinstance(payload, dict)
    assert "integrity" not in payload
    assert canonical_hash(payload) == h


def test_emit_audit_trail_signs_and_appends_to_log(tmp_path, monkeypatch):
    reg, chain = _chain_and_registry()
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("ISNAD_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("ISNAD_AUDIT_LOG", str(log))

    h, sig, payload = _emit_audit_trail(
        chain=chain,
        link_grades=[NarratorGrade.RELIABLE],
        claim_id="c1",
        claim_text="p = mv",
        final_grade="sahih",
        registry=reg,
        domain="physics",
    )
    assert len(h) == 64
    assert sig is not None and len(sig) == 64
    assert log.exists()
    assert h in log.read_text()

    # Verify-on-read: the signature must verify over the persisted payload.
    from isnad.audit.canonical import canonical_json
    from isnad.audit.sign import hmac_verifier

    assert hmac_verifier("test-secret")(canonical_json(payload), sig)
