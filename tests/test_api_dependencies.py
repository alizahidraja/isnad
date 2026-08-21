"""Tests for deterministic API dependency-injection helpers.

These pin the config-driven branches that don't require external models:
seed-config parsing and the transition-policy builder.
"""

from __future__ import annotations

from isnad.api import dependencies as deps
from isnad.core.registry import BayesianTransitionPolicy, ThresholdTransitionPolicy
from isnad.types import NarratorGrade


class TestParseSeedConfig:
    def test_empty_env_returns_empty(self, monkeypatch) -> None:
        monkeypatch.delenv("ISNAD_SEED_CONFIG", raising=False)
        assert deps._parse_seed_config() == []

    def test_valid_config_parses(self, monkeypatch) -> None:
        monkeypatch.setenv(
            "ISNAD_SEED_CONFIG",
            '[{"narrator_id": "model:x", "domain": "physics", "grade": "reliable"}]',
        )
        seeds = deps._parse_seed_config()
        assert seeds == [("model:x", "physics", NarratorGrade.RELIABLE)]

    def test_missing_grade_defaults_to_ungraded(self, monkeypatch) -> None:
        monkeypatch.setenv("ISNAD_SEED_CONFIG", '[{"narrator_id": "model:y"}]')
        seeds = deps._parse_seed_config()
        assert seeds == [("model:y", "general", NarratorGrade.UNGRADED)]

    def test_invalid_json_returns_empty(self, monkeypatch) -> None:
        monkeypatch.setenv("ISNAD_SEED_CONFIG", "not-json")
        assert deps._parse_seed_config() == []

    def test_non_list_returns_empty(self, monkeypatch) -> None:
        monkeypatch.setenv("ISNAD_SEED_CONFIG", '{"not": "a list"}')
        assert deps._parse_seed_config() == []


class TestBuildPolicy:
    def test_default_is_bayesian(self, monkeypatch) -> None:
        monkeypatch.delenv("ISNAD_POLICY", raising=False)
        assert isinstance(deps._build_policy(), BayesianTransitionPolicy)

    def test_threshold_selected_by_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ISNAD_POLICY", "threshold")
        assert isinstance(deps._build_policy(), ThresholdTransitionPolicy)

    def test_unknown_policy_falls_back_to_bayesian(self, monkeypatch) -> None:
        monkeypatch.setenv("ISNAD_POLICY", "bogus")
        assert isinstance(deps._build_policy(), BayesianTransitionPolicy)
