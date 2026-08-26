"""Extract self-contained text spans from corpus chunks for the §8 experiment.

Extracts declarative sentences (and formula-bearing spans) from physics textbook
chunks. This is a **deterministic heuristic segmenter + filter** — NOT an LLM
extractor (issue #94).

The previous version had three defects this replaces:

1. It described itself as "simulating LLM extraction" while doing regex splitting.
2. It rewrote every "X is Y" into "X equals Y", which (a) garbled natural
   language ("the glass is sitting" → "the glass equals sitting") and (b) broke
   formula matching against the content critic ("p equals mv" no longer matches
   the critic's "p = mv" pattern — the worked example silently stopped firing).
   The regex also matched "is" *inside* words ("consist" → "cons equals t").
3. It passed multiple-choice answer prefixes, OCR fragments, questions, and
   boilerplate through as "claims".

The honest unit of analysis here is a **sentence-level text span**, not an
"atomic claim" — the experiment validates the transmission-grading mechanics
(synthetic fault injection → weakest-link quarantine → jarḥ–taʿdīl), not claim
semantics. See issue #94 and the paper-v2 tracker (#51).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass


def normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def claim_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


@dataclass
class Claim:
    claim_id: str
    source: str
    chunk: str
    domain: str
    text: str
    normalized: str
    model_confidence: float


# ---------------------------------------------------------------------------
# Junk filters
# ---------------------------------------------------------------------------

# Boilerplate that never constitutes a claim (headers, questions, references).
_BOILERPLATE_RE = re.compile(
    r"^(?:learning objectives|check your understanding|the following|note that|"
    r"figure\s+\d|fig\.?|table\s+\d|example\s+\d|problem\s+\d|exercise\s+\d|"
    r"equation\s+\d|chapter\s+\d|section\s+\d|summary|glossary|key terms|index|"
    r"references|conceptual questions|problems & exercises|additional problems|"
    r"self[- ]check|take-home experiment|simulation|"
    r"solution|strategy|significance|access for free|openstax|lightandmatter)",
    re.IGNORECASE,
)

# Multiple-choice answer prefixes: "A.", "B)", "(c)", "1.", "II.", "D " etc.
_MC_PREFIX_RE = re.compile(
    r"^\s*(?:[a-dA-D][).:]\s*|\([a-dA-D]\)\s*|\d{1,2}[).]\s*|[ivxIVX]{1,4}[).]\s*)"
)
# A lone uppercase answer letter followed by whitespace and a capital letter.
_MC_LONE_LETTER_RE = re.compile(r"^\s*[A-D]\s+(?=[A-Z])")

# Finite verbs / copulas / common physics verbs. A claim must contain one of
# these or a formula. Deliberately broad — this is a junk filter, not a parser.
_VERB_TOKENS = frozenset({
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "has",
    "have",
    "had",
    "does",
    "do",
    "did",
    "can",
    "could",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "equals",
    "equal",
    "produce",
    "produces",
    "describe",
    "describes",
    "measure",
    "measures",
    "depend",
    "depends",
    "increase",
    "increases",
    "decrease",
    "decreases",
    "move",
    "moves",
    "travel",
    "travels",
    "remain",
    "remains",
    "become",
    "becomes",
    "give",
    "gives",
    "show",
    "shows",
    "mean",
    "means",
    "require",
    "requires",
    "cause",
    "causes",
    "act",
    "acts",
    "apply",
    "applies",
    "hold",
    "holds",
    "follow",
    "follows",
    "vary",
    "varies",
    "exist",
    "exists",
    "contain",
    "contains",
    "consist",
    "consists",
    "determine",
    "determines",
    "represent",
    "represents",
    "call",
    "called",
    "define",
    "defined",
    "state",
    "states",
    "provide",
    "provides",
    "result",
    "results",
    "occur",
    "occurs",
    "indicate",
    "indicates",
    "exert",
    "exerts",
    "exhibit",
    "exhibits",
    "obey",
    "obeys",
    "yield",
    "yields",
})


# Imperative problem/exercise starters — instructions, not claims.
_PROBLEM_STARTERS = frozenset({
    "calculate",
    "find",
    "determine",
    "give",
    "show",
    "prove",
    "solve",
    "estimate",
    "derive",
    "explain",
    "describe",
    "draw",
    "sketch",
    "identify",
    "compute",
    "evaluate",
    "verify",
    "assume",
    "suppose",
    "consider",
    "take",
    "use",
    "repeat",
    "compare",
    "predict",
    "check",
    "plot",
    "graph",
    "notice",
    "list",
    "rank",
    "select",
    "choose",
    "distinguish",
    "state",
    "discuss",
    "argue",
    "justify",
})


def _has_run_together(text: str) -> bool:
    """True when a token is implausibly long — PDF text with dropped spaces."""
    return any(len(w) > 20 for w in text.split())


def _has_control_chars(text: str) -> bool:
    return any(ord(ch) < 32 and ch not in "\n\t" for ch in text)


def _balanced(text: str) -> bool:
    return (
        text.count("(") == text.count(")")
        and text.count("[") == text.count("]")
        and text.count("{") == text.count("}")
    )


def _strip_mc_prefix(text: str) -> str:
    """Strip a leading multiple-choice answer marker, if present."""
    stripped = _MC_PREFIX_RE.sub("", text, count=1)
    stripped = _MC_LONE_LETTER_RE.sub("", stripped, count=1)
    return stripped.strip()


def _is_claim(text: str) -> bool:
    """True when ``text`` is a self-contained declarative span worth keeping."""
    t = text.strip()
    if not t or t.endswith("?"):
        return False

    core = _strip_mc_prefix(t)
    if not core or core.endswith("?"):
        return False
    if _BOILERPLATE_RE.match(core):
        return False
    if _has_control_chars(t):
        return False
    if _has_run_together(t):
        return False
    if not _balanced(t):
        return False
    if any(s in t.lower() for s in ("http://", "https://", "www.", "@")):
        return False

    words = core.split()
    # Imperative problem statements are exercises, not claims.
    if words[0].lower().rstrip(".,;:") in _PROBLEM_STARTERS:
        return False

    # A formula is a claim regardless of prose word count (e.g. "p = mv").
    if "=" in core:
        return len(words) >= 2
    if len(words) < 4 or len(words) > 60:
        return False

    # Otherwise require a verb-ish token so fragments don't pass.
    return any(w in _VERB_TOKENS for w in core.lower().split())


# ---------------------------------------------------------------------------
# Text segmentation
# ---------------------------------------------------------------------------


def _dehyphenate(text: str) -> str:
    """Rejoin words hyphenated across a line break: "ex-\npansions" → "expansions"."""
    return re.sub(r"(\w)-\s+(\w)", r"\1\2", text)


def _segment_sentences(text: str) -> list[str]:
    """Split a chunk into sentence-level spans.

    Collapses PDF line-wrapping to single spaces, de-hyphenates, then splits on
    sentence-ending punctuation followed by a capital letter.
    """
    flat = re.sub(r"\s+", " ", text)
    flat = _dehyphenate(flat)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", flat)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Domain assignment (unchanged behaviour)
# ---------------------------------------------------------------------------


def _domain_for_chunk(chunk_name: str) -> str:
    if "mechanics" in chunk_name or "vol1" in chunk_name:
        return "mechanics"
    if "vol2" in chunk_name or "em" in chunk_name:
        return "electromagnetism"
    if "light" in chunk_name.lower() or "crowell" in chunk_name:
        return "general"
    if "vol3" in chunk_name or "modern" in chunk_name:
        return "modern-quantum"
    return "general"


def _assign_domain(text: str, source_domain: str) -> str:
    text_lower = text.lower()
    if any(
        w in text_lower
        for w in ["quantum", "photon", "planck", "bohr", "wave function", "schr\u00f6dinger"]
    ):
        return "modern-quantum"
    if any(
        w in text_lower
        for w in ["electric", "magnetic", "charge", "current", "circuit", "coulomb", "faraday"]
    ):
        return "electromagnetism"
    if any(
        w in text_lower
        for w in ["optics", "light", "lens", "mirror", "refraction", "diffraction", "interference"]
    ):
        return "optics-waves"
    if any(
        w in text_lower
        for w in [
            "force",
            "momentum",
            "energy",
            "velocity",
            "acceleration",
            "mass",
            "newton",
            "kinetic",
            "gravity",
        ]
    ):
        return "mechanics"
    return source_domain


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_claims_from_chunks(chunks_dir: str) -> list[Claim]:
    claims: list[Claim] = []

    for fname in sorted(os.listdir(chunks_dir)):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(chunks_dir, fname)
        source = "openstax" if ("openstax" in fname or "ostax" in fname) else "crowell"
        source_domain = _domain_for_chunk(fname)

        with open(fpath) as f:
            content = f.read()

        # Drop the provenance header lines written by corpus/fetch.py.
        content = "\n".join(line for line in content.splitlines() if not line.startswith("#"))

        for sentence in _segment_sentences(content):
            if not _is_claim(sentence):
                continue
            # Store the cleaned span (multiple-choice prefix stripped).
            core = _strip_mc_prefix(sentence)
            normalized = normalize(core)
            domain = _assign_domain(core, source_domain)
            has_formula = bool(re.search(r"[=\u00d7\u221a\u222b\u2202]", core))
            base_conf = 0.85 if has_formula else 0.78
            confidence = min(0.95, base_conf + hash(core[:20]) % 10 / 100)

            claims.append(
                Claim(
                    claim_id=claim_hash(core),
                    source=source,
                    chunk=fname.replace(".txt", ""),
                    domain=domain,
                    text=core,
                    normalized=normalized,
                    model_confidence=round(confidence, 3),
                )
            )

    # Deduplicate within each source, but ALLOW cross-source duplicates
    # (identical normalized text from different sources → separate claim entries
    #  with the same claim_id but different source tags — enables corroboration).
    seen: dict[str, set[str]] = defaultdict(set)
    deduped: list[Claim] = []
    for c in claims:
        if c.source not in seen[c.normalized]:
            seen[c.normalized].add(c.source)
            deduped.append(c)

    cross_source = sum(1 for s in seen.values() if len(s) >= 2)
    if cross_source > 0:
        print(f"  Cross-source overlaps detected: {cross_source} claims appear in ≥2 sources")

    return deduped


def save_claims(claims: list[Claim], path: str) -> None:
    with open(path, "w") as f:
        json.dump(
            [
                {
                    "claim_id": c.claim_id,
                    "source": c.source,
                    "chunk": c.chunk,
                    "domain": c.domain,
                    "text": c.text,
                    "normalized": c.normalized,
                    "model_confidence": c.model_confidence,
                }
                for c in claims
            ],
            f,
            indent=2,
        )


def load_claims(path: str) -> list[dict[str, object]]:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON list in {path}")
    return [c for c in data if isinstance(c, dict)]


def main() -> None:
    exp_dir = os.path.dirname(os.path.abspath(__file__))
    chunks_dir = os.path.join(exp_dir, "corpus", "chunks")
    out_path = os.path.join(exp_dir, "results", "claims.json")

    print("Extracting sentence-level spans from corpus chunks...")
    claims = extract_claims_from_chunks(chunks_dir)
    save_claims(claims, out_path)

    domains: dict[str, int] = {}
    for c in claims:
        domains[c.domain] = domains.get(c.domain, 0) + 1

    print(f"Extracted {len(claims)} spans")
    print(f"Domain distribution: {domains}")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
