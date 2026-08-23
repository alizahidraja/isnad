"""Tests for the one-call convenience API (isnad.grade / Verdict)."""

from __future__ import annotations

from isnad import Registry, grade
from isnad.types import ChainGrade, NarratorGrade


def test_grade_returns_verdict_with_weakest_and_why() -> None:
    reg = Registry()
    reg.register("openstax", "physics", grade=NarratorGrade.RELIABLE)
    reg.register("pdf-scraper", "physics", grade=NarratorGrade.UNGRADED)
    reg.register("ingest", "physics", grade=NarratorGrade.ACCEPTABLE)

    v = grade("p = mv", ["openstax", "pdf-scraper", "ingest"], reg, domain="physics")
    assert v.chain_grade == ChainGrade.DAIF  # ungraded → ḍaʿīf (strict default)
    assert v.weakest_link == "pdf-scraper"
    assert "pdf-scraper" in v.why and "ungraded" in v.why
    assert v.action is None  # no content verdict → no matrix action


def test_grade_all_reliable_is_sahih() -> None:
    reg = Registry()
    reg.register("a", "d", grade=NarratorGrade.RELIABLE)
    reg.register("b", "d", grade=NarratorGrade.RELIABLE)
    v = grade("x", ["a", "b"], reg, domain="d")
    assert v.chain_grade == ChainGrade.SAHIH
