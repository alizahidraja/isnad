"""Tests for the model-drift leaderboard harness (#71): oracle correctness/non-circularity,
determinism, and the honesty controls."""

from __future__ import annotations

import json
from pathlib import Path

from isnad.core.decision import decide
from isnad.core.grading import grade_chain
from isnad.types import NarratorGrade, TransformType

from experiments.model_drift import run as md_run
from experiments.model_drift.dataset import FACT_CORPUS, DriftInjector, dataset_sha256
from experiments.model_drift.oracle import GroundTruth, find_fact, label_claim


def test_oracle_labels_faithful_and_hallucinated():
    fact = find_fact("f001")  # capital of France = Paris; wrong: London/Berlin/Rome
    assert label_claim("The capital of France is Paris.", fact) is GroundTruth.FAITHFUL
    assert label_claim("The capital of France is London.", fact) is GroundTruth.HALLUCINATED
    assert label_claim("I like pancakes.", fact) is GroundTruth.UNVERIFIABLE


def test_oracle_uses_corpus_not_critic():
    """The oracle's only input is the fact (correct/wrong values); it never sees a critic."""
    fact = find_fact("f003")  # water boils at 100; wrong: 90/110/212
    assert label_claim("Water boils at 100 degrees.", fact) is GroundTruth.FAITHFUL
    assert label_claim("Water boils at 212 degrees.", fact) is GroundTruth.HALLUCINATED


def test_drift_injector_deterministic():
    a = DriftInjector(0.25, seed=7)
    b = DriftInjector(0.25, seed=7)
    fact = find_fact("f001")
    seq_a = [a.transform("The capital of France is Paris.", fact) for _ in range(20)]
    seq_b = [b.transform("The capital of France is Paris.", fact) for _ in range(20)]
    assert seq_a == seq_b


def test_dataset_sha_deterministic():
    assert dataset_sha256() == dataset_sha256()
    assert len(dataset_sha256()) == 64


def test_run_depth_deterministic():
    r1 = md_run.run_depth(3, 0.25, seed=0, critic_mode="perfect")
    r2 = md_run.run_depth(3, 0.25, seed=0, critic_mode="perfect")
    assert r1["hallucination_rate"] == r2["hallucination_rate"]
    assert r1["served_error_rate"] == r2["served_error_rate"]
    assert r1["per_fact"] == r2["per_fact"]


def test_perfect_critic_serves_nothing_hallucinated():
    for depth in (1, 3, 5):
        r = md_run.run_depth(depth, 0.25, seed=0, critic_mode="perfect")
        assert r["served_error_rate"] == 0.0  # decision matrix catches 100% by construction


def test_empty_critic_serves_everything_hallucinated():
    for depth in (1, 3, 5):
        r = md_run.run_depth(depth, 0.25, seed=0, critic_mode="empty")
        if r["n_hallucinated"] > 0:
            assert r["served_error_rate"] == 1.0  # useless critic serves all hallucinated


def test_hallucination_grows_with_depth():
    d1 = md_run.run_depth(1, 0.25, seed=0, critic_mode="perfect")["hallucination_rate"]
    d5 = md_run.run_depth(5, 0.25, seed=0, critic_mode="perfect")["hallucination_rate"]
    assert d5 > d1


def test_preregistration_precedes_results():
    """The methodology file exists and the committed results carry a matching dataset hash."""
    prereg = (
        Path(__file__).resolve().parent.parent
        / "experiments"
        / "model_drift"
        / "PREREGISTRATION.md"
    )
    assert prereg.exists()
    results = (
        Path(__file__).resolve().parent.parent
        / "experiments"
        / "model_drift"
        / "results"
        / "results.json"
    )
    assert results.exists()
    record = json.loads(results.read_text())
    assert record["dataset_sha256"] == dataset_sha256()
    assert record["schema_version"] == 1
