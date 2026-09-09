"""Regression test for the chain-grounding eval harness (#239) — non-CI (nli).

Pins the eval-set hash and the honesty invariants: the FP denominator is non-empty,
the contradiction-only EmbeddingCritic fires 0 flags (by construction), and the
real LocalNLICritic(gate_affirmation=False) emits at least one CONSISTENT verdict
(no silent FP=0-by-construction). Runs only under `-m nli` (needs the nli extra).

Modules are loaded under UNIQUE names via importlib to avoid the pytest
`sys.modules` `run`/`eval_set` collision (same guard as tests/test_madar_eval.py).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.nli

_EVAL_DIR = Path(__file__).resolve().parent.parent / "experiments" / "grounding_eval"

_COMMITTED_EVAL_SET_SHA256 = "2fed84b7c65eccb4a4a8e190ed1b5a20ff964ab4f5ba9c18486533430f649014"


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_set = _load("grounding_eval_set", _EVAL_DIR / "grounding_eval_set.py")
_run = _load("_isnad_grounding_eval_run", _EVAL_DIR / "run.py")


def test_eval_set_hash_pinned():
    cases = _set.all_cases()
    assert _run._eval_set_sha256(cases) == _COMMITTED_EVAL_SET_SHA256
    assert len(_run._eval_set_sha256(cases)) == 64


def test_fp_denominator_non_empty():
    cases = _set.all_cases()
    negatives = [
        c
        for c in cases
        if c[0] in ("grounded_on_chain", "grounded_nowhere", "on_chain_contradiction")
    ]
    assert len(negatives) >= 1


def test_embedding_critic_fires_zero_by_construction():
    from isnad.critics.embedding import EmbeddingCritic
    from isnad.types import ContentVerdict

    rows = _run._run(EmbeddingCritic())
    flags = sum(1 for r in rows if r[1])
    assert flags == 0  # contradiction-only critic can never affirm CONSISTENT
    assert all(
        r[2] is not ContentVerdict.CONSISTENT for r in rows if r[0] == "grounded_off_chain_only"
    )


def test_nli_critic_emits_consistent():
    from isnad.critics.nli import LocalNLICritic
    from isnad.types import ContentVerdict

    critic = LocalNLICritic(gate_affirmation=False)
    rows = _run._run(critic)
    positives = [r for r in rows if r[0] == "grounded_off_chain_only"]
    n_consistent = sum(1 for r in positives if r[2] is ContentVerdict.CONSISTENT)
    assert n_consistent >= 1  # the degeneracy guard must not trip
