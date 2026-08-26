"""Curated labeled eval set for ISNAD content critics (issue #96).

A small but *genuine* physics corpus plus hand-labeled claim cases. Each case is
labeled one of:

- ``consistent`` — the claim states a fact the corpus asserts (verbatim or a
  light paraphrase). A critic should NOT flag it as a contradiction.
- ``contradiction`` — the claim asserts something that conflicts with a corpus
  fact (negation, opposite, wrong magnitude, regime confusion). A critic SHOULD
  flag it as a contradiction.
- ``unrelated`` — the claim is from another domain entirely; the corpus has no
  information about it. The correct verdict is UNVERIFIABLE, and neither
  CONSISTENT nor CONTRADICTION is defensible.

Unlike the earlier template-injected set (negation word-swaps the critics were
written to catch), these contradictions are *diverse*: wrong relationships,
wrong magnitudes, regime mismatches, and subtle wording. That makes the recall
numbers honest rather than circular.

The primary metric is **contradiction detection** (does the critic catch a claim
that conflicts with the corpus), with the **false-consistent rate** (a
contradiction mislabeled CONSISTENT) reported separately as the dangerous error.
"""

from __future__ import annotations

# Ground-truth physics facts — the "knowledge base" every critic is evaluated
# against. Kept modest so the NLI/LLM critics stay fast (top-k retrieval + a
# model call per case).
CORPUS: list[str] = [
    "force equals mass times acceleration",
    "the momentum of a photon is p = h/lambda",
    "momentum is the product of mass and velocity",
    "energy is conserved in an isolated system",
    "the speed of light in a vacuum is about three hundred million meters per second",
    "the entropy of an isolated system never decreases",
    "electrons carry a negative electric charge",
    "gravity between two masses is always attractive",
    "pressure is force per unit area",
    "work is force times displacement in the direction of the force",
    "power is the rate at which work is done",
    "temperature is a measure of the average kinetic energy of particles",
    "an object in motion stays in motion unless acted on by a net force",
    "acceleration is the rate of change of velocity",
    "the electric field points away from a positive charge",
    "light behaves as both a particle and a wave",
    "the nucleus of an atom contains protons and neutrons",
    "electric charge is conserved in an isolated system",
    "the wavelength of light is inversely proportional to its frequency",
    "heat flows spontaneously from hot objects to cold objects",
    "the pressure of a gas decreases as its volume increases at constant temperature",
    "sound cannot travel through a vacuum",
    "the gravitational acceleration near the earth's surface is about nine point eight meters per second squared",
    "electric current is the flow of electric charge",
    "resistance opposes the flow of electric current",
    "a moving charged particle experiences a force in a magnetic field",
    "the energy of a photon is proportional to its frequency",
    "kinetic energy is proportional to the square of velocity",
    "the total momentum of a closed system is conserved",
    "water freezes at zero degrees celsius",
]

# (claim, label) — the eval cases. CONSISTENT cases are verbatim or near-paraphrases.
CONSISTENT_CASES: list[tuple[str, str]] = [
    ("force equals mass times acceleration", "consistent"),
    ("the momentum of a photon is p = h/lambda", "consistent"),
    ("momentum is the product of mass and velocity", "consistent"),
    ("energy is conserved in an isolated system", "consistent"),
    ("electrons carry a negative electric charge", "consistent"),
    ("gravity between two masses is always attractive", "consistent"),
    ("pressure is force per unit area", "consistent"),
    ("power is the rate at which work is done", "consistent"),
    ("an object in motion stays in motion unless acted on by a net force", "consistent"),
    ("light behaves as both a particle and a wave", "consistent"),
    ("sound cannot travel through a vacuum", "consistent"),
    ("electric current is the flow of electric charge", "consistent"),
    ("kinetic energy is proportional to the square of velocity", "consistent"),
    ("the total momentum of a closed system is conserved", "consistent"),
    ("water freezes at zero degrees celsius", "consistent"),
    # Light paraphrases — same fact, different wording.
    ("the net force on an object equals its mass multiplied by its acceleration", "consistent"),
    ("a photon's momentum is given by planck's constant divided by its wavelength", "consistent"),
    ("in an isolated system the total energy does not change", "consistent"),
    ("photons with higher frequency carry more energy", "consistent"),
    ("the pressure of an ideal gas drops when its volume grows at fixed temperature", "consistent"),
]

