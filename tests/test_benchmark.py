"""Pins the adversarial benchmark's *honest* invariants (issue #50).

The benchmark's value is that it does not flatter ISNAD.  These tests assert the
shape of the truth, not a fixed score, so the benchmark can never silently
regress into over-claiming:

- the chain-grading signal (weak narrator) is caught 100% of the time;
- good claims are never falsely flagged (0 false positives);
- the content critic is the binding constraint — it misses semantic
  contradictions, so overall recall is *not* 100%.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_BENCH = _REPO / "experiments" / "adversarial_benchmark" / "run.py"


def _load_benchmark():
    import sys

    spec = importlib.util.spec_from_file_location("adversarial_benchmark", _BENCH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod.__name__] = mod  # so string annotations resolve
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _run():
    mod = _load_benchmark()
    reg = mod.Registry()
    for nid, (grade, ntype) in mod.NARRATORS.items():
        reg.register(nid, "physics", grade=grade, narrator_type=ntype)
    critic = mod.DeterministicRuleCritic()
    cases = mod._build_cases()
    results = [mod._run_case(c, reg, critic) for c in cases]

    by_kind: dict[str, dict[str, int]] = {}
    for case, r in zip(cases, results, strict=True):
        k = by_kind.setdefault(case.kind, {"tp": 0, "fn": 0, "tn": 0, "fp": 0})
        if case.good:
            k["tn" if r.served else "fp"] += 1
        else:
            k["tp" if r.caught else "fn"] += 1
    return by_kind


@pytest.fixture(scope="module")
def by_kind():
    return _run()


class TestBenchmarkIsHonest:
    def test_weak_narrators_are_always_caught(self, by_kind):
        k = by_kind["weak-narrator"]
        assert k["tp"] == 10 and k["fn"] == 0

    def test_no_false_positives_on_good_claims(self, by_kind):
        k = by_kind["good"]
        assert k["fp"] == 0 and k["tn"] == 20

    def test_semantic_contradictions_are_mostly_missed(self, by_kind):
        """The critic is word-overlap only — this is the honest gap (#34)."""
        k = by_kind["content-contradiction"]
        assert k["fn"] > k["tp"]

    def test_overall_recall_is_not_perfect(self, by_kind):
        tp = sum(v["tp"] for v in by_kind.values())
        fn = sum(v["fn"] for v in by_kind.values())
        assert tp > 0 and fn > 0  # catches some, misses some — never 100%
