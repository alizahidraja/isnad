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
    """Default corroboration policy: information-theoretic, capped, minimum-gated.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.3).  Swap freely.

    Uses HadithRank-style information-theoretic corroboration:
    multiple independent transmission chains asserting the same claim
    reduce the combined error probability multiplicatively.

    Rules:
    - Base grade is the grade of the chain under evaluation.
    - Corroboration can upgrade at most one tier.
    - Corroboration can never reach SAHIH (automatically capped).
    - At least one independent corroborating chain must be HASAN or above
      (minimum gate).
    - Chains with independence_score below INDEPENDENCE_THRESHOLD (0.8)
      are excluded: correlated chains do not count as independent.
    - All independent chains (including DAIF) contribute to the
      combined error reduction; even weak corroboration adds weight.
    - The combined log-error ratio must reach MIN_EFFECTIVE_WEIGHT
      for an upgrade to fire.
    """

    # Error probabilities per grade tier (HadithRank calibration).
    # These are reference defaults — calibrate for your domain.
    ERROR_PROBS: dict[ChainGrade, float] = {
        ChainGrade.SAHIH: 0.01,
        ChainGrade.HASAN: 0.10,
        ChainGrade.DAIF: 0.30,
        ChainGrade.MAWDU: 0.90,
    }

    MAX_UPGRADE_TIERS: int = 1
    MIN_GATE_GRADE: ChainGrade = ChainGrade.HASAN
    INDEPENDENCE_THRESHOLD: float = 0.8
    MIN_EFFECTIVE_WEIGHT: float = 2.0  # need ≥2 HASAN-equivalent chains of evidence

    # ── public API ──────────────────────────────────────────────────────

    def compute_corroborated_grade(
        self,
        base_grade: ChainGrade,
        corroborating_chains: list[ChainGrade],
        independence_scores: list[float],
    ) -> ChainGrade:
        """Compute the corroboration-upgraded chain grade.

        Uses information-theoretic error multiplication:
        combined_log_error = Σ ln(p_i)  for each independent chain + base.
        effective_weight = combined_log_error / ln(p_hasan).
        Upgrade fires when effective_weight ≥ MIN_EFFECTIVE_WEIGHT.

        Args:
            base_grade: Grade of the chain being evaluated.
            corroborating_chains: Grades of corroborating chains.
            independence_scores: Independence score for each corroborating
                chain relative to the base chain.  Must be same length.

        Returns:
            The new ChainGrade after corroboration.
        """
        import math

        if not corroborating_chains:
            return base_grade

        # --- Already MAWDU → cannot be upgraded ---
        if base_grade == ChainGrade.MAWDU:
            return base_grade

        # --- Filter: only chains that pass independence threshold ---
        independent_grades: list[ChainGrade] = []
        for grade, score in zip(
            corroborating_chains, independence_scores, strict=True
        ):
            if score >= self.INDEPENDENCE_THRESHOLD:
                independent_grades.append(grade)

        if not independent_grades:
            return base_grade

        # --- Minimum-grade gate: at least one chain must clear threshold ---
        if not any(g >= self.MIN_GATE_GRADE for g in independent_grades):
            return base_grade

        # --- Information-theoretic corroboration ---
        # Each chain at grade G_i has an implied error probability p_i.
        # Combined error ∝ ∏ p_i (multiplicative reduction).
        # Effective weight = log-reduction normalised by HASAN baseline.
        err = self.ERROR_PROBS
        combined_log_error = sum(
            math.log(max(err.get(g, 0.30), 0.001)) for g in independent_grades
        )
        combined_log_error += math.log(max(err.get(base_grade, 0.30), 0.001))

        hasan_log = math.log(err[ChainGrade.HASAN])
        effective_weight = combined_log_error / max(hasan_log, -10.0)

        if effective_weight < self.MIN_EFFECTIVE_WEIGHT:
            return base_grade

        # --- Upgrade: at most one tier, never to SAHIH ---
        if base_grade == ChainGrade.DAIF:
            return ChainGrade.HASAN  # DAIF → HASAN (cap)
        # HASAN stays HASAN; SAHIH stays SAHIH
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
# CorroborationEngine — delegates grade math to CappedCorroborationPolicy
# ===========================================================================

"""Corroboration Engine — operational mutābaʿāt (independent-chain upgrade).

Finds corroborating chains across a corpus, checks independence via
SharedLineageDetector, and delegates the grade-upgrade decision to
CappedCorroborationPolicy (information-theoretic error multiplication).

Key rules (paper §4.3):
- Chains must be truly independent (disjoint narrator sets, different sources)
- Upgrade is capped below SAHIH (cannot reach sound tier via corroboration alone)
- Minimum-grade gate: at least one corroborating chain must clear threshold
- Correlation discount: shared model family / upstream source → partial weight

Matching is exact on claim_text.  For semantic / embedding-based matching
pre-process claims externally and canonicalise to a shared key before
passing to this engine.
"""


