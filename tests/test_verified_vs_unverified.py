"""Tests for the verified-vs-unverified A/B demonstration.

These lock in the DEMONSTRATION's behavior — that the six scenarios produce
exactly the caught/missed split the README claims, and that the ground-truth
firewall holds (grading never imports ground truth).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EXP_DIR = Path(__file__).resolve().parent.parent / "experiments" / "verified_vs_unverified"
RUN_PY = EXP_DIR / "run.py"


def _run() -> str:
    result = subprocess.run(
        [sys.executable, str(RUN_PY)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"run.py failed:\n{result.stderr}"
    return result.stdout


@pytest.fixture(scope="module")
def output() -> str:
    return _run()


def test_demo_runs_and_produces_summary(output: str):
    assert "SUMMARY" in output
    assert "scenarios:          6" in output
    assert "false positives:    0" in output


def test_correct_caught_missed_split(output: str):
    """The honest split: 2 caught, 2 missed, 0 false positives."""
    assert "caught:             2" in output
    assert "missed:             2" in output


def test_scenario_b_is_caught(output: str):
    """Weak-narrator corruption must be caught."""
    b_section = output.split("[B-weak-narrator]")[1].split("\n\n")[0]
    assert "CAUGHT" in b_section


def test_scenario_c_is_missed(output: str):
    """Stale-grade drift must be honestly reported as missed (issue #4)."""
    c_section = output.split("[C-stale-grade]")[1].split("\n\n")[0]
    assert "MISSED" in c_section
    assert "stale-grade" in c_section


def test_scenario_d_is_missed(output: str):
    """Fabricated-clean-chain must be honestly reported as missed (issue #11)."""
    d_section = output.split("[D-fabricated-source]")[1].split("\n\n")[0]
    assert "MISSED" in d_section
    assert "fabricated-clean-chain" in d_section


def test_scenario_e_is_recovered_by_corroboration(output: str):
    """Corroboration must upgrade the DAIF chain (not a false positive)."""
    e_section = output.split("[E-corroboration]")[1].split("\n\n")[0]
    assert "corroborated grade=hasan" in e_section
    assert "FALSE +VE" not in e_section


def test_scenario_f_is_caught_via_ilal(output: str):
    """Sound chain + contradicted content must route to review (caught)."""
    f_section = output.split("[F-ilal]")[1].split("\n\n")[0]
    assert "CAUGHT" in f_section
    assert "action=review" in f_section


def test_ground_truth_firewall():
    """The grading modules must not import the ground-truth fixtures.

    This is the same firewall discipline as §8: grading/gating code never
    sees the injection manifest.  The only module that imports fixtures is
    run.py (the reporter).  We verify the core grading modules don't.
    """
    import isnad.core.grading as grading
    import isnad.core.registry as registry
    import isnad.core.decision as decision

    for mod in (grading, registry, decision):
        src = Path(mod.__file__).read_text()
        assert "fixtures" not in src, (
            f"{mod.__name__} imports the ground-truth fixtures — firewall broken"
        )
