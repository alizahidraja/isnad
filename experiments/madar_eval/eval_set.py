"""Curated labeled pairs for calibrating content-level madār detection (#54).

``content_madar.shares_error_with`` / ``detect_content_madar`` flag two
nominally-independent chains that repeat the **same specific error** — a
fingerprint of a common upstream (the classical madār). This set measures how
often the fingerprint is *right* and, more importantly, how often it is
*dangerously wrong*.

Each case is a pair of claims ``(a, b)`` labeled one of:

- ``shared_error`` — ``a`` and ``b`` echo the *same specific mistake* (a wrong
  figure, a wrong entity, a wrong date, repeated near-verbatim). Two genuinely
  independent witnesses do **not** independently make the identical mistake, so
  the detector SHOULD fire. These drive **recall**.

- ``independent_agreement`` — ``a`` and ``b`` state the *same correct fact* in
  different words, and they happen to share a salient token (a number, a name, a
  year). This is what real independent corroboration looks like, and the detector
  MUST NOT fire. A hit here is the **dangerous false positive**: it discounts the
  very agreement corroboration exists to reward. These drive the headline
  **false-positive rate**.

- ``independent_different`` — ``a`` and ``b`` are about different content and
  share no error. A trivial negative; the detector must not fire.

The ``shared_error`` cases are deliberately *diverse* — wrong number, wrong
entity, wrong date, wrong citation, near-paraphrase echo — not a single
word-swap family the fingerprint was written to catch, so recall is honest
rather than circular. The ``independent_agreement`` cases are deliberately
*adversarial*: each shares exactly the kind of token the fingerprint keys on,
so the false-positive number reflects the real hazard, not a strawman.

Pure data — no dependencies, no optional extras. ``content_madar`` is itself
dependency-free, so these numbers are reproducible on base deps alone.
"""

from __future__ import annotations

# (claim_a, claim_b) — two claims arriving via nominally-independent chains.

SHARED_ERROR: list[tuple[str, str]] = [
    # Same wrong figure, different phrasing (a received wrong number).
    (
        "The dataset contains 4,200 labeled records.",
        "There are 4,200 labeled records in the dataset.",
    ),
    # Same wrong magnitude for a physical constant (both wrong the same way).
    (
        "The speed of light is about 300,000 km per hour.",
        "Light travels at roughly 300,000 km per hour in a vacuum.",
    ),
    # Same wrong attribution — identical wrong entity set.
    (
        "The Odyssey was written by Virgil.",
        "Virgil is the author of the Odyssey.",
    ),
    # Same wrong date, different wording (a received wrong year).
    (
        "The Berlin Wall fell in 1991.",
        "1991 was the year the Berlin Wall came down.",
    ),
    # Same wrong citation identifier repeated verbatim.
    (
        "This result is established in arxiv:1706.03762 on convolutional models.",
        "See arxiv:1706.03762, which proves the convolutional result.",
    ),
    # Near-verbatim echo of a distinctive wrong sentence (copied upstream).
    (
        "The enzyme denatures irreversibly at exactly 37 degrees Celsius.",
        "At exactly 37 degrees Celsius the enzyme denatures irreversibly.",
    ),
    # Same wrong number+unit pair (a received wrong dosage).
    (
        "The recommended dose is 500 mg taken twice daily.",
        "Patients should take 500 mg of it twice daily as recommended.",
    ),
    # Same wrong negation about the same subject (shared received denial).
    (
        "Pluto is not a planet and has no moons.",
        "Pluto has no moons; it is not a planet.",
    ),
]

INDEPENDENT_AGREEMENT: list[tuple[str, str]] = [
    # Two correct, independent witnesses that share the correct year.
    (
        "Newton published the Principia in 1687.",
        "The Principia first appeared in 1687.",
    ),
    # Same correct count, genuinely independent restatement.
    (
        "The committee has 9 members.",
        "There are 9 people on the committee.",
    ),
    # Same correct entity, different fact framing — a shared subject is NOT a
    # shared error.
    (
        "Einstein developed the theory of general relativity.",
        "General relativity was formulated by Einstein.",
    ),
    # Correct shared constant, different phrasing.
    (
        "Water boils at 100 degrees Celsius at sea level.",
        "At sea level, the boiling point of water is 100 degrees Celsius.",
    ),
    # Correct shared citation — two chains legitimately pointing at the same real
    # source is corroboration, not madār.
    (
        "The transformer architecture is introduced in arxiv:1706.03762.",
        "arxiv:1706.03762 is the paper that introduced transformers.",
    ),
    # Correct shared number+unit (a real, agreed measurement).
    (
        "The marathon distance is 42 km.",
        "A marathon covers 42 km.",
    ),
    # Correct shared negation — both correctly deny the same false thing.
    (
        "The sun is not a planet.",
        "The sun is not a planet; it is a star.",
    ),
    # Correct shared date via different formats.
    (
        "The mission launched on 1969-07-16.",
        "Launch occurred on 1969-07-16.",
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

# label -> list of (a, b) pairs; the label is the ground truth.
LABELED: list[tuple[str, str, str]] = (
    [("shared_error", a, b) for a, b in SHARED_ERROR]
    + [("independent_agreement", a, b) for a, b in INDEPENDENT_AGREEMENT]
    + [("independent_different", a, b) for a, b in INDEPENDENT_DIFFERENT]
)


def all_cases() -> list[tuple[str, str, str]]:
    """Return every labeled (label, claim_a, claim_b) triple."""
    return list(LABELED)
