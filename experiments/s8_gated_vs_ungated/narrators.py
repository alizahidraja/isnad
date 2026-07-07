"""Narrator roster and fault injection classes for the §8 experiment.

Defines the four narrator variants with designed reliability tiers and
rule-based fault classes that deterministically corrupt claims.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field


# ===========================================================================
# Fault classes — rule-based, deterministic given seed
# ===========================================================================


def _maybe(rate: float, rng: random.Random) -> bool:
    return rng.random() < rate


def apply_ocr_noise(text: str, rng: random.Random) -> str:
    """Light OCR noise: character substitutions, whitespace glitches."""
    subs = {"l": "1", "I": "1", "O": "0", "rn": "m", "c1": "d"}
    for orig, repl in subs.items():
        if orig in text and _maybe(0.5, rng):
            text = text.replace(orig, repl, 1)
    return text


def apply_negation_drop(text: str, rng: random.Random) -> str:
    """Drop key negation words: 'not', 'never', 'no'."""
    negations = [r"\bnot\b", r"\bnever\b"]
    for pattern in negations:
        if re.search(pattern, text) and _maybe(0.5, rng):
            text = re.sub(pattern, "", text, count=1)
    return text


def apply_digit_swap(text: str, rng: random.Random) -> str:
    """Swap adjacent digits: 42 → 24."""
    digits = re.findall(r"\d{2,}", text)
    for d in digits:
        if len(d) >= 2 and _maybe(0.5, rng):
            i = rng.randint(0, len(d) - 2)
            swapped = d[:i] + d[i + 1] + d[i] + d[i + 2 :]
            text = text.replace(d, swapped, 1)
    return text


def apply_unit_corruption(text: str, rng: random.Random) -> str:
    """Corrupt units: J→kJ, m→km, m/s→m/s²."""
    unit_subs = [
        (" J", " kJ"),
        (" m/s", " m/s²"),
        (" N", " kN"),
        (" W", " kW"),
    ]
    for orig, repl in unit_subs:
        if orig in text and _maybe(0.4, rng):
            text = text.replace(orig, repl, 1)
    return text


def apply_formula_mangling(text: str, rng: random.Random) -> str:
    """Mangle formula symbols: swap operators, drop squares."""
    manglings = [
        (r"\b(v\^2)\b", "v"),
        (r"\b(r\^2)\b", "r"),
        (r"\b(1/2)\b", "2"),
    ]
    for pattern, repl in manglings:
        if re.search(pattern, text) and _maybe(0.4, rng):
            text = re.sub(pattern, repl, text, count=1)
    return text


def apply_entity_swap(text: str, rng: random.Random) -> str:
    """Swap physics entities: electron↔proton, increases↔decreases."""
    swaps = [
        ("electron", "proton"),
        ("proton", "electron"),
        ("increases", "decreases"),
        ("decreases", "increases"),
        ("attractive", "repulsive"),
        ("repulsive", "attractive"),
        ("positive", "negative"),
        ("negative", "positive"),
    ]
    for a, b in swaps:
        if a in text.lower() and _maybe(0.3, rng):
            # Use case-insensitive replacement
            pattern = re.compile(re.escape(a), re.IGNORECASE)
            text = pattern.sub(b, text, count=1)
    return text


def apply_sign_flip(text: str, rng: random.Random) -> str:
    """Flip signs and directions."""
    flips = [
        (r"\b(acceleration due to gravity)\b", "acceleration due to gravity (upward)"),
    ]
    for pattern, repl in flips:
        if re.search(pattern, text) and _maybe(0.3, rng):
            text = re.sub(pattern, repl, text, count=1)

    # Flip mathematical signs
    if _maybe(0.2, rng):
        text = text.replace(" + ", " − ", 1)
    return text


def apply_fabricated_numeric(text: str, rng: random.Random) -> str:
    """Replace a numeric value with a plausible-but-wrong one."""
    numbers = re.findall(r"\d+\.?\d*(?:\s*×\s*10\^?[−\-]?\d+)?", text)
    for num in numbers:
        if _maybe(0.3, rng):
            try:
                val = float(num.replace("×", "e").replace(" ", "").replace("^", ""))
                perturbed = val * rng.uniform(0.5, 1.5)
                new_str = f"{perturbed:.3g}"
                text = text.replace(num, new_str, 1)
            except ValueError:
                pass
    return text


def apply_regime_confusion(text: str, rng: random.Random) -> str:
    """Confuse classical and quantum regime language."""
    confusions = [
        ("classical", "quantum"),
        ("quantum", "classical"),
        ("Newtonian", "relativistic"),
        ("relativistic", "Newtonian"),
    ]
    for a, b in confusions:
        if a.lower() in text.lower() and _maybe(0.3, rng):
            pattern = re.compile(re.escape(a), re.IGNORECASE)
            text = pattern.sub(b, text, count=1)
    return text


def apply_truncation(text: str, rng: random.Random) -> str:
    """Truncate text mid-sentence."""
    if _maybe(0.5, rng) and len(text) > 30:
        cut = rng.randint(len(text) // 2, len(text) - 5)
        text = text[:cut]
    return text


# ===========================================================================
# Narrator definitions
# ===========================================================================


@dataclass
class NarratorVariant:
    narrator_id: str
    narrator_type: str  # "destructive" or "generative"
    fault_rate: float
    fault_classes: list[str] = field(default_factory=list)

    def apply_faults(self, text: str, rng: random.Random) -> tuple[str, str]:
        """Apply faults to text. Returns (corrupted_text, fault_type_or_none)."""
        applied = "none"
        for fc in self.fault_classes:
            if _maybe(self.fault_rate / max(1, len(self.fault_classes)), rng):
                func = FAULT_REGISTRY[fc]
                text = func(text, rng)
                if applied == "none":
                    applied = fc
        return text, applied


# Registry of fault functions by name
FAULT_REGISTRY: dict[str, callable] = {
    "ocr_noise": apply_ocr_noise,
    "negation_drop": apply_negation_drop,
    "digit_swap": apply_digit_swap,
    "unit_corruption": apply_unit_corruption,
    "formula_mangling": apply_formula_mangling,
    "entity_swap": apply_entity_swap,
    "sign_flip": apply_sign_flip,
    "fabricated_numeric": apply_fabricated_numeric,
    "regime_confusion": apply_regime_confusion,
    "truncation": apply_truncation,
}

# Narrator variants — as specified in config.yaml
NARRATOR_VARIANTS: dict[str, NarratorVariant] = {
    "pdf-scraper@1.2": NarratorVariant(
        narrator_id="pdf-scraper@1.2",
        narrator_type="destructive",
        fault_rate=0.01,
        fault_classes=["ocr_noise"],
    ),
    "pdf-scraper@0.9-legacy": NarratorVariant(
        narrator_id="pdf-scraper@0.9-legacy",
        narrator_type="destructive",
        fault_rate=0.18,
        fault_classes=[
            "ocr_noise", "negation_drop", "digit_swap",
            "unit_corruption", "formula_mangling", "truncation",
        ],
    ),
    "ingest@good": NarratorVariant(
        narrator_id="ingest@good",
        narrator_type="generative",
        fault_rate=0.02,
        fault_classes=["entity_swap"],
    ),
    "ingest@weak": NarratorVariant(
        narrator_id="ingest@weak",
        narrator_type="generative",
        fault_rate=0.15,
        fault_classes=[
            "entity_swap", "sign_flip", "fabricated_numeric",
            "regime_confusion",
        ],
    ),
}

SCRAPER_VARIANTS = ["pdf-scraper@1.2"]  # Only the reliable scraper for this experiment
INGEST_VARIANTS = ["ingest@good", "ingest@weak"]
