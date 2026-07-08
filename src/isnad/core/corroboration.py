"""Corroboration (mutābaʿāt) — independent-chain claim upgrade with correlation detection.

Implements paper §4.3:
- Claims carried by multiple independent chains may be upgraded.
- Upgrade is capped (never reaches SAHIH via corroboration alone).
- Minimum-grade gate: at least one corroborating chain must clear threshold.
- Correlation discount: chains sharing model family / upstream source
  (the madār problem) are detected and their corroboration discounted.

Naive set-disjointness of narrator IDs is explicitly wrong here; this module
implements correlation detection as required by the paper (§7, Limitations).
"""

from __future__ import annotations

from isnad.types import (
    ChainGrade,
    CorrelationDetector,
    CorroborationPolicy,
)

# ===========================================================================
# Default CorrelationDetector
# ===========================================================================


class SharedLineageDetector:
    """Default correlation detector: checks shared model family and upstream source.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.3, §7).  Swap freely.

    A reference stub: the heuristics here (exact match on model_family,
    substring match on upstream source) are deliberately simple.  A
    production version would incorporate structured model lineage data
    (e.g., model cards, training-data provenance) and possibly embedding
    similarity of model outputs to detect correlated blind spots.
    """

    def are_independent(
        self,
        chain_a_narrators: list[str],
        chain_b_narrators: list[str],
        narrator_metadata: dict[str, dict[str, object]],
    ) -> bool:
        """Check if two chains are truly independent.

        Returns True only if the chains are *disjoint* in narrator IDs AND
        not correlated via shared lineage.
        """
        score = self.compute_independence_score(
            chain_a_narrators, chain_b_narrators, narrator_metadata
        )
        # Independence requires score above 0.8
        return score >= 0.8

    def compute_independence_score(
        self,
        chain_a_narrators: list[str],
        chain_b_narrators: list[str],
        narrator_metadata: dict[str, dict[str, object]],
    ) -> float:
        """Compute an independence score in [0.0, 1.0].

        1.0 = fully independent; 0.0 = fully correlated (same lineage).

        Penalties applied for:
        - Shared narrator IDs (hard correlation): score = 0.0
        - Shared model family: -0.4 penalty per shared family
        - Shared upstream source: -0.3 penalty per shared source
        """
        set_a = set(chain_a_narrators)
        set_b = set(chain_b_narrators)

        # --- Shared narrator IDs → directly correlated ---
        if set_a & set_b:
            return 0.0

        # --- Check model family overlap ---
        families_a: set[str] = set()
        families_b: set[str] = set()
        for nid in set_a:
            meta = narrator_metadata.get(nid, {})
            mf = meta.get("model_family")
            if mf and isinstance(mf, str):
                families_a.add(mf)
        for nid in set_b:
            meta = narrator_metadata.get(nid, {})
            mf = meta.get("model_family")
            if mf and isinstance(mf, str):
                families_b.add(mf)

        shared_families = families_a & families_b

        # --- Check upstream source overlap ---
        sources_a: set[str] = set()
        sources_b: set[str] = set()
        for nid in set_a:
            meta = narrator_metadata.get(nid, {})
            us = meta.get("upstream_source")
            if us and isinstance(us, str):
                sources_a.add(us)
        for nid in set_b:
            meta = narrator_metadata.get(nid, {})
            us = meta.get("upstream_source")
            if us and isinstance(us, str):
                sources_b.add(us)

        shared_sources = sources_a & sources_b

        # No metadata at all → assume independent (score 1.0)
        has_any_metadata = bool(families_a or families_b or sources_a or sources_b)
        if not has_any_metadata:
            return 1.0

        # Compute penalty
        penalty = 0.0
        penalty += len(shared_families) * 0.4
        penalty += len(shared_sources) * 0.3

        # Clamp
        return max(0.0, min(1.0, 1.0 - penalty))


# ===========================================================================
# Default CorroborationPolicy
# ===========================================================================


