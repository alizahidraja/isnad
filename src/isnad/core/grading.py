"""Weakest-Link Evaluator — chain grade computation with pluggable strategy.

Implements paper §4.1 (weakest-link rule refined by transform type) and
the completeness (ittiṣāl) cap.

The default RefinedWeakestLink strategy walks the chain link-by-link:
- Destructive links: strict minimum — nothing downstream recovers what was lost.
  The destructive link's grade becomes a permanent floor.
- Generative links with corroboration and grade >= ACCEPTABLE: **replace** the
  floor with the generative link's own grade (they can both raise a lower floor
  and lower a higher floor).
- Generative links without corroboration (or WEAK generative): standard minimum.
- Incomplete chains (munqaṭiʿ): capped at DAIF regardless of narrator quality.

This is one instantiation of a parameter the framework leaves open
(see paper §4.2/§4.3).  Swap freely.
"""

from __future__ import annotations

from isnad.types import (
    AdalahGrade,
    ChainGrade,
    ContentVerdict,
    GradingStrategy,
    NarratorGrade,
    TransformType,
)


def _narrator_to_chain_grade(ng: NarratorGrade) -> ChainGrade:
    """Map a narrator grade to the corresponding chain grade tier."""
    mapping = {
        NarratorGrade.RELIABLE: ChainGrade.SAHIH,
        NarratorGrade.ACCEPTABLE: ChainGrade.HASAN,
        NarratorGrade.WEAK: ChainGrade.DAIF,
        NarratorGrade.REJECTED: ChainGrade.MAWDU,
        NarratorGrade.UNGRADED: ChainGrade.HASAN,  # ungraded → ḥasan ceiling
    }
    return mapping[ng]


