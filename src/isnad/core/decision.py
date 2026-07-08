"""Decision Matrix — the 4×2 action router combining chain grade × content criticism.

Implements paper §4.4, the framework's most directly actionable artifact.

The matrix:

                    CONSISTENT                          CONTRADICTION
  ─────────────── ──────────────────────────────────  ───────────────────────────────────
  SAHIH            SERVE (cache)                       REVIEW (ʿilal — highest-value case)
  HASAN            SERVE_WITH_CAVEAT (seek corrob.)   REVIEW (hold; do not serve)
  DAIF             REVIEW (seek corroboration first)   QUARANTINE
  MAWDU            REJECT_AND_QUARANTINE_NARRATOR      REJECT_AND_QUARANTINE_NARRATOR

Key design defaults from the paper:
- Contradictions are adjudicated by humans (the muḥaddith role).
- The ṣaḥīḥ×contradiction cell is the most informative signal, not an error.
- The mawḍūʿ tier is active containment, not passive labeling.
"""

from __future__ import annotations

from isnad.types import Action, ChainGrade, ContentVerdict

# The decision matrix as a lookup table
_MATRIX: dict[tuple[ChainGrade, ContentVerdict], Action] = {
    (ChainGrade.SAHIH, ContentVerdict.CONSISTENT): Action.SERVE,
    (ChainGrade.SAHIH, ContentVerdict.CONTRADICTION): Action.REVIEW,
    (ChainGrade.SAHIH, ContentVerdict.UNVERIFIABLE): Action.SERVE_WITH_CAVEAT,
    (ChainGrade.HASAN, ContentVerdict.CONSISTENT): Action.SERVE_WITH_CAVEAT,
    (ChainGrade.HASAN, ContentVerdict.CONTRADICTION): Action.REVIEW,
    (ChainGrade.HASAN, ContentVerdict.UNVERIFIABLE): Action.REVIEW,
    (ChainGrade.DAIF, ContentVerdict.CONSISTENT): Action.REVIEW,
    (ChainGrade.DAIF, ContentVerdict.CONTRADICTION): Action.QUARANTINE,
    (ChainGrade.DAIF, ContentVerdict.UNVERIFIABLE): Action.REVIEW,
    (ChainGrade.MAWDU, ContentVerdict.CONSISTENT): Action.REJECT_AND_QUARANTINE_NARRATOR,
    (ChainGrade.MAWDU, ContentVerdict.CONTRADICTION): Action.REJECT_AND_QUARANTINE_NARRATOR,
    (ChainGrade.MAWDU, ContentVerdict.UNVERIFIABLE): Action.REJECT_AND_QUARANTINE_NARRATOR,
}


def decide(chain_grade: ChainGrade, content_verdict: ContentVerdict) -> Action:
    """Route a (chain_grade, content_verdict) pair to the correct action.

    This is the decision matrix from paper §4.4, Table.  It combines
    transmission quality (chain grade) with content quality (matn criticism)
    into a concrete serve/review/quarantine action.

    Args:
        chain_grade: The ordinal chain grade (SAHIH/HASAN/DAIF/MAWDU).
        content_verdict: The content criticism verdict (CONSISTENT/CONTRADICTION/UNVERIFIABLE).

    Returns:
        The Action to take.

    Raises:
        KeyError: If an unexpected grade/verdict combination is passed.
    """
    key = (chain_grade, content_verdict)
    if key not in _MATRIX:
        raise KeyError(
            f"No matrix entry for chain_grade={chain_grade.value}, "
            f"content_verdict={content_verdict.value}"
        )
    return _MATRIX[key]


def describe_action(
    chain_grade: ChainGrade,
    content_verdict: ContentVerdict,
) -> str:
    """Return a human-readable description of what the matrix decided and why.

    Useful for logging, review-queue entries, and debugging.
    """
    action = decide(chain_grade, content_verdict)

    descriptions = {
        (ChainGrade.SAHIH, ContentVerdict.CONSISTENT): (
            "Sound chain, consistent content — serve directly and cache."
        ),
        (ChainGrade.SAHIH, ContentVerdict.CONTRADICTION): (
            "ʿIlal signal: sound chain but content contradicts corpus. "
            "This is the highest-value review case — either the new source "
            "changed the world's state or the corpus has a latent defect."
        ),
        (ChainGrade.HASAN, ContentVerdict.CONSISTENT): (
            "Good chain, consistent content — serve with explicit confidence "
            "caveat; seek corroboration."
        ),
        (ChainGrade.HASAN, ContentVerdict.CONTRADICTION): (
            "Good chain but content contradicts corpus — hold in review "
            "queue; do not serve until adjudicated."
        ),
        (ChainGrade.DAIF, ContentVerdict.CONSISTENT): (
            "Weak chain — hold; seek corroborating chain before serving."
        ),
        (ChainGrade.DAIF, ContentVerdict.CONTRADICTION): (
            "Weak chain with content contradiction — quarantine."
        ),
        (ChainGrade.MAWDU, ContentVerdict.CONSISTENT): (
            "Rejected narrator (mawḍūʿ tier) — reject claim and quarantine "
            "the narrator (active containment)."
        ),
        (ChainGrade.MAWDU, ContentVerdict.CONTRADICTION): (
            "Rejected narrator with content contradiction — reject claim and "
            "quarantine the narrator (poisoning mitigation)."
        ),
    }
    return descriptions.get(
        (chain_grade, content_verdict),
        f"Chain grade {chain_grade.value} × content {content_verdict.value} → {action.value}",
    )
