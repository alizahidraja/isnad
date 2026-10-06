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


class TestServingPathWiringEndToEnd:
    """Locks the ACTUAL claims.py ``submit_claim`` wiring, not a reimplementation.

    If the serving-path one-liner were reverted to an inline
    ``CorroborationEngine()`` (dropping the env opt-in), these tests fail.
    """

    def test_helper_respects_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from isnad.api.endpoints import claims

        monkeypatch.setenv(PHI_SHARED_LINEAGE_ENV, str(PHI_MEASURED))
        engine = claims._build_corroboration_engine()
        assert engine._policy.phi_shared_lineage == pytest.approx(PHI_MEASURED)

    def test_helper_defaults_to_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from isnad.api.endpoints import claims

        monkeypatch.delenv(PHI_SHARED_LINEAGE_ENV, raising=False)
        engine = claims._build_corroboration_engine()
        assert engine._policy.phi_shared_lineage == 0.0

    def test_submit_claim_uses_helper(self) -> None:
        import inspect

        from isnad.api.endpoints import claims

        src = inspect.getsource(claims.submit_claim)
        assert "_build_corroboration_engine()" in src


class TestEffectiveVotes:
    """The Kish effective-vote count is surfaced on CorroborationResult and in
    the serialized audit record, so a compliance buyer sees the discounted
    count, not the raw "n independent routes" count."""

    def _shared_family_corroborators(self) -> tuple[dict, list[dict]]:
        meta = {
            "n:A": {"model_family": "gpt-4"},
            "n:B": {"model_family": "gpt-4"},
            "n:C": {"model_family": "gpt-4"},
            "n:D": {"model_family": "gpt-4"},
        }
        chains = [
            {"grade": "hasan", "narrators": ["n:B"]},
            {"grade": "hasan", "narrators": ["n:C"]},
            {"grade": "hasan", "narrators": ["n:D"]},
        ]
        return meta, chains

    def test_phi_zero_equals_raw_count(self) -> None:
        meta, chains = self._shared_family_corroborators()
        policy = CappedCorroborationPolicy(phi_shared_lineage=0.0)
        result = CorroborationEngine(policy=policy).evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["n:A"],
            corroborating_chains=chains,
            narrator_metadata=meta,
        )
        assert result.effective_votes == pytest.approx(1 + result.independent_chains)

    def test_phi_measured_reduces_count(self) -> None:
        meta, chains = self._shared_family_corroborators()
        policy = CappedCorroborationPolicy(phi_shared_lineage=PHI_MEASURED)
        result = CorroborationEngine(policy=policy).evaluate_direct(
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["n:A"],
            corroborating_chains=chains,
            narrator_metadata=meta,
        )
        raw = 1 + result.independent_chains
        assert result.effective_votes < raw
        assert result.effective_votes == pytest.approx(raw / (1 + (raw - 1) * PHI_MEASURED))

    def test_serialized_output_includes_effective_votes(self) -> None:
        import inspect

        from isnad.api.endpoints import claims

        assert '"effective_votes"' in inspect.getsource(claims.submit_claim)
