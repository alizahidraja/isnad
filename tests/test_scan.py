"""Tests for the pipeline coverage scan (#206)."""

from isnad.core.registry import default_registry
from isnad.scan import scan_registry


def test_scan_vouched_vs_cold():
    reg = default_registry()
    result = scan_registry(["source:wikipedia", "model:gpt-4o", "unknown:narrator"], reg, "general")
    assert len(result.vouched) == 2
    assert len(result.cold) == 1
    assert result.cold[0]["narrator_id"] == "unknown:narrator"


def test_vouched_entries_carry_ordinal_grade_and_provenance():
    reg = default_registry()
    result = scan_registry(["source:wikipedia"], reg, "general")
    entry = result.vouched[0]
    assert entry["grade"] in ("reliable", "acceptable", "weak")
    assert entry["provenance"].startswith("prior")
    # Evidence listing only — no numeric confidence key.
    assert "score" not in entry and "confidence" not in entry


def test_empty_scan():
    reg = default_registry()
    result = scan_registry([], reg, "general")
    assert result.vouched == []
    assert result.cold == []


def test_ungraded_narrator_is_cold():
    from isnad.core.registry import Registry
    from isnad.types import NarratorGrade

    reg = Registry()
    reg.register("x", "general", grade=NarratorGrade.UNGRADED)
    result = scan_registry(["x"], reg, "general")
    assert len(result.cold) == 1
    assert len(result.vouched) == 0


def test_bare_register_is_not_labeled_supported():
    """A grade with no evidence is 'unvalidated', never 'Supported' (#206 audit)."""
    from isnad.core.registry import Registry
    from isnad.types import NarratorGrade

    reg = Registry()
    reg.register("x", "general", grade=NarratorGrade.WEAK)  # grade but NO evidence
    result = scan_registry(["x"], reg, "general")
    entry = result.vouched[0]
    assert entry["provenance"] == "unvalidated (no observed or human evidence)"


def test_human_reviewed_narrator_is_labeled_human_not_unvalidated():
    """A narrator with human evidence must not be labeled 'no human evidence' (2.21.2)."""
    from isnad.core.registry import Registry

    reg = Registry()
    reg.register("model:x", "general")
    reg.quarantine("model:x", "general", "fabrication")  # HUMAN_REVIEW, grade -> REJECTED
    result = scan_registry(["model:x"], reg, "general")
    entry = result.vouched[0]
    assert entry["provenance"] == "human (Reviewed)"


def test_expired_narrator_is_cold():
    """A time-decayed narrator is cold, not 'vouched' (2.21.2)."""
    from datetime import UTC, datetime
    from isnad.core.registry import default_registry

    reg = default_registry()
    n = reg.get("source:wikipedia", "general")
    n.valid_until = datetime(2020, 1, 1, tzinfo=UTC)
    n.graded_at = datetime(2019, 1, 1, tzinfo=UTC)
    result = scan_registry(["source:wikipedia"], reg, "general")
    assert len(result.cold) == 1
    assert len(result.vouched) == 0
