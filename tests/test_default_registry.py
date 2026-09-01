"""Tests for the warm default registry (issue #203)."""

from isnad import default_registry
from isnad.core.decision import gate_serve
from isnad.types import Action


def test_default_registry_ships_warm():
    reg = default_registry()
    assert reg.get("source:wikipedia", "general") is not None
    assert reg.get("model:gpt-4o", "general") is not None
    assert reg.get("scraper:web", "general") is not None


def test_every_seed_is_estimated_not_supported():
    """The honesty contract: shipped seeds are priors (Estimated), never
    observations (Supported). 'Supported' is only earned by real pipeline
    evidence, never shipped."""
    reg = default_registry()
    ids = [("source:wikipedia", "general"), ("model:gpt-4o", "general"), ("scraper:web", "general")]
    for nid, dom in ids:
        prov = reg.evidence_provenance(nid, dom)
        assert prov.prior_only is True, f"{nid} should be prior-only"
        assert prov.observation_backed is False, f"{nid} must not be observation-backed"


def test_prior_only_seed_cannot_plain_serve():
    """A chain through a seeded (prior-only) narrator must cap at
    SERVE_WITH_CAVEAT, never plain SERVE."""
    assert gate_serve(Action.SERVE, ["source:wikipedia"], hold=False) == Action.SERVE_WITH_CAVEAT


def test_unknown_vertical_returns_empty_registry():
    reg = default_registry(vertical="does-not-exist")
    assert len(reg._narrators) == 0
