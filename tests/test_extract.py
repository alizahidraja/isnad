"""Regression tests for the §8 corpus extractor (issue #94).

Pins the three defects the rewrite fixes:

1. The "X is Y" → "X equals Y" rewrite is gone (it garbled prose and broke
   formula matching — "p equals mv" no longer matched the critic's "p = mv").
2. Multiple-choice prefixes, questions, boilerplate, OCR fragments, and control
   chars are filtered out.
3. The method is honest: sentence-level spans, not LLM "atomic claims".
"""

from __future__ import annotations

import sys
from pathlib import Path

_EXP = Path(__file__).resolve().parents[1] / "experiments" / "s8_gated_vs_ungated"
if str(_EXP) not in sys.path:
    sys.path.insert(0, str(_EXP))

import extract as ex  # noqa: E402


class TestIsClaim:
    def test_normal_declarative_sentence_accepted(self) -> None:
        assert ex._is_claim("The momentum of a photon is h over lambda.")
        assert ex._is_claim("Work is a transfer of energy.")

    def test_formula_accepted_on_its_own(self) -> None:
        assert ex._is_claim("p = mv")

    def test_question_rejected(self) -> None:
        assert not ex._is_claim("What is the momentum of a photon?")

    def test_multiple_choice_prefix_stripped_then_accepted(self) -> None:
        # "D The glass is sitting..." → strip "D " → valid claim.
        assert ex._is_claim("D The glass is sitting on a level table.")

    def test_boilerplate_rejected(self) -> None:
        assert not ex._is_claim("Learning Objectives: understand momentum")
        assert not ex._is_claim("Check Your Understanding 6.3")
        assert not ex._is_claim("Figure 2.32 shows the setup.")
        assert not ex._is_claim("Example 4.1 Computing momentum")

    def test_control_chars_rejected(self) -> None:
        assert not ex._is_claim("The value is su\x00ce.")

    def test_unbalanced_brackets_rejected(self) -> None:
        assert not ex._is_claim("The weight is weightless(i")

    def test_fragment_without_verb_rejected(self) -> None:
        assert not ex._is_claim("momentum and energy")  # noun phrase, no verb

    def test_too_short_rejected(self) -> None:
        assert not ex._is_claim("Momentum.")


class TestStripMcPrefix:
    def test_letter_dot(self) -> None:
        assert ex._strip_mc_prefix("A. the answer") == "the answer"

    def test_letter_paren(self) -> None:
        assert ex._strip_mc_prefix("(b) the answer") == "the answer"

    def test_number_dot(self) -> None:
        assert ex._strip_mc_prefix("1. the answer") == "the answer"

    def test_lone_letter(self) -> None:
        assert ex._strip_mc_prefix("D The glass is sitting") == "The glass is sitting"


class TestDehyphenate:
    def test_rejoins_split_word(self) -> None:
        assert ex._dehyphenate("ex- pansions") == "expansions"


class TestEndToEnd:
    def _run(self, text: str) -> list[str]:
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "openstax_vol1_chunk_001.txt"), "w") as f:
                f.write("# Source: test\n# License: CC BY\n\n")
                f.write(text)
            claims = ex.extract_claims_from_chunks(d)
        return [c.text for c in claims]

    def test_no_equals_rewrite(self) -> None:
        texts = self._run(
            "The glass is sitting on a level table. Heat is weightless. "
            "Sound waves consist of compressions and expansions."
        )
        assert any("glass is sitting" in t for t in texts)
        assert any("consist of compressions" in t for t in texts)
        assert all(" equals " not in t for t in texts), texts

    def test_formula_kept_as_is(self) -> None:
        texts = self._run("The momentum of a photon is p = h/lambda.")
        assert any("p = h/lambda" in t for t in texts), texts

    def test_multiple_choice_prefixes_and_questions_filtered(self) -> None:
        texts = self._run(
            "D The glass is sitting on a level table. "
            "B Heat is weightless. "
            "What is the momentum of a photon?"
        )
        assert all(not t.startswith(("A", "B", "C", "D")) for t in texts), texts
        assert all(not t.endswith("?") for t in texts), texts
        # The MC-prefixed declarative answers survive as clean sentences.
        assert any("glass is sitting" in t for t in texts)

    def test_boilerplate_filtered(self) -> None:
        texts = self._run(
            "Learning Objectives: understand momentum. "
            "Check Your Understanding 6.3. "
            "Figure 2.32 shows the setup. "
            "The momentum of a photon is p = h/lambda."
        )
        assert all("Learning Objectives" not in t for t in texts)
        assert all("Check Your Understanding" not in t for t in texts)
        assert any("p = h/lambda" in t for t in texts)

    def test_garbage_not_in_output(self) -> None:
        texts = self._run("D The glass is sitting on a level table. B Heat is weightless(i")
        assert all(" equals " not in t for t in texts)
        assert all("weightless(i" not in t for t in texts)
        assert any("glass is sitting" in t for t in texts)
