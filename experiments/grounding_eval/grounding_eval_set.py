"""Curated labeled cases for measuring the chain-grounding policy's FP rate (#239).

The `ChainScopedGroundingPolicy` flags a claim as `grounded_off_chain_only` when it
is CONSISTENT against off-chain rows but UNVERIFIABLE against its own chain's rows.
This set measures that flag's recall (on true off-chain grounding) and its
false-positive rate (on claims that MUST NOT be flagged), driven by a real
semantic critic.

Each case is `(claim_text, on_chain_rows, off_chain_rows)` labeled one of:

- `grounded_off_chain_only` — the claim is supported ONLY off-chain (positive;
  the policy SHOULD flag).
- `grounded_on_chain` — the claim is supported on its own chain (negative; MUST
  NOT flag — the headline FP denominator).
- `grounded_nowhere` — the claim is supported nowhere (negative; MUST NOT flag).
- `on_chain_contradiction` — the claim is contradicted by its own chain (negative;
  MUST NOT flag — a live contradiction dominates).

Pure data; the real `LocalNLICritic` (nli extra) supplies the verdicts.
"""

from __future__ import annotations

Case = tuple[str, str, list[str], list[str]]  # (label, claim, on_chain_rows, off_chain_rows)


def _c(label: str, claim: str, on_chain: list[str], off_chain: list[str]) -> Case:
    return (label, claim, on_chain, off_chain)


CASES: list[Case] = [
    # --- grounded_off_chain_only (positive: SHOULD flag) ---
    _c(
        "grounded_off_chain_only",
        "Paris is the capital of France.",
        [],
        ["Paris is the capital of France."],
    ),
    _c(
        "grounded_off_chain_only",
        "Water freezes at 0 degrees Celsius.",
        [],
        ["Water freezes at 0 degrees Celsius at standard pressure."],
    ),
    _c(
        "grounded_off_chain_only",
        "The Moon orbits the Earth.",
        [],
        ["The Moon revolves around the Earth."],
    ),
    # --- grounded_on_chain (negative: MUST NOT flag) ---
    _c(
        "grounded_on_chain",
        "Paris is the capital of France.",
        ["Paris is the capital of France."],
        ["Paris is the capital of France."],
    ),
    _c(
        "grounded_on_chain",
        "Water freezes at 0 degrees Celsius.",
        ["Water freezes at 0 degrees Celsius."],
        [],
    ),
    _c("grounded_on_chain", "The Moon orbits the Earth.", ["The Moon orbits the Earth."], []),
    # --- grounded_nowhere (negative: MUST NOT flag) ---
    _c(
        "grounded_nowhere",
        "The Moon is made of green cheese.",
        ["Paris is the capital of France."],
        ["Water freezes at 0 degrees Celsius."],
    ),
    _c("grounded_nowhere", "A novel claim about an unverifiable private event.", [], []),
    # --- on_chain_contradiction (negative: MUST NOT flag) ---
    _c(
        "on_chain_contradiction",
        "Paris is the capital of Germany.",
        ["Paris is the capital of France."],
        ["Paris is the capital of Germany."],
    ),
    _c(
        "on_chain_contradiction",
        "Water freezes at 10 degrees Celsius.",
        ["Water freezes at 0 degrees Celsius."],
        ["Water freezes at 10 degrees Celsius."],
    ),
]


def all_cases() -> list[Case]:
    """Return every labeled (label, claim, on_chain_rows, off_chain_rows) case."""
    return list(CASES)
