"""Tests for Bayesian grading engine and corroboration engine."""

from isnad.core.corroboration import CorroborationEngine
from isnad.core.registry import BayesianTransitionPolicy, BetaState, CalibratedThresholdPolicy
from isnad.types import ChainGrade, EvidenceAction, EvidenceType, NarratorGrade


class TestBetaState:
    def test_uniform_prior(self):
        state = BetaState()
        assert state.mean == 0.5
        assert 0.0 < state.std < 1.0

    def test_update_positive(self):
        state = BetaState()
        state.update(positive=True)
        assert state.mean > 0.5

    def test_update_negative(self):
        state = BetaState()
        state.update(positive=False)
        assert state.mean < 0.5

    def test_converges_to_true_rate(self):
        """After 100 trials at 80% success, mean should be near 0.8."""
        state = BetaState()
        for _ in range(80):
            state.update(positive=True)
        for _ in range(20):
            state.update(positive=False)
        assert 0.75 <= state.mean <= 0.85

    def test_to_grade_reliable(self):
        state = BetaState(alpha=20, beta=1)  # 95% success
        assert state.to_grade() == NarratorGrade.RELIABLE

    def test_to_grade_rejected(self):
        state = BetaState(alpha=1, beta=20)  # 5% success
        assert state.to_grade() == NarratorGrade.REJECTED

    def test_confidence_interval(self):
        state = BetaState(alpha=10, beta=2)
        lo, hi = state.confidence_interval()
        assert 0 < lo <= hi <= 1.0
        assert lo <= state.mean <= hi


class TestBayesianTransitionPolicy:
    def test_version_bump_resets(self):
        policy = BayesianTransitionPolicy()
        result = policy.evaluate_transition(
            NarratorGrade.RELIABLE,
            [],
            {"evidence_type": "version_bump", "action": "neutral"},
        )
        assert result == NarratorGrade.UNGRADED

    def test_evidence_counts_drive_grade(self):
        policy = BayesianTransitionPolicy()
        # 5 positive, 1 adverse → should be high confidence
        history = [{"action": "tadil"} for _ in range(5)] + [{"action": "jarh"}]
        result = policy.evaluate_transition(
            NarratorGrade.UNGRADED,
            history,
            {"evidence_type": "post_hoc_audit", "action": "tadil"},
        )
        assert result in (NarratorGrade.RELIABLE, NarratorGrade.ACCEPTABLE)

    def test_seed_grade_sets_prior(self):
        policy = BayesianTransitionPolicy()
        policy.seed_grade("model:x", "physics", prior_mean=0.95, prior_weight=20)
        state = policy.get_state("model:x", "physics")
        assert state.mean > 0.85


class TestCalibratedThresholdPolicy:
    def test_downgrade_fires(self):
        policy = CalibratedThresholdPolicy(downgrade_threshold=5)
        history = [{"action": "jarh"} for _ in range(5)]
        result = policy.evaluate_transition(
            NarratorGrade.RELIABLE,
            history,
            {"evidence_type": "post_hoc_audit", "action": "jarh"},
        )
        assert result == NarratorGrade.ACCEPTABLE

    def test_upgrade_requires_corroboration(self):
        policy = CalibratedThresholdPolicy(upgrade_sustained_count=10)
        # 6 corroborated + 4 regular = 10 total, 6 min corroborated met
        history = [{"action": "tadil", "evidence_type": "corroboration_outcome"} for _ in range(6)]
        history += [{"action": "tadil", "evidence_type": "post_hoc_audit"} for _ in range(4)]
        result = policy.evaluate_transition(
            NarratorGrade.WEAK,
            history,
            {"evidence_type": "corroboration_outcome", "action": "tadil"},
        )
        assert result == NarratorGrade.ACCEPTABLE


