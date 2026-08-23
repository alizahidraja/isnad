"""ISNAD-Bench: the preregistered ground-truth mapping.

Pure functions mapping classical hadith data (Ibn Hajar's *Taqrib* 12-tier
narrator ranks, and the scholars' per-chain verdicts) onto ISNAD's ordinal
grades. No I/O, no state — fully unit-testable.

The mapping is frozen in ``bench/docs/mapping.md``. This module is the code
form of that document. Any change to the mapping is a new benchmark version
with a new, separately-reported number.
"""

from __future__ import annotations

from dataclasses import dataclass

from isnad.types import AdalahGrade, ChainGrade, DabtGrade, NarratorGrade

# ---------------------------------------------------------------------------
# Chain-discontinuity sentinels (ittiṣāl breaks)
#
# The corpus encodes classical chain gaps as synthetic "narrator" nodes:
#   - موضع تعليق  (taʿlīq  — the head of the chain is omitted)
#   - موضع إرسال  (irsāl   — a narrator is omitted mid-chain)
#   - موضع انقطاع (inqiṭāʿ — the chain is broken)
# These are NOT narrators; they map onto ISNAD's ``is_complete=False``.
# ---------------------------------------------------------------------------
SENTINEL_NAMES = frozenset({"موضع تعليق", "موضع إرسال", "موضع انقطاع"})


def is_sentinel(name: str | None, rank_no: int | None, rank: str | None) -> bool:
    """True if this node is a chain-gap marker, not a real narrator."""
    if name is not None and name in SENTINEL_NAMES:
        return True
    # Belt-and-suspenders: the sentinels are the only rank_no=12 nodes with no
    # grade label (real fabricators at rank 12 always carry a grade string).
    return rank_no == 12 and rank is None


@dataclass(frozen=True)
class MappedNarrator:
    """A narrator translated onto ISNAD's ordinals."""

    rank_no: int | None
    narrator_grade: NarratorGrade
    adalah_grade: AdalahGrade
    dabt_grade: DabtGrade
    is_sentinel: bool = False


# rank_no -> (NarratorGrade, AdalahGrade, DabtGrade). Preregistered (§3.1).
_RANK_TABLE: dict[int, tuple[NarratorGrade, AdalahGrade, DabtGrade]] = {
    1: (NarratorGrade.RELIABLE, AdalahGrade.HIGH, DabtGrade.HIGH),
    2: (NarratorGrade.RELIABLE, AdalahGrade.HIGH, DabtGrade.HIGH),
    3: (NarratorGrade.RELIABLE, AdalahGrade.HIGH, DabtGrade.HIGH),
    4: (NarratorGrade.ACCEPTABLE, AdalahGrade.ACCEPTABLE, DabtGrade.ACCEPTABLE),
    5: (NarratorGrade.ACCEPTABLE, AdalahGrade.ACCEPTABLE, DabtGrade.LOW),
    6: (NarratorGrade.ACCEPTABLE, AdalahGrade.ACCEPTABLE, DabtGrade.ACCEPTABLE),
    7: (NarratorGrade.UNGRADED, AdalahGrade.UNASSESSED, DabtGrade.UNASSESSED),
    8: (NarratorGrade.WEAK, AdalahGrade.ACCEPTABLE, DabtGrade.LOW),
    9: (NarratorGrade.UNGRADED, AdalahGrade.UNASSESSED, DabtGrade.UNASSESSED),
    10: (NarratorGrade.REJECTED, AdalahGrade.SUSPECT, DabtGrade.LOW),
    11: (NarratorGrade.REJECTED, AdalahGrade.COMPROMISED, DabtGrade.LOW),
    12: (NarratorGrade.REJECTED, AdalahGrade.COMPROMISED, DabtGrade.LOW),
}

_UNGRADED = (NarratorGrade.UNGRADED, AdalahGrade.UNASSESSED, DabtGrade.UNASSESSED)