# Genuine contradictions — wrong relationship, wrong magnitude, negation, regime
# confusion. These are NOT the word-swaps the reference critic was built to catch.
CONTRADICTION_CASES: list[tuple[str, str]] = [
    ("force equals acceleration divided by mass", "contradiction"),  # F = a/m, wrong
    ("force is the product of mass and acceleration squared", "contradiction"),
    ("the momentum of a photon is p = m v", "contradiction"),  # photon momentum isn't mv
    ("momentum is mass divided by velocity", "contradiction"),
    ("energy can be created from nothing in an isolated system", "contradiction"),
    ("the entropy of an isolated system always decreases", "contradiction"),
    ("electrons carry a positive electric charge", "contradiction"),
    ("gravity between two masses is always repulsive", "contradiction"),
    ("pressure is force times area", "contradiction"),
    ("power is work divided by time squared", "contradiction"),
    ("an object at rest tends to accelerate without any force", "contradiction"),
    ("acceleration is the integral of velocity over time", "contradiction"),
    ("the electric field points toward a positive charge", "contradiction"),
    ("light behaves purely as a particle and never as a wave", "contradiction"),
    ("the nucleus of an atom contains only electrons", "contradiction"),
    ("electric charge can be created or destroyed in an isolated system", "contradiction"),
    ("the wavelength of light is directly proportional to its frequency", "contradiction"),
    ("heat flows spontaneously from cold objects to hot objects", "contradiction"),
    ("sound can travel through a perfect vacuum", "contradiction"),
    ("a stationary charged particle is deflected by a magnetic field", "contradiction"),
    ("the energy of a photon is inversely proportional to its frequency", "contradiction"),
    ("kinetic energy is proportional to velocity, not its square", "contradiction"),
    ("the total momentum of a closed system increases over time", "contradiction"),
    ("water freezes at one hundred degrees celsius", "contradiction"),
    ("the speed of light in a vacuum is infinite", "contradiction"),
]

# Claims the physics corpus knows nothing about — the correct verdict is
# UNVERIFIABLE; calling these CONSISTENT (or CONTRADICTION) is an error.
UNRELATED_CASES: list[tuple[str, str]] = [
    ("the magna carta was signed in the year 1215", "unrelated"),
    ("mitochondria are the powerhouse of the cell", "unrelated"),
    ("the capital of france is paris", "unrelated"),
    ("water is composed of two hydrogen atoms and one oxygen atom", "unrelated"),
    ("the first world war ended in 1918", "unrelated"),
    ("photosynthesis converts carbon dioxide and water into glucose using sunlight", "unrelated"),
    ("shakespeare wrote hamlet", "unrelated"),
    ("the human heart has four chambers", "unrelated"),
    ("democracy originated in ancient athens", "unrelated"),
    ("dna is a double helix", "unrelated"),
    ("the great wall of china is visible from space", "unrelated"),
    ("venus is the second planet from the sun", "unrelated"),
    ("the mongol empire was the largest contiguous land empire in history", "unrelated"),
    ("a haiku traditionally has seventeen syllables", "unrelated"),
    ("the chemical symbol for gold is au", "unrelated"),
]


def all_cases() -> list[tuple[str, str, str]]:
    """Return every labeled case as (claim, label, expected_verdict)."""
    expected = {
        "consistent": "consistent",
        "contradiction": "contradiction",
        "unrelated": "unverifiable",
    }
    out: list[tuple[str, str, str]] = []
    for claim, label in [*CONSISTENT_CASES, *CONTRADICTION_CASES, *UNRELATED_CASES]:
        out.append((claim, label, expected[label]))
    return out