class RefinedWeakestLink:
    """Default grading strategy: refined weakest-link with completeness cap.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2/§4.3).  Swap freely.

    The algorithm walks the transmission chain link-by-link, maintaining
    a running *floor* that represents the best grade the chain can achieve
    after each link:

    1. Destructive (extraction, chunking, lossy summarization): the link's
       grade becomes a hard floor.  Nothing downstream recovers lost info.

    2. Generative (broad-pretrained model synthesis) with corroboration:
       the link REPLACES the floor with its own grade.  This means it can
       *raise* a floor lowered by a previous destructive link (repair) OR
       *lower* a higher floor (introduce corruption).  Only fires when the
       generative link is ACCEPTABLE or better; WEAK generative always
       degrades.

    3. Generative without corroboration, or pass-through: standard minimum.

    4. Incomplete chain → DAIF.  REJECTED narrator → MAWDU.
    """

    def compute_chain_grade(
        self,
        link_narrator_grades: list[NarratorGrade],
        link_transform_types: list[TransformType],
        is_complete: bool,
        *,
        corroboration_support: bool = False,
        link_adalah_grades: list[AdalahGrade] | None = None,
        link_fidelity_verdicts: list[ContentVerdict] | None = None,
    ) -> ChainGrade:
        """Compute the chain grade by walking the chain link-by-link.

        Args:
            link_narrator_grades: Per-link narrator grades, in chain order.
            link_transform_types: Per-link transform types, aligned with grades.
            is_complete: Whether the chain has no gaps (ittiṣāl holds).
            corroboration_support: Whether independent corroboration supports
                the claim, allowing generative links to raise the floor.
            link_adalah_grades: Optional per-link ʿadālah (integrity) grades,
                aligned with link_narrator_grades. Kept as a separate axis
                (issue #11): a narrator with a good precision/accuracy grade
                but COMPROMISED integrity still poisons the chain — integrity
                failure is not something a strong NarratorGrade can offset.
            link_fidelity_verdicts: Optional per-link transformation-fidelity
                verdicts (see core/fidelity.py), aligned with
                link_narrator_grades. A third axis, distinct from both of the
                above: does this specific generative link's output actually
                follow from its own input, right now — not the narrator's
                general track record. CONTRADICTION caps that link's
                contribution at DAIF regardless of NarratorGrade (issue #11,
                direction 3: surface *where* a chain degraded).

        Returns:
            The computed ChainGrade.
        """
        if not link_narrator_grades:
            return ChainGrade.DAIF  # empty chain is effectively munqaṭiʿ

        # --- Incomplete chain → capped at DAIF (paper §4.1, commitment 4) ---
        if not is_complete:
            return ChainGrade.DAIF

        # --- Any REJECTED narrator → MAWDU immediately ---
        if NarratorGrade.REJECTED in link_narrator_grades:
            return ChainGrade.MAWDU

        # --- Any COMPROMISED ʿadālah → MAWDU immediately ---
        # A separate axis from NarratorGrade on purpose (issue #11): integrity
        # failure poisons the chain even when the collapsed NarratorGrade for
        # that narrator still looks acceptable.
        if link_adalah_grades and AdalahGrade.COMPROMISED in link_adalah_grades:
            return ChainGrade.MAWDU

        fidelity = link_fidelity_verdicts or [ContentVerdict.UNVERIFIABLE] * len(
            link_narrator_grades
        )

        # --- Walk the chain, maintaining a running floor ---
        # Start at SAHIH — no floor yet, best possible grade
        floor: ChainGrade = ChainGrade.SAHIH

        for narrator_grade, transform_type, fidelity_verdict in zip(
            link_narrator_grades, link_transform_types, fidelity, strict=True
        ):
            link_equiv = _narrator_to_chain_grade(narrator_grade)

            # Transformation fidelity: this specific output contradicted its
            # own input — cap this link's contribution regardless of the
            # narrator's general NarratorGrade. This runs before the
            # transform-type logic below, so a contradicted generative link
            # also can't raise the floor via corroboration (its capped grade
            # no longer clears is_at_least_acceptable).
            if fidelity_verdict == ContentVerdict.CONTRADICTION:
                link_equiv = ChainGrade.min(link_equiv, ChainGrade.DAIF)

            if transform_type == TransformType.DESTRUCTIVE:
                # Destructive: permanent floor at this link's grade
                # Information was lost; nothing downstream recovers it
                floor = ChainGrade.min(floor, link_equiv)

            elif transform_type == TransformType.GENERATIVE:
                if corroboration_support and narrator_grade.is_at_least_acceptable:
                    # Generative with corroboration and adequate grade:
                    # this link REPLACES the floor with its own grade.
                    # It can repair upstream damage (raise a lowered floor)
                    # OR introduce corruption (lower a high floor).
                    # Note: link_equiv was already capped at DAIF above if this
                    # link's own fidelity verdict was CONTRADICTION, so a
                    # contradicted generative link can never use this branch
                    # to raise the floor past DAIF — it can only lower it.
                    floor = link_equiv
                else:
                    # Without corroboration, or WEAK generative:
                    # standard minimum — can only lower, never raise
                    floor = ChainGrade.min(floor, link_equiv)

            else:  # PASS_THROUGH
                # Standard minimum — identity-like transformation
                floor = ChainGrade.min(floor, link_equiv)

        return floor


# ===========================================================================
# Convenience function: grade a claim chain using the default strategy
# ===========================================================================


def grade_chain(
    link_narrator_grades: list[NarratorGrade],
    link_transform_types: list[TransformType],
    is_complete: bool,
    *,
    strategy: GradingStrategy | None = None,
    corroboration_support: bool = False,
    link_adalah_grades: list[AdalahGrade] | None = None,
    link_fidelity_verdicts: list[ContentVerdict] | None = None,
) -> ChainGrade:
    """Grade a claim chain.

    Args:
        link_narrator_grades: Per-link narrator grades.
        link_transform_types: Per-link transform types.
        is_complete: Chain completeness (ittiṣāl).
        strategy: Optional custom GradingStrategy.
        corroboration_support: Whether corroboration supports the claim.
        link_adalah_grades: Optional per-link ʿadālah (integrity) grades —
            see RefinedWeakestLink.compute_chain_grade for details.
        link_fidelity_verdicts: Optional per-link transformation-fidelity
            verdicts (core/fidelity.py) — see
            RefinedWeakestLink.compute_chain_grade for details.

    Returns:
        ChainGrade for the claim.
    """
    strat = strategy or RefinedWeakestLink()
    return strat.compute_chain_grade(
        link_narrator_grades=link_narrator_grades,
        link_transform_types=link_transform_types,
        is_complete=is_complete,
        corroboration_support=corroboration_support,
        link_adalah_grades=link_adalah_grades,
        link_fidelity_verdicts=link_fidelity_verdicts,
    )
