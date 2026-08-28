"""Tests for content-level madār detection (#54, the detectable half)."""

from __future__ import annotations

from isnad.core.content_madar import ErrorFingerprint, detect_content_madar
from isnad.types import ContentVerdict

CONSISTENT = ContentVerdict.CONSISTENT
CONTRADICTION = ContentVerdict.CONTRADICTION
UNVERIFIABLE = ContentVerdict.UNVERIFIABLE


class TestErrorFingerprint:
    def test_identical_wrong_numbers_are_shared_error(self):
        a = ErrorFingerprint.from_claim("The total is 97 records.")
        b = ErrorFingerprint.from_claim("There are 97 records in total.")
        assert a.shares_error_with(b)

    def test_identical_numbers_different_negation_is_not_shared(self):
        # Same wrong number, but one claim says "not" — different polarity is a
        # different mistake, not an echo of the same one.
        a = ErrorFingerprint.from_claim("There are 97 records.")
        b = ErrorFingerprint.from_claim("There are not 97 records.")
        assert not a.shares_error_with(b)

    def test_different_numbers_are_not_shared_error(self):
        a = ErrorFingerprint.from_claim("The total is 97 records.")
        b = ErrorFingerprint.from_claim("The total is 95 records.")
        assert not a.shares_error_with(b)

    def test_commas_normalize(self):
        a = ErrorFingerprint.from_claim("3,000 records")
        b = ErrorFingerprint.from_claim("3000 records")
        assert a.shares_error_with(b)


class TestDetectContentMadar:
    def test_correct_agreement_is_not_madar(self):
        # Two chains agreeing on a CORRECT claim is expected — not correlation.
        madar = detect_content_madar(
            "The speed of light is 300,000 km/s.",
            CONSISTENT,
            [("The speed of light is 300,000 km/s.", CONSISTENT)],
        )
        assert madar is False

    def test_shared_wrong_number_is_madar(self):
        # Base claim contradicts the corpus (wrong number); a 'corroborating'
        # chain repeats the SAME wrong number -> a received mistake, not
        # independent confirmation.
        madar = detect_content_madar(
            "The speed of light is 500,000 km/s.",
            CONTRADICTION,
            [("The speed of light is 500,000 km/s.", CONTRADICTION)],
        )
        assert madar is True

    def test_different_wrong_numbers_are_not_madar(self):
        # Two chains making DIFFERENT mistakes are independently wrong — which
        # is itself weak evidence of independence (they didn't copy one error).
        madar = detect_content_madar(
            "The speed of light is 500,000 km/s.",
            CONTRADICTION,
            [("The speed of light is 700,000 km/s.", CONTRADICTION)],
        )
        assert madar is False

    def test_unverifiable_base_is_not_madar(self):
        # Novel claim the corpus can't check -> content-madar is undetectable,
        # reported False (not guessed True).
        madar = detect_content_madar(
            "The half-life of ununennium-295 is 12 ms.",
            UNVERIFIABLE,
            [("The half-life of ununennium-295 is 12 ms.", UNVERIFIABLE)],
        )
        assert madar is False

    def test_corroborator_not_flagged_is_not_madar(self):
        # Base is wrong, but the corroborator is NOT flagged as wrong — it's a
        # different reading, not an echo of the same error.
        madar = detect_content_madar(
            "The speed of light is 500,000 km/s.",
            CONTRADICTION,
            [("The speed of light is 300,000 km/s.", CONSISTENT)],
        )
        assert madar is False

    def test_shared_negation_is_madar(self):
        # A dropped/flipped negation repeated is a shared specific mistake.
        madar = detect_content_madar(
            "Energy is not conserved in an isolated system.",
            CONTRADICTION,
            [("Energy is not conserved in an isolated system.", CONTRADICTION)],
        )
        assert madar is True
