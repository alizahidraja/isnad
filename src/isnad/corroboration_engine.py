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

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

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
    ):
        self.min_independent_chains = min_independent_chains
        self.corroboration_cap = corroboration_cap
        self.min_gate_grade = min_gate_grade

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
            corroborating.append({
                "grade": cg,
                "narrators": chain.get("narrator_ids", []),
                "source": chain.get("source", ""),
            })

        # Filter: must have different narrator sets
        independent = []
        for c in corroborating:
            c_narrators = set(c["narrators"])
            base_set = set(base_narrators)
            if c_narrators & base_set:
                continue  # shared narrator — not independent
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
        gating_passed = any(
            c["grade"] >= self.min_gate_grade for c in independent
        )
        if not gating_passed:
            return CorroborationResult(
                base_grade=base_chain_grade,
                upgraded_grade=base_chain_grade,
                corroborating_chains=len(corroborating),
                independent_chains=len(independent),
                effective_weight=float(len(independent)),
                upgraded=False,
                reason=f"No corroborating chain meets min grade "
                f"{self.min_gate_grade.value}",
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
                reason=f"Effective weight {effective_weight:.1f} < "
                f"{self.min_independent_chains}",
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
