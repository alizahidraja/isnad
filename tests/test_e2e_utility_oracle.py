"""Tests for the e2e-utility oracle (#128).

The ground-truth oracle must be deterministic and independent of the content
critic — these tests lock that down so the experiment's served-error numbers
cannot silently drift from a broken oracle.

NOTE: the LLM generation path is NOT tested here (it needs a live key); these
tests cover the deterministic labelling, which is the part that makes the
experiment's numbers meaningful.
"""

from __future__ import annotations

import importlib.util
import os


# Load the experiment module under a UNIQUE name (see test_two_axis_ablation.py
# for why: both experiments ship a run.py, and bare `from run import` collides).
def _load(module_name: str, path: str):
    import sys

    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec so any @dataclass decorators can find their module.
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_exp_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments", "e2e_utility"
)
_run = _load("_isnad_e2e_utility_run", os.path.join(_exp_dir, "run.py"))

label_claim = _run.label_claim


def test_correct_restatements_are_labelled_correct() -> None:
    """Paraphrases of in-corpus facts must be recognised as correct."""
    correct = [
        "The speed of light in a vacuum is exactly 299,792,458 meters per second.",
        "light travels through empty space at roughly 300 million metres per second",
        "Newton's second law states the net force equals the product of mass and acceleration.",
        "Energy can neither be created nor destroyed, only transformed.",
        "In any isolated system, the total energy remains constant over time.",
        "The momentum of a photon is p = h/λ.",
        "water freezes at zero degrees celsius",
    ]
    for claim in correct:
        assert label_claim(claim), f"should be correct: {claim!r}"


def test_novel_and_hallucinated_claims_are_labelled_incorrect() -> None:
    """Out-of-corpus and hallucinated claims must be labelled incorrect."""
    incorrect = [
        "The melting point of tungsten is 3422 degrees Celsius.",
        "Francium-223 has a half-life of 22 minutes.",
        "the speed of light in a vacuum is five hundred million meters per second",
        "the acceleration due to gravity on earth is 20 meters per second squared",
        "The viscosity of liquid helium-4 at 1 kelvin is 1.2 micropascal-seconds.",
    ]
    for claim in incorrect:
        assert not label_claim(claim), f"should be incorrect: {claim!r}"


def test_oracle_is_not_the_critic() -> None:
    """Sanity: the oracle recognises a fact the word-overlap critic would miss."""
    # 'neither created nor destroyed' is a true conservation statement; the
    # oracle must recognise it even though it shares no wording with 'conserved'.
    assert label_claim("energy can neither be created nor destroyed")
