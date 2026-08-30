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

    def test_no_numbers_returns_bool_false_not_frozenset(self):
        """Empty numbers must return False (bool), not an empty frozenset."""
        a = ErrorFingerprint.from_claim("This claim has no figures at all.")
        b = ErrorFingerprint.from_claim("This claim also has no figures whatsoever.")
        result = a.shares_error_with(b)
        assert result is False
        assert isinstance(result, bool)


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

    def test_shared_wrong_entity_is_madar(self):
        # Same wrong author + wrong work, reworded — error identity, not text.
        madar = detect_content_madar(
            "Shakespeare wrote the Iliad.",
            CONTRADICTION,
            [("The Iliad was authored by Shakespeare.", CONTRADICTION)],
        )
        assert madar is True

    def test_different_wrong_entity_is_not_madar(self):
        # Different wrong author — different mistake, not a shared one.
        madar = detect_content_madar(
            "Shakespeare wrote the Iliad.",
            CONTRADICTION,
            [("Marlowe wrote the Iliad.", CONTRADICTION)],
        )
        assert madar is False

    def test_same_subject_different_work_is_not_madar(self):
        # Shared subject alone is NOT a shared error (set equality, not intersection).
        madar = detect_content_madar(
            "Shakespeare wrote the Iliad.",
            CONTRADICTION,
            [("Shakespeare wrote the Odyssey.", CONTRADICTION)],
        )
        assert madar is False

    def test_shared_wrong_date_is_madar(self):
        madar = detect_content_madar(
            "The event occurred in the year 1492.",
            CONTRADICTION,
            [("A historical event took place in 1492.", CONTRADICTION)],
        )
        assert madar is True


class TestContentMadarWiredIntoEngine:
    """The engine withholds corroboration when a corroborator repeats the base
    claim's same error (the #54 gap that was previously unwired)."""

    def test_engine_withholds_on_shared_wrong_number(self):
        from isnad.core.corroboration import CorroborationEngine
        from isnad.types import ChainGrade

        engine = CorroborationEngine()
        result = engine.evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["source:A", "ingest:A", "model:A"],
            corroborating_chains=[
                {
                    "grade": "hasan",
                    "narrators": ["source:B", "ingest:B", "model:B"],
                    "claim_text": "The total is 97 records.",
                    "content_verdict": "contradiction",
                }
            ],
            base_claim_text="The total is 97 records.",
            base_content_verdict=ContentVerdict.CONTRADICTION,
        )
        assert result.upgraded is False
        assert result.shared_error_detected is True
        assert "content-level madār" in result.reason

    def test_engine_withholds_even_without_live_contradiction_flag(self):
        """The madār gate fires on the base verdict alone — the caller does not
        need to also pass has_live_contradiction."""
        from isnad.core.corroboration import CorroborationEngine
        from isnad.types import ChainGrade

        engine = CorroborationEngine()
        result = engine.evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["source:A"],
            corroborating_chains=[
                {
                    "grade": "hasan",
                    "narrators": ["source:B"],
                    "claim_text": "Energy is not conserved in an isolated system.",
                    "content_verdict": "contradiction",
                }
            ],
            base_claim_text="Energy is not conserved in an isolated system.",
            base_content_verdict=ContentVerdict.CONTRADICTION,
            # has_live_contradiction deliberately NOT set
        )
        assert result.upgraded is False
        assert result.shared_error_detected is True

    def test_engine_does_not_withhold_on_different_errors(self):
        """Two chains making different mistakes are independently wrong, not a
        shared upstream — corroboration proceeds normally (no madār)."""
        from isnad.core.corroboration import CorroborationEngine
        from isnad.types import ChainGrade

        engine = CorroborationEngine()
        result = engine.evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["source:A"],
            corroborating_chains=[
                {
                    "grade": "hasan",
                    "narrators": ["source:B"],
                    "claim_text": "The speed of light is 700,000 km/s.",
                    "content_verdict": "contradiction",
                }
            ],
            base_claim_text="The speed of light is 500,000 km/s.",
            base_content_verdict=ContentVerdict.CONTRADICTION,
        )
        assert result.shared_error_detected is False