class TestConfigurableTransitionPolicyRatchet:
    """The §8 experiment's ConfigurableTransitionPolicy shares the ratchet fix.

    It lives under experiments/ and is loaded here directly from its file. This
    pins that the issue #9 finding #1 fix (sliding window + edge trigger) was
    applied there too: a downgraded narrator recovers, and a persistently
    failing one is still contained.
    """

    @staticmethod
    def _policy(**kw):
        import importlib.util
        import pathlib

        path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "experiments"
            / "s8_gated_vs_ungated"
            / "sweep_policy.py"
        )
        spec = importlib.util.spec_from_file_location("sweep_policy", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ConfigurableTransitionPolicy(**kw)

    def test_downgraded_narrator_recovers(self):
        from isnad.core.registry import Registry
        from isnad.types import EvidenceAxis

        policy = self._policy(downgrade_threshold=3)
        reg = Registry(transition_policy=policy)
        reg.register("n", "d", grade=NarratorGrade.RELIABLE)
        # Precision (ḍabṭ) lapse — recoverable.
        for _ in range(3):
            reg.record_evidence(
                "n",
                "d",
                EvidenceType.POST_HOC_AUDIT,
                EvidenceAction.JARH,
                "",
                axis=EvidenceAxis.PRECISION,
            )
        assert reg.get_grade("n", "d") == NarratorGrade.ACCEPTABLE
        for _ in range(policy.window + policy.upgrade_sustained_count):
            reg.record_evidence(
                "n",
                "d",
                EvidenceType.CORROBORATION_OUTCOME,
                EvidenceAction.TADIL,
                "",
                axis=EvidenceAxis.PRECISION,
            )
        assert reg.get_grade("n", "d") == NarratorGrade.RELIABLE

    def test_persistent_adverse_still_reaches_rejected(self):
        from isnad.core.registry import Registry

        policy = self._policy(downgrade_threshold=3)
        reg = Registry(transition_policy=policy)
        reg.register("bad", "d", grade=NarratorGrade.RELIABLE)
        for _ in range(9):
            reg.record_evidence("bad", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, "")
        assert reg.get_grade("bad", "d") == NarratorGrade.REJECTED


class TestCorroborationEngine:
    def test_mawdu_cannot_be_upgraded(self):
        engine = CorroborationEngine()
        result = engine.evaluate("claim", ChainGrade.MAWDU, ["n1"], [])
        assert not result.upgraded
        assert "MAWDU" in result.reason

    def test_needs_independent_chains(self):
        engine = CorroborationEngine(min_independent_chains=2)
        result = engine.evaluate(
            "F=ma",
            ChainGrade.DAIF,
            ["n1", "n2"],
            [
                {
                    "claim_text": "F=ma",
                    "chain_grade": "hasan",
                    "narrator_ids": ["n1", "n3"],
                },  # shares n1
            ],
        )
        assert not result.upgraded

    def test_daif_upgraded_with_good_corroboration(self):
        engine = CorroborationEngine(min_independent_chains=2)
        chains = [
            {"claim_text": "E=mc^2", "chain_grade": "hasan", "narrator_ids": ["n3", "n4"]},
            {"claim_text": "E=mc^2", "chain_grade": "hasan", "narrator_ids": ["n5", "n6"]},
        ]
        # Attested distinct lineage → demonstrable independence (issue #54).
        metadata = {
            n: {"model_family": f"f{n}", "upstream_source": f"s{n}"}
            for n in ["n1", "n2", "n3", "n4", "n5", "n6"]
        }
        result = engine.evaluate(
            "E=mc^2", ChainGrade.DAIF, ["n1", "n2"], chains, narrator_metadata=metadata
        )
        assert result.upgraded
        assert result.upgraded_grade == ChainGrade.HASAN

    # Attested distinct lineage so chains clear the independence check (issue
    # #54) and these tests isolate the gate / weight logic they actually target.
    _LINEAGE = {
        "n1": {"model_family": "f1", "upstream_source": "s1"},
        "n3": {"model_family": "f3", "upstream_source": "s3"},
        "n4": {"model_family": "f4", "upstream_source": "s4"},
    }

    def test_min_grade_gate_blocks_weak(self):
        engine = CorroborationEngine(min_independent_chains=1, min_gate_grade=ChainGrade.HASAN)
        chains = [
            {"claim_text": "x", "chain_grade": "daif", "narrator_ids": ["n3"]},
        ]
        result = engine.evaluate(
            "x", ChainGrade.DAIF, ["n1"], chains, narrator_metadata=self._LINEAGE
        )
        assert not result.upgraded
        assert "min grade" in result.reason.lower()

    def test_effective_weight_computed(self):
        engine = CorroborationEngine()
        chains = [
            {"claim_text": "p=mv", "chain_grade": "hasan", "narrator_ids": ["n3"]},
            {"claim_text": "p=mv", "chain_grade": "hasan", "narrator_ids": ["n4"]},
        ]
        result = engine.evaluate(
            "p=mv", ChainGrade.DAIF, ["n1"], chains, narrator_metadata=self._LINEAGE
        )
        assert result.effective_weight > 0
        assert result.upgraded