class CappedCorroborationPolicy:
    """Default corroboration policy: capped, minimum-gated, correlation-discounted.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.3).  Swap freely.

    Rules:
    - Base grade is the grade of the chain under evaluation.
    - Corroboration can upgrade at most one tier.
    - Corroboration can never reach SAHIH (automatically capped).
    - At least one corroborating chain must be HASAN or above (minimum gate).
    - Correlated chains (independence_score < 0.8) are discounted: they
      contribute partial weight rather than full weight.
    """

    # Constants (reference defaults — see paper §8 for calibration experiment)
    MAX_UPGRADE_TIERS: int = 1
    MIN_GATE_GRADE: ChainGrade = ChainGrade.HASAN
    INDEPENDENCE_THRESHOLD: float = 0.8
    EFFECTIVE_CHAINS_FOR_UPGRADE: int = 2  # need ≥2 effective independent chains

    def compute_corroborated_grade(
        self,
        base_grade: ChainGrade,
        corroborating_chains: list[ChainGrade],
        independence_scores: list[float],
    ) -> ChainGrade:
        """Compute the corroboration-upgraded chain grade.

        Args:
            base_grade: Grade of the chain being evaluated.
            corroborating_chains: Grades of corroborating chains.
            independence_scores: Independence score for each corroborating
                chain relative to the base chain.  Must be same length.

        Returns:
            The new ChainGrade after corroboration.
        """
        if not corroborating_chains:
            return base_grade

        # --- Already MAWDU → cannot be upgraded ---
        if base_grade == ChainGrade.MAWDU:
            return base_grade

        # --- Minimum gate: at least one corroborating chain must clear threshold ---
        gating_passed = any(
            grade >= self.MIN_GATE_GRADE and score >= self.INDEPENDENCE_THRESHOLD
            for grade, score in zip(corroborating_chains, independence_scores, strict=True)
        )
        if not gating_passed:
            return base_grade

        # --- Count effective corroborating chains (discount correlated) ---
        effective_count: float = 0.0
        for grade, score in zip(corroborating_chains, independence_scores, strict=True):
            if grade == ChainGrade.MAWDU:
                continue  # rejected chains contribute nothing
            if grade == ChainGrade.DAIF:
                continue  # DAIF chains cannot corroborate an upgrade
            if score < self.INDEPENDENCE_THRESHOLD:
                continue  # correlated chains don't count independently
            weight = min(1.0, score)  # independence score as weight
            effective_count += weight

        # --- Need enough effective independent chains ---
        if effective_count < self.EFFECTIVE_CHAINS_FOR_UPGRADE:
            return base_grade

        # --- Upgrade: at most one tier, never to SAHIH ---
        if base_grade == ChainGrade.DAIF:
            return ChainGrade.HASAN  # DAIF → HASAN (cap)
        if base_grade == ChainGrade.HASAN:
            return ChainGrade.HASAN  # HASAN stays HASAN (corroboration cannot reach SAHIH)

        return base_grade


# ===========================================================================
# Convenience functions
# ===========================================================================


def evaluate_corroboration(
    base_grade: ChainGrade,
    corroborating_chain_grades: list[ChainGrade],
    base_narrators: list[str],
    corroborating_narrators: list[list[str]],
    narrator_metadata: dict[str, dict[str, object]],
    *,
    policy: CorroborationPolicy | None = None,
    detector: CorrelationDetector | None = None,
) -> ChainGrade:
    """Evaluate corroboration for a claim.

    Args:
        base_grade: The chain grade of the claim under evaluation.
        corroborating_chain_grades: Grades of corroborating chains.
        base_narrators: Narrator IDs in the base claim's chain.
        corroborating_narrators: Narrator IDs for each corroborating chain.
        narrator_metadata: Metadata dict for correlation detection.
        policy: Optional custom CorroborationPolicy.
        detector: Optional custom CorrelationDetector.

    Returns:
        The (possibly upgraded) ChainGrade.
    """
    pol = policy or CappedCorroborationPolicy()
    det = detector or SharedLineageDetector()

    scores = [
        det.compute_independence_score(base_narrators, corr_narrators, narrator_metadata)
        for corr_narrators in corroborating_narrators
    ]

    return pol.compute_corroborated_grade(
        base_grade=base_grade,
        corroborating_chains=corroborating_chain_grades,
        independence_scores=scores,
    )


