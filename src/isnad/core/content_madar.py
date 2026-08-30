"""Content-level shared-error detection — the *detectable* half of chain independence (#54).

The N_eff / tawatur discount (see ``corroboration.py``) prices in the
*unobservable* shared-failure prior. This module handles the *observable* half:
when two nominally-independent chains repeat the **same error**, that is a
fingerprint of a common upstream (the classical madar — a received mistake
echoed through distinct routes), not independent confirmation.

The discriminator is **error identity, not answer identity**:

- Two chains agreeing on a *correct* statement is expected agreement — it is
  what independent corroboration looks like.
- Two chains agreeing on a *wrong* statement is suspicious — independent
  witnesses do not independently make the *same specific mistake*.

This is checkable **only where we can verify wrongness** — i.e. where a content
critic has flagged the claim as CONTRADICTION against the corpus. For a novel
claim the corpus cannot check, content-level shared-error is genuinely
undetectable, and that limit is stated, not papered over.

The fingerprint is *deterministic and dependency-free*: numbers (and their
units), named entities, dates, and citation/identifier tokens, plus a lexical
shingle for near-paraphrase. It reports "evidence consistent with a shared
error", never proof of a common upstream — the flag only withholds
corroboration, it never serves or upgrades.

This module is pure and side-effect-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from isnad.types import ContentVerdict

_NUM = re.compile(r"[0-9][0-9,]*\.?[0-9]*")
# number followed by a unit token (e.g. "500,000 km/s", "97 records", "3 mg").
_NUM_UNIT = re.compile(r"([0-9][0-9,]*\.?[0-9]*)\s*([a-z]+(?:/[a-z0-9]+)?)")
# title-case words (proper names / entities), >=2 chars, not all-caps acronyms.
_TITLE_CASE = re.compile(r"\b[A-Z][a-z]{1,}\b")
# years 1000-2099, ISO dates, and month names.
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_MONTH = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.IGNORECASE,
)
# citation/identifier tokens: DOI, arXiv, URL, and "ref [n]" style.
_DOI = re.compile(r"10\.\d{4,9}/[^\s]+")
_ARXIV = re.compile(r"arxiv:\d{4}\.\d{4,5}", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s]+")
_REF = re.compile(r"ref\s*\[?\d+\]?", re.IGNORECASE)

_WORD = re.compile(r"[a-z0-9]+")

_SHINGLE_THRESHOLD = 0.7

_STOPWORDS = frozenset(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "by",
        "at",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "as",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "not",
        "no",
        "nor",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "can",
        "could",
        "would",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "will",
        "they",
        "them",
        "their",
        "he",
        "she",
        "his",
        "her",
        "we",
        "you",
        "our",
        "your",
        "i",
        "me",
        "my",
        "who",
        "whom",
        "which",
        "what",
        "when",
        "where",
        "why",
        "how",
    ]  # noqa: SIM905
)


def _normalize_numbers(text: str) -> frozenset[str]:
    return frozenset(t.replace(",", "") for t in _NUM.findall(text))


def _extract_units(text: str) -> frozenset[str]:
    """Normalized number+unit pairs, so a unit-prefix/format change still matches."""
    out = set()
    for m in _NUM_UNIT.finditer(text):
        num = m.group(1).replace(",", "")
        unit = m.group(2).lower()
        out.add(f"{num}|{unit}")
    return frozenset(out)


def _extract_entities(text: str) -> frozenset[str]:
    """Case-folded title-case tokens (proper names), minus stopwords."""
    return frozenset(
        t.lower() for t in _TITLE_CASE.findall(text) if t.lower() not in _STOPWORDS
    )


def _extract_dates(text: str) -> frozenset[str]:
    out = {m.group(0) for m in _YEAR.finditer(text)}
    out.update(m.group(0) for m in _ISO_DATE.finditer(text))
    out.update(m.group(0).lower() for m in _MONTH.finditer(text))
    return frozenset(out)


def _extract_citations(text: str) -> frozenset[str]:
    out = {m.group(0) for m in _DOI.finditer(text)}
    out.update(m.group(0).lower() for m in _ARXIV.finditer(text))
    out.update(m.group(0) for m in _URL.finditer(text))
    out.update(m.group(0).lower() for m in _REF.finditer(text))
    return frozenset(out)


def _extract_shingles(text: str) -> frozenset[str]:
    """Stopword-stripped word 2- and 3-grams, for near-paraphrase detection."""
    words = [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS]
    out = set()
    for n in (2, 3):
        for i in range(len(words) - n + 1):
            out.add(" ".join(words[i : i + n]))
    return frozenset(out)


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class ErrorFingerprint:
    """A fingerprint of a claim's specific error, extracted for comparison.

    ``numbers`` is the set of numeric tokens; ``negation`` is whether the claim
    asserts a negation ("is not", "no", "never"). ``units``/``entities``/
    ``dates``/``citations`` are the dependency-free "class of error" signals,
    and ``shingles`` supports near-paraphrase. Two claims that match on the
    same *specific* signal are candidates for a shared upstream mistake — the
    result is "evidence consistent with", never proof of, a common upstream.
    """

    numbers: frozenset[str]
    negation: bool
    units: frozenset[str]
    entities: frozenset[str]
    dates: frozenset[str]
    citations: frozenset[str]
    shingles: frozenset[str]
    text: str

    @classmethod
    def from_claim(cls, text: str) -> ErrorFingerprint:
        n = _normalize_text(text)
        negation = any(
            re.search(w, n)
            for w in (
                r"\bis not\b",
                r"\bare not\b",
                r"\bno\b",
                r"\bnever\b",
                r"\bdoes not\b",
                r"\bdo not\b",
                r"\bcannot\b",
                r"\bcan't\b",
            )
        )
        return cls(
            numbers=_normalize_numbers(text),
            negation=bool(negation),
            units=_extract_units(text),
            entities=_extract_entities(text),
            dates=_extract_dates(text),
            citations=_extract_citations(text),
            shingles=_extract_shingles(text),
            text=n,
        )

    def shares_error_with(self, other: ErrorFingerprint) -> bool:
        """True if two fingerprints could be the *same specific mistake*.

        Signals, strongest first:
        1. identical full text with identical numbers (verbatim echo);
        2. identical numbers with identical negation (a wrong figure repeated);
        3. identical negation AND an identical error-class token (same wrong
           entity — via set equality, so "X wrote the Iliad" vs "X wrote the
           Odyssey" do NOT collide on the shared "X" — or the same date,
           citation, or number+unit pair);
        4. near-paraphrase (lexical shingle overlap) AND a shared signal.
        Different numbers on the same sentence are different mistakes, not a
        shared one.
        """
        if self.text == other.text:
            return self.numbers == other.numbers

        # Legacy: a wrong figure repeated, with the same polarity.
        if bool(self.numbers) and self.numbers == other.numbers and self.negation == other.negation:
            return True

        # All remaining signals require matching polarity (negation is part of
        # error identity: a flipped vs a dropped "not" are different mistakes).
        if self.negation != other.negation:
            return False

        # Same wrong entity (full set equality, not mere intersection — a shared
        # subject alone is not a shared error).
        if self.entities and self.entities == other.entities:
            return True

        # Same scalar error-class token: unit, date, or citation.
        for a, b in (
            (self.units, other.units),
            (self.dates, other.dates),
            (self.citations, other.citations),
        ):
            if a and a & b:
                return True

        # Near-paraphrase: high lexical overlap AND at least one shared signal.
        if _jaccard(self.shingles, other.shingles) >= _SHINGLE_THRESHOLD:
            shared = (
                (self.entities & other.entities)
                or (self.dates & other.dates)
                or (self.citations & other.citations)
                or (self.units & other.units)
                or (self.numbers & other.numbers)
            )
            if shared:
                return True

        return False


def detect_content_madar(
    base_claim: str,
    base_verdict: ContentVerdict,
    corroborating: list[tuple[str, ContentVerdict]],
) -> bool:
    """Return True if any corroborating chain shares the base claim's *error*.

    Only fires when the base claim is itself CONTRADICTION (a corpus-checkable
    error). If the base claim is correct or unverifiable, there is no error to
    fingerprint, and the result is False (an undetectable case for novel claims
    is reported as False, not guessed). The result is "evidence consistent with
    a shared upstream error", never proof.
    """
    if base_verdict is not ContentVerdict.CONTRADICTION:
        return False

    base_fp = ErrorFingerprint.from_claim(base_claim)
    for text, verdict in corroborating:
        if verdict is not ContentVerdict.CONTRADICTION:
            continue
        if base_fp.shares_error_with(ErrorFingerprint.from_claim(text)):
            return True
    return False