def narrator_grade_from_rank(
    rank_no: int | None, rank: str | None = None, name: str | None = None
) -> MappedNarrator:
    """Map one narrator's rank to ISNAD's (narrator, integrity, precision) grades.

    Sentinels (chain gaps) are returned with ``is_sentinel=True`` and an
    UNGRADED grade — callers must exclude them from the narrator list and treat
    the chain as incomplete. Unranked/unknown narrators map to UNGRADED.
    """
    if is_sentinel(name, rank_no, rank):
        return MappedNarrator(
            rank_no=rank_no,
            narrator_grade=NarratorGrade.UNGRADED,
            adalah_grade=AdalahGrade.UNASSESSED,
            dabt_grade=DabtGrade.UNASSESSED,
            is_sentinel=True,
        )
    ng, ag, dg = _RANK_TABLE.get(rank_no if rank_no is not None else -1, _UNGRADED)
    return MappedNarrator(
        rank_no=rank_no,
        narrator_grade=ng,
        adalah_grade=ag,
        dabt_grade=dg,
        is_sentinel=False,
    )


# ---------------------------------------------------------------------------
# Chain verdict (sanads.hukum) -> ChainGrade
#
# The scholars' free-text isnād verdicts. Classified on the leading phrase.
# Order matters: the "very weak" markers (shadīd al-ḍaʿf / matrūk / munkar /
# muttaham / fabrication) are checked before plain "weak".
# ---------------------------------------------------------------------------

# "Very weak" = a rejected narrator is the binding constraint (→ ISNAD MAWDU).
_MAWDU_MARKERS = (
    "شديد الضعف",  # very weak
    "متهم بالوضع",  # accused of fabrication
    "متهم بالكذب",  # accused of lying
    "منكر الحديث",  # rejected/munkar narrator
    "متروك الحديث",  # abandoned/matrūk narrator
    "موضوع",  # fabricated
    "كذاب",  # liar
    "يضع الحديث",  # fabricates hadith
)


def chain_grade_from_hukum(hukum: str | None) -> ChainGrade | None:
    """Classify a scholar's chain verdict into an ISNAD ``ChainGrade``.

    Returns ``None`` for verdicts that do not match any preregistered pattern
    (these are reported as "unclassified" rather than silently guessed).
    """
    if not hukum:
        return None
    for marker in _MAWDU_MARKERS:
        if marker in hukum:
            return ChainGrade.MAWDU
    if "ضعيف" in hukum:
        return ChainGrade.DAIF
    if "حسن" in hukum:
        return ChainGrade.HASAN
    if "متصل" in hukum or "ثقات" in hukum:
        return ChainGrade.SAHIH
    return None


# ---------------------------------------------------------------------------
# Critic statements (aqwal.qawl) -> NarratorGrade
#
# Used by M3 (the human ceiling): how well do the critics agree with each other
# on a narrator? Keyword order matters — strongest verdicts first.
# ---------------------------------------------------------------------------

_REJECTED_QAWL = ("متروك", "منكر", "كذاب", "وضاع", "ليس بثقة", "يضع الحديث", "متهم")
_WEAK_QAWL = (
    "ضعيف",
    "ضعفه",
    "ضعفوه",
    "ليس بالقوي",
    "لين الحديث",
    "ليس بشيء",
    "فيه نظر",
    "لا يتابع",
    "الضعفاء",
)
_UNGRADED_QAWL = ("مجهول", "لا يعرف", "لم أعرفه", "لا أعرفه", "لا يدرى", "مستور")
_RELIABLE_QAWL = (
    "ثقة",
    "وثق",
    "ثبت",
    "حافظ",
    "الثقات",
    "صحابي",
    "صحبة",
    "أثنى عليه",
    "محله الصدق",
    "صالح الحديث",
)
_ACCEPTABLE_QAWL = (
    "صدوق",
    "مقبول",
    "لا بأس",
    "ليس به بأس",
    "صالح",
    "شيخ صالح",
)


def grade_from_qawl(qawl: str | None) -> NarratorGrade | None:
    """Classify a critic's jarḥ–taʿdīl statement into a NarratorGrade.

    Returns ``None`` for statements that are biographical references ("mentioned
    in book X") or otherwise carry no grade, so the human-ceiling analysis can
    report its coverage honestly rather than guessing.
    """
    if not qawl:
        return None
    q = qawl.strip()
    if any(k in q for k in _REJECTED_QAWL):
        return NarratorGrade.REJECTED
    if any(k in q for k in _WEAK_QAWL):
        return NarratorGrade.WEAK
    if any(k in q for k in _UNGRADED_QAWL):
        return NarratorGrade.UNGRADED
    if any(k in q for k in _RELIABLE_QAWL):
        return NarratorGrade.RELIABLE
    if any(k in q for k in _ACCEPTABLE_QAWL):
        return NarratorGrade.ACCEPTABLE
    return None
