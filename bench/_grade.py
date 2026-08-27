"""Shared chain-grading logic for ISNAD-Bench (extracted from run.py).

These are the pure functions that map one isnād chain to an ISNAD grade and
label a disagreement with its principled explanation.  They live here — imported
by both ``run.py`` (the compute path) and ``export.py`` (the dataset-export
path) — so the two can never drift: the exported per-claim grades are, by
construction, the exact grades the benchmark's κ was computed from.
"""

from __future__ import annotations

from bench.data import Node
from bench.mapping import is_sentinel, narrator_grade_from_rank
from isnad.core.grading import grade_chain
from isnad.types import NarratorGrade, TransformType

# Sentinel names (gap markers) → whether the gap is the grade-preserving taʿlīq
# form or a genuine break (irsāl / inqiṭāʿ).
_TALIQ = "موضع تعليق"

# The corroboration bucket label (must match the RESULTS.md wording exactly).
_CORROBORATION_BUCKET = "corroboration: weak-alone → ḥasan-with-mutābaʿa"

_GradeResult = tuple[list[NarratorGrade], bool, list[int], bool, bool]


def grade_one_chain(
    nodes: tuple[Node, ...], rank_map: dict[int, NarratorGrade] | None = None
) -> _GradeResult:
    """Map one chain's nodes to ISNAD grades (sentinels → is_complete).

    Returns (narrator_grades, is_complete, rank_nos, has_taliq, has_gap).
    """
    narrator_grades: list[NarratorGrade] = []
    rank_nos: list[int] = []
    has_gap = False
    has_taliq = False
    for node in nodes:
        mapped = narrator_grade_from_rank(node.rank_no, node.rank, node.name)
        if mapped.is_sentinel:
            has_gap = True
            if node.name == _TALIQ:
                has_taliq = True
            continue
        if rank_map is not None and node.rank_no in rank_map:
            grade = rank_map[node.rank_no]
        else:
            grade = mapped.narrator_grade
        narrator_grades.append(grade)
        if node.rank_no is not None:
            rank_nos.append(node.rank_no)
    return narrator_grades, not has_gap, rank_nos, has_taliq, has_gap


def chain_grade_from_narrators(
    narrator_grades: list[NarratorGrade], is_complete: bool, lenient_unknown: bool = False
) -> str:
    """Apply the weakest-link rule to mapped narrator grades."""
    transforms = [TransformType.PASS_THROUGH] * len(narrator_grades)
    return str(
        grade_chain(narrator_grades, transforms, is_complete, lenient_unknown=lenient_unknown).value
    )


def independence_set(nodes: tuple[Node, ...]) -> frozenset[int]:
    """Narrator ids excluding companions (rank 1) and gap sentinels.

    Two routes of the same hadith that share *only* the companion are treated as
    independent (the madār-free comparison), since the companion is the common
    origin of every route.
    """
    return frozenset(
        n.rawi_id for n in nodes if not is_sentinel(n.name, n.rank_no, n.rank) and n.rank_no != 1
    )


def bucket(
    true: str,
    pred: str,
    has_gap: bool,
    has_taliq: bool,
    rank_nos: list[int],
    hukum: str | None,
) -> str | None:
    """Label a disagreement with the principled explanation, or None."""
    if true == pred:
        return None
    hukum = hukum or ""
    if true == "daif" and pred == "mawdu":
        return "severity: classical ḍaʿīf vs ISNAD mawḍūʿ (rejected narrator)"
    if true == "mawdu" and pred == "daif":
        return "severity: classical mawḍūʿ vs ISNAD ḍaʿīf"
    if has_gap and pred == "daif":
        if has_taliq:
            return "continuity: taʿlīq gap (scholar still sound/good)"
        return "continuity: irsāl/inqiṭāʿ gap"
    if true == "daif" and pred in ("hasan", "sahih"):
        if "توبع" in hukum:
            return _CORROBORATION_BUCKET
        if any(r in (7, 9) for r in rank_nos):
            return "leniency: majhūl → ḥasan ceiling"
        if any(k in hukum for k in ("تعليق", "إرسال", "انقطاع")):
            return "gap-in-text-only: ḍaʿīf by irsāl/taʿlīq (no sentinel)"
        return "leniency: weak → sound/good (mapping)"
    if true in ("sahih", "hasan") and pred in ("hasan", "sahih"):
        return "grade: ṣaḥīḥ ↔ ḥasan boundary"
    return "other"
