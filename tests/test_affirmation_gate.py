"""Tests for the default-ON affirmation gate (issue #34)."""

from __future__ import annotations

import pytest

from isnad.critics.affirmation_gate import allows, gated, register, _records
from isnad.types import ContentVerdict


@pytest.fixture(autouse=True)
def _clear_records(monkeypatch):
    _records.clear()
    monkeypatch.delenv("ISNAD_AFFIRMATION_MAX_FCR", raising=False)
    monkeypatch.delenv("ISNAD_AFFIRMATION_MAX_AGE_DAYS", raising=False)
    yield
    _records.clear()


def _record(**overrides) -> dict:
    rec = {
        "schema_version": 1,
        "domain": "physics",
        "critic_kind": "llm",
        "provider": None,
        "model": None,
        "n_cases": 60,
        "n_contradiction_cases": 25,
        "false_consistent_count": 0,
        "false_consistent_rate": 0.0,
        "eval_set_sha256": "abc123",
        "evaluated_at": "2026-08-01T00:00:00Z",
    }
    rec.update(overrides)
    return rec


def test_no_record_refuses_affirmation():
    assert allows("llm", "physics") is False
    assert gated("llm", "physics", ContentVerdict.CONSISTENT) is ContentVerdict.UNVERIFIABLE


def test_valid_record_licenses_affirmation():
    register(_record())
    assert allows("llm", "physics", provider="deepseek", model="deepseek-chat") is True
    assert (
        gated(
            "llm", "physics", ContentVerdict.CONSISTENT, provider="deepseek", model="deepseek-chat"
        )
        is ContentVerdict.CONSISTENT
    )


def test_gate_never_suppresses_contradiction():
    # No record, but CONTRADICTION/UNVERIFIABLE pass through untouched.
    assert gated("llm", "physics", ContentVerdict.CONTRADICTION) is ContentVerdict.CONTRADICTION
    assert gated("llm", "physics", ContentVerdict.UNVERIFIABLE) is ContentVerdict.UNVERIFIABLE


def test_provider_model_mismatch_refuses():
    register(_record(provider="deepseek", model="deepseek-chat"))
    assert allows("llm", "physics", provider="openai", model="gpt-4o") is False


def test_threshold_refuses_when_rate_too_high():
    register(_record(false_consistent_count=3, false_consistent_rate=0.12))
    assert allows("llm", "physics") is False


def test_small_denominator_refuses():
    register(_record(n_contradiction_cases=10))
    assert allows("llm", "physics") is False


def test_missing_eval_set_sha_refuses():
    register(_record(eval_set_sha256=""))
    assert allows("llm", "physics") is False


def test_expired_record_refuses():
    register(_record(evaluated_at="2020-01-01T00:00:00Z"))
    assert allows("llm", "physics") is False


def test_future_dated_record_refuses():
    register(_record(evaluated_at="2099-01-01T00:00:00Z"))
    assert allows("llm", "physics") is False


def test_threshold_env_override_relaxes(monkeypatch):
    monkeypatch.setenv("ISNAD_AFFIRMATION_MAX_FCR", "0.2")
    register(_record(false_consistent_count=3, false_consistent_rate=0.12))
    assert allows("llm", "physics") is True
