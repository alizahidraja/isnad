"""Tests for the warm default registry (#203, #204)."""

from isnad import default_registry
from isnad.core.decision import gate_serve
from isnad.core.registry import _DEFAULT_SEED_ENTRIES
from isnad.types import Action, NarratorGrade, NarratorType


def test_default_registry_ships_warm():
    reg = default_registry()
    assert len(reg._narrators) == len(_DEFAULT_SEED_ENTRIES)
    assert reg.get("source:wikipedia", "general") is not None
    assert reg.get("model:gpt-4o", "general") is not None
    assert reg.get("scraper:web-generic", "general") is not None


def test_every_seed_is_estimated_not_supported():
    """The honesty contract: shipped seeds are priors (Estimated), never
    observations (Supported). 'Supported' is only earned by real pipeline
    evidence, never shipped."""
    reg = default_registry()
    for nid, dom in reg._narrators:
        prov = reg.evidence_provenance(nid, dom)
        assert prov.prior_only is True, f"{nid} should be prior-only"
        assert prov.observation_backed is False, f"{nid} must not be observation-backed"


def test_all_seed_values_are_valid():
    """Every shipped entry must use valid enum values (fail loudly, not silently)."""
    for entry in _DEFAULT_SEED_ENTRIES:
        NarratorGrade(entry.grade)
        NarratorType(entry.narrator_type)
        assert entry.source, f"{entry.narrator_id} missing evidence source"


def test_seed_grades_are_conservative():
    """Never ship a REJECTED or UNGRADED default — only conservative priors."""
    for entry in _DEFAULT_SEED_ENTRIES:
        assert entry.grade in ("reliable", "acceptable", "weak"), (
            f"{entry.narrator_id}: cannot ship {entry.grade} as a prior"
        )


def test_prior_only_seed_cannot_plain_serve():
    """A chain through a seeded (prior-only) narrator must cap at
    SERVE_WITH_CAVEAT, never plain SERVE."""
    assert gate_serve(Action.SERVE, ["source:wikipedia"], hold=False) == Action.SERVE_WITH_CAVEAT


def test_unknown_vertical_returns_empty_registry():
    reg = default_registry(vertical="does-not-exist")
    assert len(reg._narrators) == 0


def test_default_seed_entries_are_evidence_sourced():
    """Serving warms from evidence-sourced defaults, not unprovenanced seeds (#2.21.1)."""
    from isnad.core.registry import default_seed_entries

    entries = default_seed_entries()
    assert len(entries) == len(_DEFAULT_SEED_ENTRIES)
    assert all(e.source != "warm-start" for e in entries)
    assert all(e.grade in {"reliable", "acceptable", "weak"} for e in entries)
