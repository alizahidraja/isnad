"""Validate the committed critic eval set (issue #96).

The eval set is the ground truth for the measured critic numbers, so it must be
well-formed and internally consistent. These tests run in CI (no API keys, no
model downloads) and guard against a bad label or a duplicate slipping in.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EXP = Path(__file__).resolve().parents[1] / "experiments" / "critic_eval"
if str(_EXP) not in sys.path:
    sys.path.insert(0, str(_EXP))

from eval_set import (  # noqa: E402
    CONSISTENT_CASES,
    CONTRADICTION_CASES,
    CORPUS,
    UNRELATED_CASES,
    all_cases,
)

_VALID_LABELS = {"consistent", "contradiction", "unrelated"}
_EXPECTED = {
    "consistent": "consistent",
    "contradiction": "contradiction",
    "unrelated": "unverifiable",
}


def test_corpus_is_nonempty_and_unique() -> None:
    assert CORPUS, "corpus must not be empty"
    assert len(CORPUS) == len({c.lower() for c in CORPUS}), "corpus has duplicate facts"


def test_every_case_has_a_valid_label() -> None:
    for claim, label, expected in all_cases():
        assert label in _VALID_LABELS, f"bad label {label!r} on {claim!r}"
        assert expected == _EXPECTED[label]


def test_contradictions_do_not_verbatim_match_corpus() -> None:
    """A contradiction case must differ from every corpus fact — otherwise it
    isn't a contradiction."""
    corpus = {c.lower() for c in CORPUS}
    for claim, _ in CONTRADICTION_CASES:
        assert claim.lower() not in corpus, f"contradiction {claim!r} verbatim in corpus"


def test_consistent_cases_match_corpus_or_paraphrase() -> None:
    """At least the verbatim consistent cases must be in the corpus."""
    corpus = {c.lower() for c in CORPUS}
    verbatim = [c for c, _ in CONSISTENT_CASES if c.lower() in corpus]
    assert len(verbatim) >= 10, "expected most consistent cases to be verbatim corpus facts"


def test_counts_match_docs() -> None:
    assert len(CONSISTENT_CASES) == 20
    assert len(CONTRADICTION_CASES) == 25
    assert len(UNRELATED_CASES) == 15
