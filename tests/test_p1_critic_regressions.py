"""Regression tests for the P1 critic fixes (content-madar contractions + RecomputeCritic units)."""

from __future__ import annotations

from isnad.core.content_madar import ErrorFingerprint
from isnad.critics.recompute import RecomputeCritic
from isnad.types import ContentVerdict


def test_couldnt_and_could_not_are_shared_error():
    a = ErrorFingerprint.from_claim("The model couldn't produce 97 records.")
    b = ErrorFingerprint.from_claim("The model could not produce 97 records.")
    assert a.negation is True
    assert b.negation is True
    assert a.shares_error_with(b)


def test_same_entities_different_numbers_are_not_shared_error():
    a = ErrorFingerprint.from_claim("Acme did not report 97 records.")
    b = ErrorFingerprint.from_claim("Acme did not report 95 records.")
    assert a.negation is True and b.negation is True
    assert a.entities == b.entities  # same entity set, different numbers
    assert not a.shares_error_with(b)


def test_count_noun_does_not_trigger_unit_guard():
    critic = RecomputeCritic()
    # "30 kg" is a real unit in the corpus; "30 entries" is a count noun, not a unit.
    # Before the fix the unit guard downgraded this to UNVERIFIABLE; it must not.
    verdict = critic.evaluate(
        "The report has 30 entries.",
        "The report has 30 entries.",
        ["category: 30 kg"],
    )
    assert verdict is ContentVerdict.CONSISTENT


def test_comma_formatted_unit_mismatch_is_caught():
    critic = RecomputeCritic()
    # "1,240 miles" (comma) must normalize to "1240" and mismatch "1240 km".
    verdict = critic.evaluate(
        "The trip is 1,240 miles.",
        "The trip is 1,240 miles.",
        ["distance: 1240 km"],
    )
    assert verdict is ContentVerdict.UNVERIFIABLE
