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
    ChainGrade,
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
    ) -> ChainGrade:
        """Compute the chain grade by walking the chain link-by-link.

        Args:
            link_narrator_grades: Per-link narrator grades, in chain order.
            link_transform_types: Per-link transform types, aligned with grades.
            is_complete: Whether the chain has no gaps (ittiṣāl holds).
            corroboration_support: Whether independent corroboration supports
                the claim, allowing generative links to raise the floor.

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

        # --- Walk the chain, maintaining a running floor ---
        # Start at SAHIH — no floor yet, best possible grade
        floor: ChainGrade = ChainGrade.SAHIH

        for narrator_grade, transform_type in zip(
            link_narrator_grades, link_transform_types, strict=True
        ):
            link_equiv = _narrator_to_chain_grade(narrator_grade)

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
) -> ChainGrade:
    """Grade a claim chain.

    Args:
        link_narrator_grades: Per-link narrator grades.
        link_transform_types: Per-link transform types.
        is_complete: Chain completeness (ittiṣāl).
        strategy: Optional custom GradingStrategy.
        corroboration_support: Whether corroboration supports the claim.

    Returns:
        ChainGrade for the claim.
    """
    strat = strategy or RefinedWeakestLink()
    return strat.compute_chain_grade(
        link_narrator_grades=link_narrator_grades,
        link_transform_types=link_transform_types,
        is_complete=is_complete,
        corroboration_support=corroboration_support,
    )
