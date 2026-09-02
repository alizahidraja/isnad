"""Regression test for the content-madār calibration harness (#54).

Pins the headline invariants so the committed RESULTS.md numbers cannot silently
drift, and so the *shape* of the result — the gate removes the raw fingerprint's
dangerous false positives — stays true. This does not re-assert exact rates
(those live in RESULTS.md); it asserts the properties that make the measurement
meaningful.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent.parent / "experiments" / "madar_eval"
sys.path.insert(0, str(_EVAL_DIR))

from eval_set import all_cases  # noqa: E402
from run import _eval_set_sha256, _gated_fires, _metrics, _raw_fires  # noqa: E402


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
