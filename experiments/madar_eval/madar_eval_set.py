"""Curated labeled cases for calibrating content-level madār detection (#54).

``content_madar.shares_error_with`` / ``detect_content_madar`` flag two
nominally-independent chains that repeat the **same specific error** — a
fingerprint of a common upstream (the classical madār). This set measures how
often the fingerprint is *right* and, more importantly, how often it is
*dangerously wrong*.

Each pair is labeled one of:

- ``shared_error`` — ``a`` and ``b`` echo the *same specific mistake* and share a
  salient token (a wrong figure, entity, date, citation). These drive **recall**
  on the fingerprint's strengths.
- ``shared_error_tokenless`` — the *same specific mistake*, reworded so the two
  phrasings share **no** salient token (number/entity/date/citation/unit). This
  is where recall *honestly fails* — the fingerprint cannot see a reworded error.
- ``independent_agreement`` — the same *correct* fact in different words, sharing
  a salient token. The detector MUST NOT fire. Drives the headline FP.
- ``near_miss_boundary`` — one correct + one wrong claim that share a subject
  token but differ in the specific value (e.g. 1687 vs 1689). MUST NOT fire, but
  the current detector's entity-set-equality rule fires *before* the numbers are
  compared, so these false-positive — a measured defect, disclosed not fixed.
- ``independent_different`` — different content, no shared error. Trivial negative.

N-way (3+ chain) cases exercise ``detect_content_madar(base, verdict,
corroborating)`` with a real multi-claim list, which the pair-only set never
touches.

Pure data — no dependencies. ``content_madar`` is dependency-free, so these
numbers reproduce on base deps alone.
"""

from __future__ import annotations


# Same specific mistake, sharing a salient token (the fingerprint's strength).
SHARED_ERROR: list[tuple[str, str]] = [
    (
        "The human genome contains about 500,000 protein-coding genes.",
        "There are roughly 500,000 protein-coding genes in the human genome.",
    ),
    (
        "The speed of light is about 300,000 km per hour.",
        "Light travels at roughly 300,000 km per hour in a vacuum.",
    ),
    (
        "The Odyssey was written by Virgil.",
        "Virgil is the author of the Odyssey.",
    ),
    (
        "The Berlin Wall fell in 1991.",
        "1991 was the year the Berlin Wall came down.",
    ),
    (
        "This result is established in arxiv:1706.03762 on convolutional models.",
        "See arxiv:1706.03762, which proves the convolutional result.",
    ),
    (
        "The enzyme denatures irreversibly at exactly 37 degrees Celsius.",
        "At exactly 37 degrees Celsius the enzyme denatures irreversibly.",
    ),
    (
        "The recommended single dose of paracetamol is 5000 mg.",
        "Take 5000 mg of paracetamol as a single recommended dose.",
    ),
    (
        "Pluto is not a planet and has no moons.",
        "Pluto has no moons; it is not a planet.",
    ),
]

# Same specific mistake, reworded so NO salient token is shared (recall gap).
TOKENLESS_SHARED_ERROR: list[tuple[str, str]] = [
    (
        "The Moon is larger than the Earth.",
        "A planet is smaller than its orbiting moon.",
    ),
    (
        "Mercury is the hottest planet.",
        "The closest world to the Sun is the warmest.",
    ),
    (
        "The Atlantic is the largest ocean.",
        "The ocean between the Americas and Europe is the biggest.",
    ),
    (
        "Shakespeare wrote the Divine Comedy.",
        "The English playwright authored Dante's epic poem.",
    ),
]

INDEPENDENT_AGREEMENT: list[tuple[str, str]] = [
    (
        "Newton published the Principia in 1687.",
        "The Principia first appeared in 1687.",
    ),
    (
        "The committee has 9 members.",
        "There are 9 people on the committee.",
    ),
    (
        "Einstein developed the theory of general relativity.",
        "General relativity was formulated by Einstein.",
    ),
    (
        "Water boils at 100 degrees Celsius at sea level.",
        "At sea level, the boiling point of water is 100 degrees Celsius.",
    ),
    (
        "The transformer architecture is introduced in arxiv:1706.03762.",
        "arxiv:1706.03762 is the paper that introduced transformers.",
    ),
    (
        "The marathon distance is 42 km.",
        "A marathon covers 42 km.",
    ),
    (
        "The sun is not a planet.",
        "The sun is not a planet; it is a star.",
    ),
    (
        "The mission launched on 1969-07-16.",
        "Launch occurred on 1969-07-16.",
    ),
]

# One correct + one wrong, sharing a subject token but differing in the value.
# The detector MUST NOT fire here; it currently does (entity-equality defect).
NEAR_MISS_BOUNDARY: list[tuple[str, str]] = [
    (
        "Newton published the Principia in 1687.",
        "Newton published the Principia in 1689.",
    ),
    (
        "Water boils at 100 degrees Celsius at sea level.",
        "Water boils at 110 degrees Celsius at sea level.",
    ),
    (
        "The Berlin Wall fell in 1989.",
        "The Berlin Wall fell in 1991.",
    ),
    (
        "The Titanic sank in 1912.",
        "The Titanic sank in 1915.",
    ),
]

INDEPENDENT_DIFFERENT: list[tuple[str, str]] = [
    (
        "The dataset contains 4,200 labeled records.",
        "The model was trained for 12 epochs.",
    ),
    (
        "The Odyssey was written by Homer.",
        "The speed of light is about 300,000 km per second.",
    ),
    (
        "The recommended dose is 500 mg twice daily.",
        "The committee meets on the first Monday of each month.",
    ),
    (
        "Photosynthesis converts light into chemical energy.",
        "The Berlin Wall fell in 1989.",
    ),
]

# N-way (3+ chain) cases: (base_claim, [corroborating claims]).
N_CHAIN_SHARED_ERROR: list[tuple[str, list[str]]] = [
    (
        "The speed of light is about 300,000 km per hour.",
        [
            "Light travels at roughly 300,000 km per hour.",
            "The speed of light is 300,000 km/h.",
        ],
    ),
]

N_CHAIN_NEGATIVE: list[tuple[str, list[str]]] = [
    (
        "The speed of light is about 300,000 km per second.",
        [
            "Light travels at roughly 300,000 km per hour.",
            "The speed of light is 300,000 km/h.",
        ],
    ),
]

LABELED: list[tuple[str, str, str]] = (
    [("shared_error", a, b) for a, b in SHARED_ERROR]
    + [("shared_error_tokenless", a, b) for a, b in TOKENLESS_SHARED_ERROR]
    + [("independent_agreement", a, b) for a, b in INDEPENDENT_AGREEMENT]
    + [("near_miss_boundary", a, b) for a, b in NEAR_MISS_BOUNDARY]
    + [("independent_different", a, b) for a, b in INDEPENDENT_DIFFERENT]
)


def all_cases() -> list[tuple[str, str, str]]:
    """Return every labeled (label, claim_a, claim_b) triple."""
    return list(LABELED)


def n_chain_cases() -> list[tuple[str, str, list[str]]]:
    """Return every N-way (label, base_claim, [corroborating]) case."""
    return [("n_chain_shared_error", b, c) for b, c in N_CHAIN_SHARED_ERROR] + [
        ("n_chain_negative", b, c) for b, c in N_CHAIN_NEGATIVE
    ]
