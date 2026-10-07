"""Tests for the isnad[tenuo] bridge: grade attestations + the constraint."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone, UTC

import pytest

from isnad.integrations.tenuo import (
    IsnadGradeConstraint,
    attest,
    ed25519_public_bytes,
    ed25519_public_key_from_bytes,
    ed25519_signing_key,
    mint_grade_attestation,
    verify_grade_attestation,
)

VALUE = "DE89 3704 0044 0532 0130 00"


@pytest.fixture()
def keys():
    signing = ed25519_signing_key()
    public = ed25519_public_key_from_bytes(ed25519_public_bytes(signing))
    return signing, public


def _mint(signing, value=VALUE, grade="sound", digest="trace:1", ttl=600):
    return mint_grade_attestation(value, grade, digest, ttl, signing)


def test_mint_verify_round_trip(keys):
    signing, public = keys
    att = _mint(signing)
    assert verify_grade_attestation(VALUE, att, public, min_grade="good")


def test_accepts_chain_grade_value_mapping(keys):
    signing, public = keys
    att = mint_grade_attestation(VALUE, "sahih", "trace:1", 600, signing)
    # "sahih" maps to "sound", which meets min_grade="good".
    assert verify_grade_attestation(VALUE, att, public, min_grade="good")


def test_tampered_attestation_fails(keys):
    signing, public = keys
    att = _mint(signing)
    data = json.loads(att)
    data["isnad_digest"] = "forged:1"
    forged = json.dumps(data, sort_keys=True, separators=(",", ":"))
    assert not verify_grade_attestation(VALUE, forged, public, min_grade="good")


def test_wrong_value_fails(keys):
    signing, public = keys
    att = _mint(signing, value=VALUE)
    assert not verify_grade_attestation("OTHER-IBAN", att, public, min_grade="good")


def test_expired_fails(keys):
    signing, public = keys
    att = _mint(signing, ttl=1)
    future = datetime.now(UTC) + timedelta(seconds=60)
    assert not verify_grade_attestation(VALUE, att, public, min_grade="good", now=future)


def test_grade_below_min_fails(keys):
    signing, public = keys
    att = _mint(signing, grade="weak")
    assert not verify_grade_attestation(VALUE, att, public, min_grade="good")


def test_grade_ordering(keys):
    signing, public = keys
    sound = _mint(signing, grade="sound")
    weak = _mint(signing, grade="weak")
    assert verify_grade_attestation(VALUE, sound, public, min_grade="good")
    assert not verify_grade_attestation(VALUE, weak, public, min_grade="good")
    assert verify_grade_attestation(VALUE, weak, public, min_grade="weak")


def test_bad_signature_fails(keys):
    signing, _ = keys
    att = _mint(signing)
    wrong_pub = ed25519_public_key_from_bytes(ed25519_public_bytes(ed25519_signing_key()))
    assert not verify_grade_attestation(VALUE, att, wrong_pub, min_grade="good")


def test_never_raises_on_garbage():
    public = ed25519_public_key_from_bytes(ed25519_public_bytes(ed25519_signing_key()))
    assert verify_grade_attestation(VALUE, "not-json", public, min_grade="good") is False
    assert verify_grade_attestation(VALUE, "{}", public, min_grade="good") is False


def test_constraint_missing_attestation_denied(keys):
    _, public = keys
    constraint = IsnadGradeConstraint(min_grade="good", trusted_public_key=public)
    assert not constraint.satisfies("DE89 ...")  # bare value, required=True
    assert not constraint.satisfies(attest(VALUE, None))  # missing attestation


def test_constraint_optional_missing_allowed(keys):
    _, public = keys
    constraint = IsnadGradeConstraint(min_grade="good", trusted_public_key=public, required=False)
    assert constraint.satisfies("bare-value") is True


def test_constraint_end_to_end(keys):
    signing, public = keys
    constraint = IsnadGradeConstraint(min_grade="good", trusted_public_key=public)
    sound = _mint(signing, grade="sound")
    weak = _mint(signing, grade="weak")
    assert constraint.satisfies(attest(VALUE, sound))
    assert not constraint.satisfies(attest(VALUE, weak))
    assert not constraint.satisfies(attest("OTHER", sound))


def test_constraint_repr(keys):
    _, public = keys
    constraint = IsnadGradeConstraint(min_grade="good", trusted_public_key=public)
    assert "IsnadGradeConstraint" in repr(constraint)
