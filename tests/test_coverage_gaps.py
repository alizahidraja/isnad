"""Targeted tests that close specific coverage gaps in pure-logic modules.

These are the small, valuable branches that were previously untested:
- DeterministicRuleCritic.add_pattern (extending the contradiction set)
- decide()'s defensive KeyError for an incomplete matrix
- Live Verify document-specific normalization edge cases (byte-compatibility)
"""

from __future__ import annotations

import pytest

from isnad.core.decision import _MATRIX, decide
from isnad.integrations.liveverify.normalize import apply_doc_specific_norm, normalize_text
from isnad.matn import DeterministicRuleCritic
from isnad.types import Action, ChainGrade, ContentVerdict


class TestMatnAddPattern:
    def test_add_pattern_extends_contradiction_detection(self) -> None:
        critic = DeterministicRuleCritic()
        critic.add_pattern("water is wet", "water is dry")
        verdict = critic.evaluate(
            "water is wet",
            "water is wet",
            ["water is dry"],
        )
        assert verdict == ContentVerdict.CONTRADICTION

    def test_add_pattern_lowercases_inputs(self) -> None:
        critic = DeterministicRuleCritic()
        critic.add_pattern("WATER", "DRY")
        assert ("water", "dry") in critic._CONTRADICTION_PATTERNS


class TestDecisionMatrixDefensiveBranch:
    def test_decide_raises_keyerror_for_missing_combination(self, monkeypatch) -> None:
        # Remove one combination so the defensive branch fires.
        monkeypatch.delitem(_MATRIX, (ChainGrade.SAHIH, ContentVerdict.CONSISTENT))
        with pytest.raises(KeyError):
            decide(ChainGrade.SAHIH, ContentVerdict.CONSISTENT)

    def test_decide_is_total_for_all_defined_combinations(self) -> None:
        for cg in ChainGrade:
            for cv in ContentVerdict:
                assert isinstance(decide(cg, cv), Action)


class TestLiveVerifyNormalization:
    def test_valid_char_normalization(self) -> None:
        meta = {"charNormalization": "éè→e"}
        assert apply_doc_specific_norm("café crèche", meta) == "cafe creche"

    def test_char_normalization_skips_malformed_groups(self) -> None:
        meta = {"charNormalization": "noarrow multi→xy"}
        # "noarrow" has no →; "multi→xy" has a 2-char target → both skipped.
        assert apply_doc_specific_norm("abc", meta) == "abc"

    def test_ocr_rules_apply_regex(self) -> None:
        meta = {"ocrNormalizationRules": [{"pattern": r"\s+", "replacement": " "}]}
        assert apply_doc_specific_norm("a   b", meta) == "a b"

    def test_ocr_rules_skip_non_dict_entries(self) -> None:
        meta = {"ocrNormalizationRules": ["not-a-dict", {"pattern": "x", "replacement": "y"}]}
        assert apply_doc_specific_norm("x", meta) == "y"

    def test_ocr_rules_skip_invalid_regex(self) -> None:
        meta = {"ocrNormalizationRules": [{"pattern": "[", "replacement": "z"}]}
        assert apply_doc_specific_norm("x", meta) == "x"

    def test_ocr_rules_skip_missing_pattern_or_replacement(self) -> None:
        meta = {"ocrNormalizationRules": [{"pattern": "", "replacement": "z"}]}
        assert apply_doc_specific_norm("x", meta) == "x"

    def test_no_metadata_is_identity(self) -> None:
        assert apply_doc_specific_norm("hello", None) == "hello"

    def test_normalize_text_handles_unicode_quotes_dashes_ellipsis(self) -> None:
        text = "\u201chello\u201d \u2014 world\u2026\u00a0done"
        normalized = normalize_text(text)
        assert normalized == '"hello" - world... done'


class TestSha256Hex:
    def test_known_vector(self) -> None:
        from isnad.integrations.liveverify.normalize import sha256_hex

        # SHA-256 of the empty string, a well-known vector.
        assert sha256_hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