import math
from dataclasses import dataclass

from isnad.types import ChainGrade, NarratorGrade


@dataclass
class CorroborationResult:
    """Result of a corroboration check."""

    base_grade: ChainGrade
    upgraded_grade: ChainGrade
    corroborating_chains: int  # matching chains (excl. base chain itself)
    independent_chains: int    # after correlation discount
    effective_weight: float    # info-theoretic log-error ratio
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
    information-theoretic corroboration upgrade via CappedCorroborationPolicy.

    Usage:
        engine = CorroborationEngine(min_independent_chains=1)
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
        min_independent_chains: int = 1,
        corroboration_cap: ChainGrade = ChainGrade.HASAN,
        min_gate_grade: ChainGrade = ChainGrade.HASAN,
        correlation_detector: SharedLineageDetector | None = None,
        policy: CappedCorroborationPolicy | None = None,
    ):
        """Args:
            min_independent_chains: Minimum number of *corroborating*
                (not counting the base) independent chains required.
                Default 1 = one corroborating chain + base = two total.
            corroboration_cap: Highest grade reachable via corroboration.
            min_gate_grade: At least one corroborating chain must meet
                this grade for upgrade to be considered.
            correlation_detector: Optional custom SharedLineageDetector.
            policy: Optional custom CappedCorroborationPolicy for the
                upgrade decision math.
        """
        self.min_independent_chains = min_independent_chains
        self.corroboration_cap = corroboration_cap
        self.min_gate_grade = min_gate_grade
        self._correlation_detector = correlation_detector or SharedLineageDetector()
        self._policy = policy or CappedCorroborationPolicy()

    def evaluate(
        self,
        claim_text: str,
        base_chain_grade: ChainGrade,
        base_narrators: list[str],
        all_chains: list[dict],
        narrator_metadata: dict[str, dict] | None = None,
    ) -> CorroborationResult:
        """Evaluate corroboration for a claim.

        Matching is exact on claim_text.  Pre-canonicalise claims that
        are semantically equivalent but textually different before
        calling this method.

        Args:
            claim_text: Normalized claim text (exact match).
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

        # Find corroborating chains — exclude the base chain itself
        base_narrator_set = set(base_narrators)
        corroborating = []
        for chain in all_chains:
            if chain.get("claim_text", "") != claim_text:
                continue
            # Exclude the base chain (same narrator set)
            if set(chain.get("narrator_ids", [])) == base_narrator_set:
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
            if self._correlation_detector.are_independent(
                base_narrators, c["narrators"], narrator_metadata or {}
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
                reason=(
                    f"Need ≥{self.min_independent_chains} independent chains, "
                    f"have {len(independent)}"
                ),
            )

        # Minimum-grade gate: at least one chain must clear threshold
        if not any(c["grade"] >= self.min_gate_grade for c in independent):
            return CorroborationResult(
                base_grade=base_chain_grade,
                upgraded_grade=base_chain_grade,
                corroborating_chains=len(corroborating),
                independent_chains=len(independent),
                effective_weight=0.0,
                upgraded=False,
                reason=f"No corroborating chain meets min grade {self.min_gate_grade.value}",
            )

        # Delegate grade computation to CappedCorroborationPolicy
        independence_scores = [
            self._correlation_detector.compute_independence_score(
                base_narrators, c["narrators"], narrator_metadata or {}
            )
            for c in independent
        ]
        corroborating_grades = [c["grade"] for c in independent]

        upgraded = self._policy.compute_corroborated_grade(
            base_grade=base_chain_grade,
            corroborating_chains=corroborating_grades,
            independence_scores=independence_scores,
        )

        # Compute effective weight for reporting
        err = self._policy.ERROR_PROBS
        combined_log = sum(
            math.log(max(err.get(g, 0.30), 0.001)) for g in corroborating_grades
        )
        combined_log += math.log(max(err.get(base_chain_grade, 0.30), 0.001))
        hasan_log = math.log(err[ChainGrade.HASAN])
        effective_weight = combined_log / max(hasan_log, -10.0)

        upgraded_flag = upgraded != base_chain_grade

        return CorroborationResult(
            base_grade=base_chain_grade,
            upgraded_grade=upgraded,
            corroborating_chains=len(corroborating),
            independent_chains=len(independent),
            effective_weight=effective_weight,
            upgraded=upgraded_flag,
            reason=(
                f"Upgraded via {len(independent)} independent chains "
                f"(effective weight={effective_weight:.1f})"
                if upgraded_flag
                else (
                    f"Effective weight {effective_weight:.1f} < "
                    f"{self._policy.MIN_EFFECTIVE_WEIGHT}"
                )
            ),
        )