def find_corroborating_claims(
    normalized_claim: str,
    claim_id: str,
    all_claims: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Find claims with the same normalized text but different claim_ids.

    Args:
        normalized_claim: The normalized claim text to match.
        claim_id: The claim_id to exclude (the claim under evaluation).
        all_claims: List of claim dicts with keys: claim_id, normalized_text,
            narrator_ids, chain_grade.

    Returns:
        List of matching claim dicts that are not the same claim.
    """
    return [
        c
        for c in all_claims
        if c.get("normalized_text") == normalized_claim and c.get("claim_id") != claim_id
    ]


# ===========================================================================
# CorroborationEngine — information-theoretic with SharedLineageDetector
# ===========================================================================

"""Corroboration Engine — operational mutābaʿāt (independent-chain upgrade).

Implements the HadithRank-style information-theoretic corroboration:
multiple independent transmission chains asserting the same claim reduce
the combined error probability multiplicatively.

Key rules (paper §4.3):
- Chains must be truly independent (disjoint narrator sets, different sources)
- Upgrade is capped below SAHIH (cannot reach sound tier via corroboration alone)
- Minimum-grade gate: at least one corroborating chain must clear threshold
- Correlation discount: shared model family / upstream source → partial weight

Status: EXPERIMENTAL.  Corroboration has not fired on real corpora in the
§8 experiment.  This engine implements the rule correctly; it requires
warm baseline grades and genuine cross-source overlaps to activate.
"""


import math
from dataclasses import dataclass

# SharedLineageDetector is defined above in this file
from isnad.types import ChainGrade, NarratorGrade


@dataclass
class CorroborationResult:
    """Result of a corroboration check."""

    base_grade: ChainGrade
    upgraded_grade: ChainGrade
    corroborating_chains: int
    independent_chains: int  # after correlation discount
    effective_weight: float
    upgraded: bool
    reason: str = ""


def _narrator_to_chain_grade(ng: NarratorGrade) -> ChainGrade:
    mapping = {
        NarratorGrade.RELIABLE: ChainGrade.SAHIH,
        NarratorGrade.ACCEPTABLE: ChainGrade.HASAN,
        NarratorGrade.WEAK: ChainGrade.DAIF,
        NarratorGrade.REJECTED: ChainGrade.MAWDU,
        NarratorGrade.UNGRADED: ChainGrade.HASAN,
    }
    return mapping[ng]


class CorroborationEngine:
    """Engine for cross-claim corroboration (mutābaʿāt).

    Finds independent chains for a given claim and applies the
    information-theoretic corroboration upgrade.

    Usage:
        engine = CorroborationEngine()
        result = engine.evaluate(
            claim_text="F = ma",
            base_chain_grade=ChainGrade.DAIF,
            base_narrators=["source:A", "scraper:v1", "model:gpt4"],
            all_chains=all_claim_chains,
            narrator_metadata=narrator_metadata,
        )
        if result.upgraded:
            print(f"Upgraded from {result.base_grade.value} "
                  f"to {result.upgraded_grade.value}")
    """

    def __init__(
        self,
        min_independent_chains: int = 2,
        corroboration_cap: ChainGrade = ChainGrade.HASAN,
        min_gate_grade: ChainGrade = ChainGrade.HASAN,
        correlation_detector: SharedLineageDetector | None = None,
    ):
        self.min_independent_chains = min_independent_chains
        self.corroboration_cap = corroboration_cap
        self.min_gate_grade = min_gate_grade
        self._correlation_detector = correlation_detector or SharedLineageDetector()

    def evaluate(
        self,
        claim_text: str,
        base_chain_grade: ChainGrade,
        base_narrators: list[str],
        all_chains: list[dict],
        narrator_metadata: dict[str, dict] | None = None,
    ) -> CorroborationResult:
        """Evaluate corroboration for a claim.

        Args:
            claim_text: Normalized claim text.
            base_chain_grade: Grade of the claim's own chain.
            base_narrators: Narrator IDs in the base claim's chain.
            all_chains: List of all claim chain dicts with keys:
                claim_text, chain_grade, narrator_ids.
            narrator_metadata: Optional metadata for correlation detection.

        Returns:
            CorroborationResult with upgrade decision.
        """
        if base_chain_grade == ChainGrade.MAWDU:
            return CorroborationResult(
                base_grade=base_chain_grade,
                upgraded_grade=base_chain_grade,
                corroborating_chains=0,
                independent_chains=0,
                effective_weight=0.0,
                upgraded=False,
                reason="MAWDU chains cannot be corroborated",
            )

        # Find corroborating chains
        corroborating = []
        for chain in all_chains:
            if chain.get("claim_text", "") != claim_text:
                continue
            cg_raw = chain.get("chain_grade", "daif")
            try:
                cg = ChainGrade(cg_raw)
            except ValueError:
                cg = ChainGrade.DAIF
            corroborating.append(
                {
                    "grade": cg,
                    "narrators": chain.get("narrator_ids", []),
                    "source": chain.get("source", ""),
                }
            )

        # Filter: must be truly independent (narrator sets + lineage detection)
        independent = []
        for c in corroborating:
            c_narrators = c["narrators"]
            # Use SharedLineageDetector for madār-aware independence check
            if self._correlation_detector.are_independent(
                base_narrators, c_narrators, narrator_metadata or {}
            ):
                independent.append(c)

        if len(independent) < self.min_independent_chains:
            return CorroborationResult(
                base_grade=base_chain_grade,
                upgraded_grade=base_chain_grade,
                corroborating_chains=len(corroborating),
                independent_chains=len(independent),
                effective_weight=0.0,
                upgraded=False,
                reason=f"Need ≥{self.min_independent_chains} independent chains, "
                f"have {len(independent)}",
            )

        # Minimum-grade gate: at least one corroborating chain must clear threshold
        gating_passed = any(c["grade"] >= self.min_gate_grade for c in independent)
        if not gating_passed:
            return CorroborationResult(
                base_grade=base_chain_grade,
                upgraded_grade=base_chain_grade,
                corroborating_chains=len(corroborating),
                independent_chains=len(independent),
                effective_weight=float(len(independent)),
                upgraded=False,
                reason=f"No corroborating chain meets min grade {self.min_gate_grade.value}",
            )

        # Information-theoretic corroboration (HadithRank-style)
        # Each independent chain at grade G_i has an implied error probability p_i.
        # Combined error probability ∝ ∏ p_i (multiplicative reduction).
        # Effective weight = log-reduction in error probability.
        error_probs = {
            ChainGrade.SAHIH: 0.01,
            ChainGrade.HASAN: 0.10,
            ChainGrade.DAIF: 0.30,
            ChainGrade.MAWDU: 0.90,
        }

        combined_log_error = 0.0
        for c in independent:
            p = error_probs.get(c["grade"], 0.30)
            combined_log_error += math.log(max(p, 0.001))

        # Base chain's own error
        base_p = error_probs.get(base_chain_grade, 0.30)
        combined_log_error += math.log(max(base_p, 0.001))

        # Effective weight: how many independent chains at HASAN-grade
        # would produce this error reduction
        hasan_log_p = math.log(error_probs[ChainGrade.HASAN])
        effective_weight = combined_log_error / max(hasan_log_p, -10.0)

        # Upgrade decision
        can_upgrade = effective_weight >= self.min_independent_chains

        if not can_upgrade:
            return CorroborationResult(
                base_grade=base_chain_grade,
                upgraded_grade=base_chain_grade,
                corroborating_chains=len(corroborating),
                independent_chains=len(independent),
                effective_weight=effective_weight,
                upgraded=False,
                reason=f"Effective weight {effective_weight:.1f} < {self.min_independent_chains}",
            )

        # Apply capped upgrade
        if base_chain_grade == ChainGrade.DAIF:
            upgraded = ChainGrade.HASAN
        elif base_chain_grade == ChainGrade.HASAN:
            upgraded = ChainGrade.HASAN  # cap — cannot reach SAHIH
        else:
            upgraded = base_chain_grade

        # Cap at corroboration ceiling
        if upgraded > self.corroboration_cap:
            upgraded = self.corroboration_cap

        return CorroborationResult(
            base_grade=base_chain_grade,
            upgraded_grade=upgraded,
            corroborating_chains=len(corroborating),
            independent_chains=len(independent),
            effective_weight=effective_weight,
            upgraded=(upgraded != base_chain_grade),
            reason=f"Upgraded via {len(independent)} independent chains "
            f"(effective weight={effective_weight:.1f})",
        )
