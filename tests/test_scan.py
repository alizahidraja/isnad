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
