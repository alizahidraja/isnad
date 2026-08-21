"""Tests for the critic evaluation harness (critics/eval.py).

The harness measures content critics honestly — precision/recall, and most
importantly the false-CONSISTENT rate (contradictions a critic wrongly calls
fine).  These are the metrics behind the README's "what's validated" claims,
so they deserve tests even though the harness itself was previously orphaned.
"""

from __future__ import annotations

from isnad.critics import eval as eval_mod
from isnad.critics.embedding import EmbeddingCritic
from isnad.matn import DeterministicRuleCritic
from isnad.types import ContentVerdict


class TestBuildEvalSet:
    def test_builds_contradiction_templates_without_corpus(self):
        # There are 10 hardcoded contradiction templates; n beyond that is
        # capped by the template count.
        entries = eval_mod.build_eval_set(None, n=20)
        assert len(entries) == 10
        # All entries without a corpus are contradiction templates.
        assert all(e["true_label"] == "contradiction" for e in entries)
        # Each has a claim and a corpus context list.
        assert all(e["claim_text"] for e in entries)
        assert all(isinstance(e["corpus"], list) for e in entries)

    def test_respects_n_cap(self):
        entries = eval_mod.build_eval_set(None, n=3)
        assert len(entries) == 3

    def test_is_deterministic_given_seed(self):
        a = eval_mod.build_eval_set(None, n=10)
        b = eval_mod.build_eval_set(None, n=10)
        assert [e["claim_text"] for e in a] == [e["claim_text"] for e in b]


class TestEvaluateCritic:
    def _entries(self):
        return [
            {
                "claim_text": "energy is not conserved",
                "normalized": "energy is not conserved",
                "corpus": ["energy is conserved"],
                "true_label": "contradiction",
                "domain": "general",
            },
            {
                "claim_text": "force equals mass times acceleration",
                "normalized": "force equals mass times acceleration",
                "corpus": [],
                "true_label": "consistent",
                "domain": "general",
            },
        ]

    def test_perfect_critic_scores_full(self):
        class PerfectCritic:
            def evaluate(self, claim_text, normalized, corpus, domain):
                return (
                    ContentVerdict.CONTRADICTION
                    if "not conserved" in claim_text
                    else ContentVerdict.CONSISTENT
                )

        m = eval_mod.evaluate_critic(PerfectCritic(), self._entries())
        assert m["tp"] == 1
        assert m["tn"] == 1
        assert m["precision"] == 1.0
        assert m["recall"] == 1.0
        assert m["false_consistent_among_contra"] == 0.0

    def test_false_consistent_is_flagged(self):
        """A critic that never flags contradictions has a dangerous false-consistent rate."""

        class AlwaysConsistentCritic:
            def evaluate(self, claim_text, normalized, corpus, domain):
                return ContentVerdict.CONSISTENT

        m = eval_mod.evaluate_critic(AlwaysConsistentCritic(), self._entries())
        assert m["fn"] == 1  # the contradiction was missed
        assert m["false_consistent_among_contra"] == 1.0

    def test_embedding_critic_runs(self):
        m = eval_mod.evaluate_critic(EmbeddingCritic(), self._entries())
        # Just assert it produces all expected keys without error.
        for key in ("precision", "recall", "f1", "false_consistent_among_contra", "accuracy"):
            assert key in m


class TestGenerateReport:
    def test_report_marks_unsafe_false_consistent_rate(self):
        results = {
            "stub": {
                "total": 10,
                "precision": 0.5,
                "recall": 0.3,
                "f1": 0.4,
                "false_consistent_among_contra": 0.4,
                "accuracy": 0.5,
                "unverifiable": 3,
            },
        }
        report = eval_mod.generate_report(results)
        assert "NOT SAFE" in report
        assert "False-Consistent" in report

    def test_report_marks_acceptable_rate(self):
        results = {
            "good": {
                "total": 10,
                "precision": 0.9,
                "recall": 0.9,
                "f1": 0.9,
                "false_consistent_among_contra": 0.01,
                "accuracy": 0.9,
                "unverifiable": 0,
            },
        }
        report = eval_mod.generate_report(results)
        assert "Acceptable" in report
