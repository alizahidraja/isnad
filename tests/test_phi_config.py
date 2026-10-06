"""Tests for the 3.0.6 end-to-end phi config (ISNAD_PHI_SHARED_LINEAGE).

Locks the operator opt-in surface: the env var is read, validated, clamped, and
wired into the serving path so that setting it actually changes the
corroboration decision. Default stays 0.0 (no discount).
"""

import math

import pytest

from isnad.core.corroboration import (
    CappedCorroborationPolicy,
    CorroborationEngine,
    PHI_SHARED_LINEAGE_ENV,
    phi_shared_lineage_from_env,
)
from isnad.types import ChainGrade

PHI_MEASURED = 0.6172


class TestPhiSharedLineageFromEnv:
    def test_default_is_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PHI_SHARED_LINEAGE_ENV, raising=False)
        assert phi_shared_lineage_from_env() == 0.0

    def test_valid_value_passes_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PHI_SHARED_LINEAGE_ENV, "0.6172")
        assert phi_shared_lineage_from_env() == pytest.approx(0.6172)

    def test_empty_string_defaults_to_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PHI_SHARED_LINEAGE_ENV, "  ")
        assert phi_shared_lineage_from_env() == 0.0

    def test_clamps_high_to_just_below_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PHI_SHARED_LINEAGE_ENV, "1.5")
        assert phi_shared_lineage_from_env() == pytest.approx(1.0 - 1e-12)

    def test_clamps_low_to_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PHI_SHARED_LINEAGE_ENV, "-0.5")
        assert phi_shared_lineage_from_env() == 0.0

    def test_garbage_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PHI_SHARED_LINEAGE_ENV, "not-a-number")
        with pytest.raises(ValueError, match=PHI_SHARED_LINEAGE_ENV):
            phi_shared_lineage_from_env()

    def test_nan_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PHI_SHARED_LINEAGE_ENV, "nan")
        with pytest.raises(ValueError):
            phi_shared_lineage_from_env()

    def test_infinity_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PHI_SHARED_LINEAGE_ENV, "inf")
        with pytest.raises(ValueError):
            phi_shared_lineage_from_env()


class TestServingPathWiring:
    """The serving path constructs the policy exactly as claims.py now does:
    CappedCorroborationPolicy(phi_shared_lineage=phi_shared_lineage_from_env())."""

    def _shared_family_corroborators(self) -> tuple[dict, list[dict]]:
        meta = {
            "n:A": {"model_family": "gpt-4"},
            "n:B": {"model_family": "gpt-4"},
            "n:C": {"model_family": "gpt-4"},
            "n:D": {"model_family": "gpt-4"},
            "n:E": {"model_family": "gpt-4"},
        }
        chains = [
            {"grade": "hasan", "narrators": ["n:B"]},
            {"grade": "hasan", "narrators": ["n:C"]},
            {"grade": "hasan", "narrators": ["n:D"]},
            {"grade": "hasan", "narrators": ["n:E"]},
        ]
        return meta, chains

    def test_env_opt_in_changes_serving_path_decision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Setting the env var to the measured phi flips a shared-lineage
        corroboration that would otherwise upgrade DAIF->HASAN."""
        meta, chains = self._shared_family_corroborators()

        def run_with_env(value: str | None) -> ChainGrade:
            if value is None:
                monkeypatch.delenv(PHI_SHARED_LINEAGE_ENV, raising=False)
            else:
                monkeypatch.setenv(PHI_SHARED_LINEAGE_ENV, value)
            policy = CappedCorroborationPolicy(phi_shared_lineage=phi_shared_lineage_from_env())
            result = CorroborationEngine(policy=policy).evaluate_direct(
                base_chain_grade=ChainGrade.DAIF,
                base_narrators=["n:A"],
                corroborating_chains=chains,
                narrator_metadata=meta,
            )
            return result.upgraded_grade

        naive = run_with_env(None)
        discounted = run_with_env(str(PHI_MEASURED))

        assert naive == ChainGrade.HASAN
        assert discounted == ChainGrade.DAIF

    def test_default_env_keeps_policy_phi_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PHI_SHARED_LINEAGE_ENV, raising=False)
        policy = CappedCorroborationPolicy(phi_shared_lineage=phi_shared_lineage_from_env())
        assert policy.phi_shared_lineage == 0.0
        # sanity: the clamped value must not be NaN/Inf
        assert math.isfinite(policy.phi_shared_lineage)
