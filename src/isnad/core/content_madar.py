"""Content-level madār detection — the *detectable* half of chain independence (#54).

The N_eff / tawātur discount (see ``corroboration.py``) prices in the
*unobservable* shared-failure prior. This module handles the *observable* half:
when two nominally-independent chains repeat the **same error**, that is a
fingerprint of a common upstream (the classical madār — a received mistake
echoed through distinct routes), not independent confirmation.

The discriminator is **error identity, not answer identity**:

- Two chains agreeing on a *correct* statement is expected agreement — it is
  what independent corroboration looks like.
- Two chains agreeing on a *wrong* statement is suspicious — independent
  witnesses do not independently make the *same specific mistake*.

This is checkable **only where we can verify wrongness** — i.e. where a content
critic has flagged the claim as CONTRADICTION against the corpus. For a novel
claim the corpus cannot check, content-level madār is genuinely undetectable,
and that limit is stated, not papered over.

This module is pure and side-effect-free: it takes the base claim's content
verdict, the corroborating chains' content verdicts, and the claim texts, and
returns whether any corroborating chain shares the base claim's error
fingerprint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from isnad.types import ContentVerdict

# Number tokens, normalised for comparison: "3,000" -> "3000", "3.0" -> "3.0".
_NUM = re.compile(r"[0-9][0-9,]*\.?[0-9]*")


def _normalize_numbers(text: str) -> frozenset[str]:
    return frozenset(t.replace(",", "") for t in _NUM.findall(text))


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass(frozen=True)
class ErrorFingerprint:
    """A fingerprint of a claim's specific error, extracted for comparison.

    ``numbers`` is the multiset of numeric tokens; ``negation`` is whether the
    claim asserts a negation (\"is not\", \"no\", \"never\"). Two claims with the
    same error fingerprint are candidates for a shared upstream mistake.
    """

    numbers: frozenset[str]
    negation: bool
    text: str

    @classmethod
    def from_claim(cls, text: str) -> ErrorFingerprint:
        n = _normalize_text(text)
        # Detect a dropped/flipped negation. Match at word boundaries so both
        # sentence-initial ("Never…") and mid-string ("is not…") forms fire.
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
            text=n,
        )

    def shares_error_with(self, other: ErrorFingerprint) -> bool:
        """True if two fingerprints could be the *same specific mistake*.

        The strongest signal is identical numbers (a wrong figure repeated) or
        identical negation (a dropped/flipped 'not' repeated). Identical full
        text with different numbers is NOT an error match — different numbers on
        the same sentence are different mistakes, not a shared one.
        """
        if self.text == other.text:
            # Same words. If the numbers also match, it's the same exact claim;
            # if not, the sentence is a template and the numbers differ — not a
            # shared numeric error.
            return self.numbers == other.numbers
        # Different words but identical numbers and identical negation polarity:
        # the specific wrong figure (or the specific wrong polarity) is echoed.
        # ``bool(self.numbers)`` guards the empty case explicitly: the old form
        # ``self.numbers and ...`` returned an empty frozenset (falsy) instead of
        # False when there were no numbers — behaviorally equivalent but not a
        # bool, which is a latent type bug (and a footgun for `is False` checks).
        return (
            bool(self.numbers)
            and self.numbers == other.numbers
            and self.negation == other.negation
        )


def detect_content_madar(
    base_claim: str,
    base_verdict: ContentVerdict,
    corroborating: list[tuple[str, ContentVerdict]],
) -> bool:
    """Return True if any corroborating chain shares the base claim's *error*.

    Only fires when the base claim is itself CONTRADICTION (a corpus-checkable
    error). If the base claim is correct or unverifiable, there is no error to
    fingerprint, and corroboration is not content-madar (an undetectable case
    for novel claims is reported as ``False``, not guessed).
    """
    if base_verdict is not ContentVerdict.CONTRADICTION:
        return False

    base_fp = ErrorFingerprint.from_claim(base_claim)
    for text, verdict in corroborating:
        if verdict is not ContentVerdict.CONTRADICTION:
            # A corroborating chain that is *not* flagged as an error is not
            # repeating the base claim's mistake — it may be a genuine
            # independent confirmation of a *different* (correct) reading.
            continue
        if base_fp.shares_error_with(ErrorFingerprint.from_claim(text)):
            return True
    return False
