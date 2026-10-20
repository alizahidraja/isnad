"""Embedding-based content critic for ISNAD — TF-IDF weighted, zero-dependency.

The DEFAULT critic.  Works out of the box with no downloads, no API keys.
Uses TF-IDF (Term Frequency × Inverse Document Frequency) weighting for
much better similarity than raw word-overlap.

Upgrade path (optional):
    pip install isnad[nli]  →  enables HybridCritic (MiniLM embeddings)
    pip install sentence-transformers  →  enables LocalNLICritic (DeBERTa NLI)

For production: use LocalNLICritic or LLMCritic for highest accuracy.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from isnad.types import ContentVerdict


def _tokenize(text: str) -> list[str]:
    """Tokenize text into words, keeping numbers and units."""
    return re.findall(r"[a-z0-9]+(?:/[a-z0-9²³]+)?", text.lower())


class TFIDFIndex:
    """Lightweight TF-IDF index — zero dependencies, corpus-aware weighting.

    Builds an inverted index from the corpus and computes TF-IDF vectors
    for similarity scoring.  Much better than raw word-overlap because
    rare terms get higher weight and common words are discounted.
    """

    def __init__(self, corpus: list[str] | None = None):
        self._doc_freq: Counter[str] = Counter()
        self._doc_count = 0
        self._docs: list[list[str]] = []
        if corpus:
            self.fit(corpus)

    def fit(self, corpus: list[str]) -> None:
        """Build TF-IDF index from corpus documents."""
        self._doc_count = len(corpus)
        self._docs = []
        self._doc_freq = Counter()
        for doc in corpus:
            tokens = list(set(_tokenize(doc)))  # unique terms per doc for DF
            self._docs.append(_tokenize(doc))  # all terms for TF
            for t in tokens:
                self._doc_freq[t] += 1

    def tfidf_vector(self, text: str) -> dict[str, float]:
        """Compute TF-IDF vector for a text."""
        tokens = _tokenize(text)
        if not tokens:
            return {}
        tf = Counter(tokens)
        vec: dict[str, float] = {}
        for term, count in tf.items():
            df = self._doc_freq.get(term, 0)
            if df == 0:
                df = 1  # smooth unseen terms
            idf = math.log((self._doc_count + 1) / (df + 1)) + 1.0
            vec[term] = (count / len(tokens)) * idf
        return vec

    def cosine_similarity(self, a: dict[str, float], b: dict[str, float]) -> float:
        """Cosine similarity between two TF-IDF vectors."""
        if not a or not b:
            return 0.0
        dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in set(a) | set(b))
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


_WORD_NUMBERS = {
    "zero": 0.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
    "eleven": 11.0,
    "twelve": 12.0,
    "thirteen": 13.0,
    "fourteen": 14.0,
    "fifteen": 15.0,
    "sixteen": 16.0,
    "seventeen": 17.0,
    "eighteen": 18.0,
    "nineteen": 19.0,
    "twenty": 20.0,
    "thirty": 30.0,
    "forty": 40.0,
    "fifty": 50.0,
    "sixty": 60.0,
    "seventy": 70.0,
    "eighty": 80.0,
    "ninety": 90.0,
}
_WORD_SCALES = {
    "hundred": 100.0,
    "thousand": 1000.0,
    "million": 1000000.0,
    "billion": 1000000000.0,
}
_TENS = {
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
}
_ONES = {
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
}


def _has_phrase(text: str, phrase: str) -> bool:
    """Whole-word/phrase membership (avoids 'per' matching inside 'experiment')."""
    # Lookbehind/lookahead exclude word chars AND hyphens, so a hyphen inside
    # a compound ("non-negative") does not open a word boundary.
    return re.search(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])", text) is not None


def _parse_number(tokens: list[str], i: int) -> tuple[float | None, int]:
    """Parse one written-out number starting at tokens[i]; return (value, next_i)."""
    t = tokens[i]
    if t in ("infinite", "infinity"):
        return float("inf"), i + 1
    if t not in _WORD_NUMBERS:
        return None, i
    # decimal: "three point one four" -> 3.14 (all following number words are digits)
    if i + 2 < len(tokens) and tokens[i + 1] == "point" and tokens[i + 2] in _WORD_NUMBERS:
        whole = _WORD_NUMBERS[t]
        j = i + 2
        digits: list[float] = []
        while j < len(tokens) and tokens[j] in _WORD_NUMBERS and tokens[j] not in _WORD_SCALES:
            digits.append(_WORD_NUMBERS[tokens[j]])
            j += 1
        frac = sum(d / (10 ** (k + 1)) for k, d in enumerate(digits))
        return whole + frac, j
    value = _WORD_NUMBERS[t]
    i += 1
    # tens + ones: "twenty one" -> 21
    if t in _TENS and i < len(tokens) and tokens[i] in _ONES:
        value += _WORD_NUMBERS[tokens[i]]
        i += 1
    # scales: "three hundred million" -> 3e8; continuation "one hundred twenty one" -> 121
    while i < len(tokens) and tokens[i] in _WORD_SCALES:
        value *= _WORD_SCALES[tokens[i]]
        i += 1
        if i < len(tokens) and tokens[i] in _WORD_NUMBERS and tokens[i] not in _WORD_SCALES:
            cont, i = _parse_number(tokens, i)
            if cont is not None:
                value += cont
    return value, i


def _word_numbers(text: str) -> list[float]:
    """Extract written-out numbers ("zero", "three hundred million", 3.14, 121)."""
    tokens = re.findall(r"[a-z]+", text.lower())
    out: list[float] = []
    i = 0
    while i < len(tokens):
        value, i = _parse_number(tokens, i)
        if value is not None:
            out.append(value)
        else:
            i += 1
    return out


def _extract_numbers(text: str) -> list[float]:
    """All numeric values in a text: digit numbers plus written-out numbers."""
    nums = [float(n) for n in re.findall(r"\d+\.?\d*", text)]
    nums.extend(_word_numbers(text))
    return nums


def _numbers_diverge(a: float, b: float) -> bool:
    """True when two magnitudes genuinely conflict (safe to call a contradiction)."""
    if a == b:
        return False
    if (a == 0.0) != (b == 0.0):
        return True
    if math.isinf(a) or math.isinf(b):
        return True
    if a <= 0.0 or b <= 0.0:
        return False
    return max(a, b) / min(a, b) > 3.0


_TEMP_UNITS = ("fahrenheit", "kelvin", "celsius", "centigrade")


def _temp_scale(text: str) -> str | None:
    """Return the named temperature scale, or None if no scale is named."""
    for u in _TEMP_UNITS:
        if _has_phrase(text, u):
            return "celsius" if u in ("celsius", "centigrade") else u
    return None


def _has_contradiction_signal(claim: str, corpus_claim: str) -> bool:
    """Heuristic contradiction detection between two similar claims.

    Checks negation patterns, opposite words, and numeric divergence
    (including zero, written-out numbers, and "infinite").
    """
    c_low = claim.lower()
    cc_low = corpus_claim.lower()

    if c_low == cc_low:
        return False

    for pos, neg in [
        (" is ", " is not "),
        (" does ", " does not "),
        (" can ", " cannot "),
        (" has ", " has no "),
    ]:
        if (pos in c_low and neg in cc_low) or (neg in c_low and pos in cc_low):
            return True

    for a, b in [
        ("increases", "decreases"),
        ("positive", "negative"),
        ("attractive", "repulsive"),
        ("faster", "slower"),
        ("higher", "lower"),
        ("larger", "smaller"),
        ("up", "down"),
        ("hotter", "colder"),
        ("clockwise", "counterclockwise"),
        ("left", "right"),
        ("always", "never"),
        ("toward", "away"),
        ("stationary", "moving"),
        ("at rest", "in motion"),
        ("both", "purely"),
    ]:
        if (_has_phrase(c_low, a) and _has_phrase(cc_low, b)) or (
            _has_phrase(c_low, b) and _has_phrase(cc_low, a)
        ):
            return True

    nums_c = _extract_numbers(claim)
    nums_cc = _extract_numbers(corpus_claim)
    if len(nums_c) == 1 and len(nums_cc) == 1 and _numbers_diverge(nums_c[0], nums_cc[0]):
        scale_c = _temp_scale(c_low)
        scale_cc = _temp_scale(cc_low)
        same_scale = scale_c is None or scale_cc is None or scale_c == scale_cc
        if same_scale and not any(_has_phrase(c_low, w) for w in ["equal", "same", "constant"]):
            return True
    return False


class EmbeddingCritic:
    """Default content critic — TF-IDF weighted, zero dependencies.

    Works immediately with no installs, no downloads, no API keys.
    For better accuracy: pip install isnad[nli] and use HybridCritic.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.4).  Swap freely.

    This critic is contradiction-ONLY: it returns CONTRADICTION when it finds a
    negation/antonym/numeric-divergence signal and UNVERIFIABLE otherwise. It
    never returns CONSISTENT — symmetric lexical overlap cannot affirm that a
    claim is correct (a <=3x dose error or an unlisted antonym pair would be
    blessed). Affirming consistency is the semantic critic's job (NLI/LLM).

    Args:
        contradiction_threshold: Cosine sim above which we check for
            contradiction signals.
    """

    def __init__(
        self,
        contradiction_threshold: float = 0.50,
    ):
        self.contradiction_threshold = contradiction_threshold
        self._index: TFIDFIndex | None = None
        self._corpus_texts: list[str] = []
        self._vectors: list[dict[str, float]] = []

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against the corpus using TF-IDF similarity."""
        if not corpus_claims:
            return ContentVerdict.UNVERIFIABLE

        # Build index on first call or when corpus changes
        if self._index is None or corpus_claims != self._corpus_texts:
            self._index = TFIDFIndex(corpus_claims)
            self._corpus_texts = list(corpus_claims)
            self._vectors = [self._index.tfidf_vector(c) for c in corpus_claims]

        claim_vec = self._index.tfidf_vector(normalized_claim)

        best_sim = 0.0
        best_idx = 0
        for i, cv in enumerate(self._vectors):
            sim = self._index.cosine_similarity(claim_vec, cv)
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        # Check contradiction first (lower threshold, more specific)
        if best_sim >= self.contradiction_threshold:
            best_text = self._corpus_texts[best_idx]
            if _has_contradiction_signal(normalized_claim, best_text):
                return ContentVerdict.CONTRADICTION

        # Never return CONSISTENT: symmetric lexical overlap cannot affirm a
        # claim is correct (<=3x dose errors and unlisted antonym pairs would be
        # blessed). CONTRADICTION is the only positive signal; everything else
        # is UNVERIFIABLE. Affirming consistency is the semantic critic's job.

        return ContentVerdict.UNVERIFIABLE
