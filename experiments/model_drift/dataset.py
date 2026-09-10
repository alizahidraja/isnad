"""Model-drift leaderboard dataset (#71): fixed fact corpus + chain templates + drift injector.

The fact corpus is a fixed set of ground-truth assertions, each with a canonical
(subject, correct_value) pair and a small set of deterministic *wrong* values that the
offline drift-injector substitutes to simulate hallucination. This keeps the offline
mode reproducible and the oracle deterministic and non-circular (it reads the corpus,
never the critic under test).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from isnad.types import TransformType


@dataclass(frozen=True)
class Fact:
    fact_id: str
    assertion: str
    subject: str  # the canonical subject key, e.g. "capital of France"
    correct_value: str  # the ground-truth value, e.g. "Paris"
    wrong_values: tuple[str, ...]  # deterministic corruption values for offline drift
    domain: str


# A small seed corpus across domains. Each wrong value is a plausible-but-false
# substitution the drift injector uses, so the oracle can deterministically detect it.
FACT_CORPUS: tuple[Fact, ...] = (
    Fact(
        "f001",
        "The capital of France is Paris.",
        "capital of France",
        "Paris",
        ("London", "Berlin", "Rome"),
        "geography",
    ),
    Fact(
        "f002",
        "The capital of Japan is Tokyo.",
        "capital of Japan",
        "Tokyo",
        ("Osaka", "Kyoto", "Seoul"),
        "geography",
    ),
    Fact(
        "f003",
        "Water boils at 100 degrees Celsius at sea level.",
        "boiling point of water",
        "100",
        ("90", "110", "212"),
        "physics",
    ),
    Fact(
        "f004",
        "The speed of light is about 300,000 km per second.",
        "speed of light",
        "300,000",
        ("150,000", "600,000", "30,000"),
        "physics",
    ),
    Fact(
        "f005",
        "The Earth orbits the Sun.",
        "center of Earth's orbit",
        "Sun",
        ("Moon", "Mars", "Venus"),
        "astronomy",
    ),
    Fact(
        "f006",
        "The Moon orbits the Earth.",
        "center of Moon's orbit",
        "Earth",
        ("Sun", "Mars", "Jupiter"),
        "astronomy",
    ),
    Fact(
        "f007",
        "World War II ended in 1945.",
        "WWII end year",
        "1945",
        ("1944", "1946", "1918"),
        "history",
    ),
    Fact(
        "f008",
        "The Berlin Wall fell in 1989.",
        "Berlin Wall fall year",
        "1989",
        ("1987", "1991", "1961"),
        "history",
    ),
    Fact(
        "f009",
        "Humans have 23 pairs of chromosomes.",
        "human chromosome pairs",
        "23",
        ("24", "46", "22"),
        "biology",
    ),
    Fact(
        "f010",
        "The mitochondria is the powerhouse of the cell.",
        "cell powerhouse",
        "mitochondria",
        ("nucleus", "ribosome", "chloroplast"),
        "biology",
    ),
    Fact("f011", "Water is H2O.", "water formula", "H2O", ("CO2", "O2", "NaCl"), "chemistry"),
    Fact(
        "f012",
        "The chemical symbol for gold is Au.",
        "gold symbol",
        "Au",
        ("Ag", "Fe", "Go"),
        "chemistry",
    ),
)


# Chain template: a tuple of (agent_name, TransformType) per depth.
# depth d means the claim passes through d agents in this fixed order.
_AGENTS: tuple[tuple[str, TransformType], ...] = (
    ("retriever", TransformType.PASS_THROUGH),
    ("synthesis", TransformType.GENERATIVE),
    ("critic", TransformType.GENERATIVE),
    ("re-synthesis", TransformType.GENERATIVE),
    ("summarizer", TransformType.DESTRUCTIVE),
)


def chain_template(depth: int) -> tuple[tuple[str, TransformType], ...]:
    """The fixed multi-agent topology for a given depth (1..5)."""
    if depth < 1 or depth > len(_AGENTS):
        raise ValueError(f"depth must be in 1..{len(_AGENTS)}")
    return _AGENTS[:depth]


def dataset_sha256() -> str:
    """Deterministic hash of the corpus + templates — the reproducibility pin."""
    payload = json.dumps(
        [
            {
                "fact_id": f.fact_id,
                "assertion": f.assertion,
                "subject": f.subject,
                "correct_value": f.correct_value,
                "wrong_values": list(f.wrong_values),
                "domain": f.domain,
            }
            for f in FACT_CORPUS
        ]
        + [[a[0], a[1].value] for a in _AGENTS],
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class DriftInjector:
    """Deterministic offline model stand-in: corrupts a claim's value with a fixed
    per-hop probability, seeded so runs are byte-reproducible.

    This is NOT a real model — it is the offline-mode mechanism that makes the
    *pipeline* measurable without API keys. Real-model runs are a separate, keyed,
    live phase; their cells render "not run" in offline results.
    """

    def __init__(self, corruption_probability: float, seed: int):
        if not 0.0 <= corruption_probability <= 1.0:
            raise ValueError("corruption_probability must be in [0, 1]")
        self.p = corruption_probability
        self._state = (seed + 0x9E3779B9) & 0xFFFFFFFF

    def _rand(self) -> int:
        # xorshift32: a deterministic, seeded PRNG stream.
        x = self._state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self._state = x
        return x

    def transform(self, claim: str, fact: Fact) -> str:
        """Return the claim this hop emits: unchanged, or corrupted in place."""
        if (self._rand() / 0xFFFFFFFF) < self.p:
            idx = self._rand() % len(fact.wrong_values)
            wrong = fact.wrong_values[idx]
            if fact.correct_value in claim:
                return claim.replace(fact.correct_value, wrong, 1)
        return claim
