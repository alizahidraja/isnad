"""Tests for bench.metrics — kappa, confusion matrix, per-class metrics."""

from __future__ import annotations

import pytest

from bench.metrics import (
    cohens_kappa,
    confusion_matrix,
    linear_weighted_kappa,
    per_class_metrics,
)


class TestConfusionMatrix:
    def test_counts(self):
        cm = confusion_matrix(["a", "a", "b", "b", "a"], ["a", "b", "b", "b", "a"], ["a", "b"])
        assert cm == {"a": {"a": 2, "b": 1}, "b": {"a": 0, "b": 2}}


class TestCohensKappa:
    def test_perfect_agreement_is_one(self):
        cm = {"a": {"a": 5, "b": 0}, "b": {"a": 0, "b": 5}}
        assert cohens_kappa(cm, ["a", "b"]) == pytest.approx(1.0)

    def test_known_example(self):
        # Classic worked example: p_o=0.75, p_e=0.71 → κ ≈ 0.1379.
        cm = {"yes": {"yes": 70, "no": 10}, "no": {"yes": 15, "no": 5}}
        assert cohens_kappa(cm, ["yes", "no"]) == pytest.approx(0.1379, abs=1e-3)

    def test_majority_class_is_zero(self):
        # Always predicting the mode yields κ = 0 (the point of kappa).
        cm = {"a": {"a": 60, "b": 0}, "b": {"a": 40, "b": 0}}
        assert cohens_kappa(cm, ["a", "b"]) == pytest.approx(0.0, abs=1e-9)

    def test_empty_matrix_is_zero(self):
        cm = {"a": {"a": 0, "b": 0}, "b": {"a": 0, "b": 0}}
        assert cohens_kappa(cm, ["a", "b"]) == 0.0


class TestLinearWeightedKappa:
    def test_perfect_is_one(self):
        cm = {"a": {"a": 5, "b": 0}, "b": {"a": 0, "b": 5}}
        assert linear_weighted_kappa(cm, ["a", "b"]) == pytest.approx(1.0)

    def test_near_miss_scores_higher_than_far_miss(self):
        # Off-by-one (a↔b) vs off-by-two (a↔c) on 3 ordinal classes,
        # with balanced marginals so chance agreement is well-defined.
        near = {
            "a": {"a": 0, "b": 1, "c": 0},
            "b": {"a": 0, "b": 1, "c": 0},
            "c": {"a": 0, "b": 0, "c": 1},
        }
        far = {
            "a": {"a": 0, "b": 0, "c": 1},
            "b": {"a": 0, "b": 1, "c": 0},
            "c": {"a": 0, "b": 0, "c": 1},
        }
        assert linear_weighted_kappa(near, ["a", "b", "c"]) == pytest.approx(0.5714, abs=1e-3)
        assert linear_weighted_kappa(far, ["a", "b", "c"]) == pytest.approx(0.25, abs=1e-3)
        assert linear_weighted_kappa(near, ["a", "b", "c"]) > linear_weighted_kappa(
            far, ["a", "b", "c"]
        )


class TestPerClassMetrics:
    def test_precision_recall_f1(self):
        classes = ["a", "b"]
        # true: a,a,a,b ; pred: a,a,b,b → a: TP2 FP0 FN1 ; b: TP1 FP1 FN0
        m = per_class_metrics(["a", "a", "a", "b"], ["a", "a", "b", "b"], classes)
        assert m["a"]["precision"] == pytest.approx(1.0)
        assert m["a"]["recall"] == pytest.approx(2 / 3)
        assert m["b"]["precision"] == pytest.approx(0.5)
        assert m["b"]["recall"] == pytest.approx(1.0)
        assert m["a"]["support"] == 3
        assert m["b"]["support"] == 1
