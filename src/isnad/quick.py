"""The one-call convenience API — ``isnad.grade(...)``.

Everything in the expert API stays available; this is the surface a stranger
should be able to use in thirty seconds and screenshot.  ``Verdict.why`` is the
human-readable justification — the thing people paste into Slack and blog posts.
"""

from __future__ import annotations

from dataclasses import dataclass

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.types import Action, ChainGrade, NarratorGrade, TransformType


@dataclass
class Verdict:
    """The result of ``grade``: a chain grade, an action, and a ``why``."""

    chain_grade: ChainGrade
    action: Action | None
    weakest_link: str
    why: str


def _narrator_grade(registry: Registry, narrator_id: str, domain: str) -> NarratorGrade:
    return registry.get_grade_for_link(narrator_id, domain, None)


def grade(
    claim: str,
    chain: list[str],
    registry: Registry,
    *,
    domain: str = "general",
    transform_types: list[TransformType] | None = None,
) -> Verdict:
    """Grade a claim's transmission chain and decide an action.

    Args:
        claim: The claim text (used for the ``why`` string; content criticism is
            not run here — pass a critic's verdict through ``decide`` if you
            want the full 4×2 matrix).
        chain: Ordered narrator ids (source first, answer last).
        registry: The graded-narrator registry.
        domain: Domain tag for grading.
        transform_types: Optional per-link transform types; defaults to
            PASS_THROUGH (identity).

    Returns:
        A ``Verdict``.  ``action`` is ``None`` when no content verdict is
        supplied — chain grading alone does not decide serve/review/quarantine.
    """
    specs = [
        ChainLinkSpec(
            narrator_id,
            i,
            domain=domain,
            transform_type=(transform_types[i] if transform_types else TransformType.PASS_THROUGH),
        )
        for i, narrator_id in enumerate(chain)
    ]
    chain_obj = Chain(specs)
    grades = [registry.get_grade_for_link(s.narrator_id, s.domain, s.version) for s in specs]
    chain_grade = grade_chain(
        grades, [s.transform_type for s in specs], is_complete=chain_obj.is_complete
    )

    weakest = min(chain, key=lambda nid: _narrator_grade(registry, nid, domain))
    weakest_grade = _narrator_grade(registry, weakest, domain)

    why = (
        f"claim {claim!r} → chain {chain_grade.value.upper()} "
        f"(weakest: {weakest}, {weakest_grade.value})"
    )
    return Verdict(
        chain_grade=chain_grade,
        action=None,
        weakest_link=weakest,
        why=why,
    )


__all__ = ["Verdict", "grade"]
