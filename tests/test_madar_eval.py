"""Regression test for the content-madār calibration harness (#54).

Pins the headline invariants so the committed RESULTS.md numbers cannot silently
drift, and so the *shape* of the result — the gate short-circuits before the raw
fingerprint on CONSISTENT claims — stays true. This does not re-assert exact
rates (those live in RESULTS.md); it asserts the properties that make the
measurement meaningful.

The experiment modules are loaded under UNIQUE names via importlib: every
experiment ships an ``eval_set``/``run``, and a bare ``from run import`` /
``from eval_set import`` collides under pytest's shared process (the first module
of that name imported wins in ``sys.modules``, so this test would silently run
against critic_eval's data). See tests/test_e2e_utility_oracle.py for the same
guard.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent.parent / "experiments" / "madar_eval"


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec so run.py's own `from madar_eval_set import ...` and
    # any @dataclass decorators resolve against the right modules.
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# eval_set must be importable by its own module name (run.py imports it), so load
# it under that exact unique name first, then run.py.
_load("madar_eval_set", _EVAL_DIR / "madar_eval_set.py")
_run = _load("_isnad_madar_eval_run", _EVAL_DIR / "run.py")

all_cases = _run.all_cases
_eval_set_sha256 = _run._eval_set_sha256
_gated_fires = _run._gated_fires
_metrics = _run._metrics
_raw_fires = _run._raw_fires


def _rows():
    cases = all_cases()
    raw = [(label, _raw_fires(a, b)) for label, a, b in cases]
    gated = [(label, _gated_fires(label, a, b)) for label, a, b in cases]
    return _metrics(raw), _metrics(gated)


def test_gate_never_fingerprints_a_consistent_claim():
    """Structural fact (NOT an empirical FP measurement): because the harness
    feeds an oracle verdict from the label, every non-shared-error pair is
    CONSISTENT and detect_content_madar short-circuits before the fingerprint
    runs. So the gated layer fires on no negative pair — by construction of the
    oracle, independent of the fingerprint's behaviour. This test pins that
    short-circuit, not any property of the detector. See run.py::_gated_fires."""
    _raw, gated = _rows()
    assert gated["fp"] == 0
    assert gated["false_positive_rate_agreement"] == 0.0


def test_raw_fingerprint_is_intrinsically_hazardous():
    """The raw fingerprint DOES collide on independent agreement — that hazard is
    the whole reason the gate exists. If this ever drops to zero the eval set has
    gone toothless (no adversarial agreement cases left)."""
    raw, _gated = _rows()
    assert raw["false_positive_rate_agreement"] > 0.0


def test_recall_is_total_on_shared_errors():
    """Both layers catch every genuine shared-error pair."""
    raw, gated = _rows()
    assert raw["recall"] == 1.0
    assert gated["recall"] == 1.0


def test_gated_oracle_row_has_no_worse_precision_than_raw():
    """Under the oracle verdict the gated row makes fewer false positives than the
    raw fingerprint — but this is the oracle short-circuit, not a measured gate
    property (see test_gate_never_fingerprints_a_consistent_claim). Pinned only
    so the two rows don't accidentally invert."""
    raw, gated = _rows()
    assert gated["precision"] >= raw["precision"]
    assert gated["fp"] < raw["fp"]


def test_eval_set_hash_is_stable():
    """The re-runnability pin is deterministic for a fixed eval set."""
    cases = all_cases()
    assert _eval_set_sha256(cases) == _eval_set_sha256(all_cases())
    assert len(_eval_set_sha256(cases)) == 64
