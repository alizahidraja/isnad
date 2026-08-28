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

import math
from dataclasses import dataclass, field

from isnad.types import (
    ChainGrade,
    CorrelationDetector,
    CorroborationPolicy,
    NarratorGrade,
)

# ===========================================================================
# Default CorrelationDetector
# ===========================================================================


@dataclass(frozen=True)
class IndependenceAssessment:
    """A structured independence verdict: a score plus *which* signals fired.

    The score alone cannot answer "why were these chains correlated?" — a
    compliance buyer or reviewer needs the provenance.  ``shared_signals`` is a
    list of human-readable reasons (e.g. "shared model family: gpt-4-family"),
    empty when no shared signal was found.

    The score is the same value ``compute_independence_score`` returns; this
    dataclass exists so the detector can report *why* without a second call.
    """

    score: float
    shared_signals: tuple[str, ...]

    @property
    def is_independent(self) -> bool:
        """True when the score clears the corroboration gate (>= 0.8)."""
        return self.score >= 0.8


class SharedLineageDetector:
    """Default correlation detector: checks shared model family and upstream source.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.3, §7).  Swap freely.

    A reference stub: the heuristics here (exact match on model_family,
    substring match on upstream source) are deliberately simple.  A
    production version would incorporate structured model lineage data
    (e.g., model cards, training-data provenance) and possibly embedding
    similarity of model outputs to detect correlated blind spots.

    **Independence must be demonstrated, not assumed (issue #54).** Topology can
    only ever *falsify* independence (by finding a shared signal), never *prove*
    it — the paper's §7 concedes that a correlated pair sharing none of the three
    signals, and content-level correlated error, are undetectable here. So the
    detector distinguishes three cases, not two:

    - **Known-distinct lineage** — both chains carry lineage metadata and it
      differs → high independence (earned).
    - **Unknown lineage** — no metadata to reason about → ``UNKNOWN_LINEAGE_SCORE``,
      deliberately *below* the corroboration gate. Absent evidence of
      independence, the framework no longer assumes it (previously this returned
      1.0 — "most independent when we know least", the exact inversion issue #54
      warns against).
    - **Shared signal detected** → penalised toward 0.

    This is an honesty calibration, not a detection mechanism: it narrows the
    independence *assumption*, it does not claim to detect correlated blind spots.
    """

    # Independence we cannot rule out but also cannot demonstrate. Below the
    # default gate (0.8) so unattested chains do not silently corroborate; a
    # caller who can attest distinct lineage supplies metadata and clears it.
    UNKNOWN_LINEAGE_SCORE: float = 0.5

    def are_independent(
        self,
        chain_a_narrators: list[str],
        chain_b_narrators: list[str],
        narrator_metadata: dict[str, dict[str, object]],
        *,
        chain_a_document_hashes: set[str] | None = None,
        chain_b_document_hashes: set[str] | None = None,
    ) -> bool:
        """Check if two chains are truly independent.

        Returns True only if the chains are *disjoint* in narrator IDs AND
        not correlated via shared lineage or shared retrieval documents.

        ``chain_a_document_hashes`` / ``chain_b_document_hashes`` are optional
        sets of retrieved-document content hashes per chain. When both are
        provided, any overlap is hard correlation (the madār case: two chains
        reading the same source are one source). When absent, the document
        check is skipped and the lineage signals alone decide.
        """
        score = self.compute_independence_score(
            chain_a_narrators,
            chain_b_narrators,
            narrator_metadata,
            chain_a_document_hashes=chain_a_document_hashes,
            chain_b_document_hashes=chain_b_document_hashes,
        )
        # Independence requires score above 0.8
        return score >= 0.8

    def compute_independence_score(
        self,
        chain_a_narrators: list[str],
        chain_b_narrators: list[str],
        narrator_metadata: dict[str, dict[str, object]],
        *,
        chain_a_document_hashes: set[str] | None = None,
        chain_b_document_hashes: set[str] | None = None,
    ) -> float:
        """Compute an independence score in [0.0, 1.0].

        1.0 = demonstrably independent; 0.0 = fully correlated (same lineage
        or same retrieved documents); ``UNKNOWN_LINEAGE_SCORE`` = independence
        neither shown nor ruled out.

        Convenience wrapper over :meth:`detect` — see that method for the
        full signal semantics and for the *why* (provenance) when a non-zero
        penalty was applied.
        """
        return self.detect(
            chain_a_narrators,
            chain_b_narrators,
            narrator_metadata,
            chain_a_document_hashes=chain_a_document_hashes,
            chain_b_document_hashes=chain_b_document_hashes,
        ).score

    def detect(
        self,
        chain_a_narrators: list[str],
        chain_b_narrators: list[str],
        narrator_metadata: dict[str, dict[str, object]],
        *,
        chain_a_document_hashes: set[str] | None = None,
        chain_b_document_hashes: set[str] | None = None,
    ) -> IndependenceAssessment:
        """Compute an independence assessment: score plus which signals fired.

        Correlation signals, in order of severity (each adds a provenance entry):
        - Shared narrator IDs (hard): score = 0.0.
        - Shared retrieved-document hashes (hard, the madār case): score = 0.0.
          Two chains that retrieved the same document are one source regardless
          of model family. Requires both hash sets to be provided.
        - Shared model family: -0.4 penalty per shared family.
        - Shared upstream source: -0.3 penalty per shared source.

        With no lineage metadata on either side, independence cannot be
        demonstrated, so the score is ``UNKNOWN_LINEAGE_SCORE`` (below the gate),
        not 1.0 — see the class docstring and issue #54.

        Document hashes are a chain property, not a narrator property, so they
        arrive as optional keyword-only args rather than inside
        ``narrator_metadata``. ``None`` means "not provided" and skips the check;
        non-overlap is not evidence of independence and never raises the score.
        """
        set_a = set(chain_a_narrators)
        set_b = set(chain_b_narrators)

        # --- Shared narrator IDs → directly correlated ---
        shared_ids = set_a & set_b
        if shared_ids:
            return IndependenceAssessment(0.0, (f"shared narrator IDs: {sorted(shared_ids)}",))

        # --- Shared retrieved-document hashes → hard correlation (madār). ---
        # Checked before the unknown-lineage fallback: this is hard evidence
        # that dominates lineage metadata, and matches the callback's
        # SHARED_ANCESTRY_DETECTED verdict on any shared hash. If either set is
        # absent we have no information and fall through (no penalty, no bonus).
        if chain_a_document_hashes is not None and chain_b_document_hashes is not None:
            shared_hashes = set(chain_a_document_hashes) & set(chain_b_document_hashes)
            if shared_hashes:
                return IndependenceAssessment(
                    0.0, (f"shared retrieved document hash: {sorted(shared_hashes)}",)
                )

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

        # Independence must be *demonstrable* to score high. That needs lineage
        # metadata on BOTH sides so a difference can actually be observed. If
        # either side is missing it, distinctness is unknown → below-gate score
        # (issue #54). Previously this returned 1.0 whenever no metadata existed
        # at all — assuming independence exactly when least was known.
        side_a_known = bool(families_a or sources_a)
        side_b_known = bool(families_b or sources_b)
        if not (side_a_known and side_b_known):
            # Unknown lineage is NOT a shared signal — it is a distinct
            # "cannot tell" case. shared_signals stays empty so callers can
            # distinguish "correlation found" (non-empty signals) from
            # "independence unprovable" (empty signals, score 0.5).
            return IndependenceAssessment(self.UNKNOWN_LINEAGE_SCORE, ())

        # Compute penalty
        signals: list[str] = []
        penalty = 0.0
        for fam in sorted(shared_families):
            penalty += 0.4
            signals.append(f"shared model family: {fam}")
        for src in sorted(shared_sources):
            penalty += 0.3
            signals.append(f"shared upstream source: {src}")

        # Clamp
        score = max(0.0, min(1.0, 1.0 - penalty))
        return IndependenceAssessment(score, tuple(signals))


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
    - Chains above the threshold earn credit in proportion to their
      independence score (the disjointness discount, #125 tier 1): a chain
      at 0.85 contributes 85% of a full chain's log-error reduction.
    - **The tawātur discount (#54).** Even a chain with independence score 1.0
      is not a full independent witness, because two agents can share an
      *unobservable* correlated failure (shared training data, shared blind
      spot) that no topology check can see. Classical tawātur never tried to
      *prove* per-pair independence; it required a number of reporters large
      enough that collusion on a falsehood was inconceivable. The computational
      translation is an explicit prior ``shared_blind_spot_prior`` — the
      probability that a nominally-independent chain shares a failure mode with
      the base chain — which discounts every chain's witness weight. Default is
      conservatively high (0.20); an operator who can *attest* distinct lineage
      (#47) or exchange evidence (#44) lowers it.
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

    MIN_GATE_GRADE: ChainGrade = ChainGrade.HASAN
    INDEPENDENCE_THRESHOLD: float = 0.8
    MIN_EFFECTIVE_WEIGHT: float = 2.0  # need ≥2 HASAN-equivalent chains of evidence

    # The witness-type-aware blind-spot prior (#54, mutābaʿa vs shāhid).
    #
    # Classical corroboration was NOT uniform: a mutābaʿa (a narrator confirming
    # from the same teacher) is weak corroboration, while a shāhid (a *different*
    # companion confirming the same meaning) is strong. The computational
    # translation: two witnesses of the SAME kind (two LLMs, both trained on
    # internet text) share a high prior probability of a correlated blind spot;
    # two witnesses of DIFFERENT kinds (a model and a human reviewer, a model
    # and a cryptographically-sealed source) share a far lower prior.
    #
    # These are STATED DEFAULTS, not truths — each cell is an assumption to be
    # calibrated, never asserted as fact. The matrix is keyed by narrator type
    # (NarratorType.value); an unknown type falls back to the flat
    # ``shared_blind_spot_prior``.
    BLIND_SPOT_MATRIX: dict[tuple[str, str], float] = {
        # same-kind: high prior — shared training lineage, shared blind spots
        ("model", "model"): 0.25,
        ("scraper", "scraper"): 0.15,
        ("source", "source"): 0.10,  # sources can still mirror the same received error
        ("tool", "tool"): 0.15,
        # cross-kind: low prior — qualitatively different failure modes
        ("model", "human"): 0.05,
        ("human", "model"): 0.05,
        ("model", "source"): 0.08,
        ("source", "model"): 0.08,
        ("model", "scraper"): 0.10,
        ("scraper", "model"): 0.10,
        ("human", "source"): 0.02,
        ("source", "human"): 0.02,
    }

    def blind_spot_prior_for(self, base_type: str | None, corr_type: str | None) -> float:
        """The blind-spot prior for a base witness and a corroborating witness.

        Looks up the witness-type matrix; falls back to the flat
        ``shared_blind_spot_prior`` when either type is unknown or the pair is
        not in the matrix. This is the shāhid/mutābaʿa distinction made explicit:
        cross-kind corroboration is charged a smaller honesty discount.
        """
        if base_type is None or corr_type is None:
            return self.shared_blind_spot_prior
        return self.BLIND_SPOT_MATRIX.get((base_type, corr_type), self.shared_blind_spot_prior)

    def __init__(self, *, shared_blind_spot_prior: float = 0.20):
        """Args:
        shared_blind_spot_prior: the prior probability (0.0–1.0) that a
            nominally-independent chain shares an *unobservable* correlated
            failure with the base chain — shared training data, a shared
            blind spot, a shared received error. This is the tawātur
            discount (#54): it is never zero, because topology cannot prove
            independence. Operators with attestation (#47) or evidence
            exchange (#44) may lower it; it must not be silently assumed
            away.
        """
        self.shared_blind_spot_prior = max(0.0, min(1.0, shared_blind_spot_prior))

    # ── public API ──────────────────────────────────────────────────────

    def compute_corroborated_grade(
        self,
        base_grade: ChainGrade,
        corroborating_chains: list[ChainGrade],
        independence_scores: list[float],
        *,
        chain_blind_spot_priors: list[float] | None = None,
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
            chain_blind_spot_priors: Optional per-chain tawātur priors (one per
                corroborating chain). When omitted, the flat
                ``shared_blind_spot_prior`` is used for every chain. This is
                the shāhid/mutābaʿa distinction: cross-kind witnesses get a
                lower prior than same-kind witnesses.

        Returns:
            The new ChainGrade after corroboration.
        """
        if not corroborating_chains:
            return base_grade

        # --- Already MAWDU → cannot be upgraded ---
        if base_grade == ChainGrade.MAWDU:
            return base_grade

        # --- Filter: only chains that pass independence threshold. ---
        # Keep (grade, score, prior) triples so the disjointness discount and
        # the per-chain tawātur discount can both be applied.
        priors = chain_blind_spot_priors
        independent: list[tuple[ChainGrade, float, float]] = [
            (grade, score, priors[i] if priors is not None else self.shared_blind_spot_prior)
            for i, (grade, score) in enumerate(
                zip(corroborating_chains, independence_scores, strict=True)
            )
            if score >= self.INDEPENDENCE_THRESHOLD
        ]

        if not independent:
            return base_grade

        # --- Minimum-grade gate: at least one chain must clear threshold ---
        if not any(g >= self.MIN_GATE_GRADE for g, _, _ in independent):
            return base_grade

        # --- Information-theoretic corroboration with the disjointness discount
        #     and the per-chain tawātur discount (#54). ---
        # Each chain at grade G_i has an implied error probability p_i. A chain's
        # contribution is weighted by its independence score s_i (the #125
        # disjointness discount) AND by (1 - prior_i) (the #54 tawātur discount):
        # even a fully topology-independent chain is not a full witness, because
        # it may share an unobservable correlated failure. The prior is per-chain
        # when witness types are known (the shāhid/mutābaʿa distinction), flat
        # otherwise.
        #
        # So the effective witness weight of chain i is
        #     w_i = s_i * (1 - prior_i)
        # and a chain can never earn full (1.0) witness credit — which is the
        # honest tawātur position: corroboration requires *more* chains than the
        # nominal count suggests, never fewer.
        err = self.ERROR_PROBS
        combined_log_error = sum(
            score * (1.0 - prior) * math.log(max(err.get(g, 0.30), 0.001))
            for g, score, prior in independent
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


# ===========================================================================
# CorroborationEngine — operational mutābaʿāt (independent-chain upgrade)
#
# Finds corroborating chains across a corpus, checks independence via
# SharedLineageDetector, and delegates the grade-upgrade decision to
# CappedCorroborationPolicy (information-theoretic error multiplication).
#
# Key rules (paper §4.3):
# - Chains must be truly independent (disjoint narrator sets, different sources)
# - Upgrade is capped below SAHIH (cannot reach sound tier via corroboration alone)
# - Minimum-grade gate: at least one corroborating chain must clear threshold
# - Correlation discount: shared model family / upstream source → partial weight
#
# Matching is exact on claim_text.  For semantic / embedding-based matching
# pre-process claims externally and canonicalise to a shared key before
# passing to this engine.
# ===========================================================================


@dataclass
class CorroborationResult:
    """Result of a corroboration check."""

    base_grade: ChainGrade
    upgraded_grade: ChainGrade
    corroborating_chains: int  # matching chains (excl. base chain itself)
    independent_chains: int  # after correlation discount
    effective_weight: float  # info-theoretic log-error ratio
    upgraded: bool
    reason: str = ""
    # Per-chain independence provenance (issue #125 step 3): the score and the
    # *why* for every corroborating chain that was evaluated, so a caller (or an
    # audit record) can see which shared signal discounted a chain. Present for
    # every corroborating chain, not just the independent ones.
    chain_independence: list[IndependenceAssessment] = field(default_factory=list)
    # The tawātur discount (#54): the explicit prior that a nominally-independent
    # chain shares an unobservable correlated failure with the base chain. It is
    # never zero, and it caps the effective witness count below the nominal count.
    shared_blind_spot_prior: float = 0.20
    # The effective number of independent witnesses, after the tawātur discount.
    # Always ≤ the nominal independent-chain count; the gap is the honesty margin.
    effective_witnesses: float = 0.0


def _narrator_to_chain_grade(ng: NarratorGrade) -> ChainGrade:
    mapping = {
        NarratorGrade.RELIABLE: ChainGrade.SAHIH,
        NarratorGrade.ACCEPTABLE: ChainGrade.HASAN,
        NarratorGrade.WEAK: ChainGrade.DAIF,
        NarratorGrade.REJECTED: ChainGrade.MAWDU,
        NarratorGrade.UNGRADED: ChainGrade.HASAN,
    }
    return mapping[ng]


# Narrator types, in order of precedence for deciding a chain's "dominant
# witness type" — the model (synthesis) is the trust-relevant link; a human
# reviewer or source is a distinct witness kind; a scraper/tool is transmission
# plumbing. Used for the shāhid/mutābaʿa per-chain tawātur prior (#54).
_TYPE_PRECEDENCE = ("model", "human", "source", "tool", "scraper")


def _chain_narrator_type(
    narrator_ids: list[str], narrator_metadata: dict[str, dict[str, object]]
) -> str | None:
    """The dominant narrator type of a chain, for the blind-spot prior matrix.

    Returns the highest-precedence narrator type present in the chain, or None
    if no type is known. The model (synthesis) link is the trust-relevant
    witness; if absent, a human, source, tool, or scraper in that order.
    """
    present: set[str] = set()
    for nid in narrator_ids:
        meta = narrator_metadata.get(nid, {})
        nt = meta.get("narrator_type")
        if nt and isinstance(nt, str):
            present.add(nt)
    for t in _TYPE_PRECEDENCE:
        if t in present:
            return t
    return next(iter(present), None) if present else None


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
            Also sets the effective-weight threshold on the policy.
        corroboration_cap: Highest grade reachable via corroboration.
        min_gate_grade: At least one corroborating chain must meet
            this grade for upgrade to be considered.
        correlation_detector: Optional custom SharedLineageDetector.
        policy: Optional custom CappedCorroborationPolicy for the
            upgrade decision math.  If not provided, one is created
            with MIN_EFFECTIVE_WEIGHT = min_independent_chains.
        """
        self.min_independent_chains = min_independent_chains
        self.corroboration_cap = corroboration_cap
        self.min_gate_grade = min_gate_grade
        self._correlation_detector = correlation_detector or SharedLineageDetector()
        if policy is not None:
            self._policy = policy
        else:
            self._policy = CappedCorroborationPolicy()
            self._policy.MIN_EFFECTIVE_WEIGHT = float(min_independent_chains)

    def evaluate(
        self,
        claim_text: str,
        base_chain_grade: ChainGrade,
        base_narrators: list[str],
        all_chains: list[dict],
        narrator_metadata: dict[str, dict] | None = None,
        *,
        has_live_contradiction: bool = False,
        base_document_hashes: set[str] | None = None,
    ) -> CorroborationResult:
        """Evaluate corroboration by matching claims via exact claim_text.

        For semantic / embedding-based matching, canonicalise claims to a
        shared key before calling this method, or use evaluate_direct().

        Args:
            claim_text: Normalized claim text (exact match).
            base_chain_grade: Grade of the claim's own chain.
            base_narrators: Narrator IDs in the base claim's chain.
            all_chains: List of all claim chain dicts with keys:
                claim_text, chain_grade, narrator_ids. Optional:
                document_hashes (list[str] or set[str]) for each chain, used
                by the correlation detector's madār check.
            narrator_metadata: Optional metadata for correlation detection.
            has_live_contradiction: True when content criticism has flagged
                this claim as contradicting an existing claim (issue #11 —
                the corroboration bonus must not be usable to paper over a
                live contradiction; withhold any upgrade in that case).
            base_document_hashes: Retrieved-document content hashes of the
                base chain, used for the madār check against corroborators.

        Returns:
            CorroborationResult with upgrade decision.
        """
        # Find corroborating chains by exact text match
        base_narrator_set = set(base_narrators)
        corroborating_raw: list[dict] = []
        for chain in all_chains:
            if chain.get("claim_text", "") != claim_text:
                continue
            if set(chain.get("narrator_ids", [])) == base_narrator_set:
                continue  # exclude base chain itself
            cg_raw = chain.get("chain_grade", "daif")
            try:
                cg = ChainGrade(cg_raw)
            except ValueError:
                cg = ChainGrade.DAIF
            corroborating_raw.append({
                "grade": cg,
                "narrators": chain.get("narrator_ids", []),
                "source": chain.get("source", ""),
                "document_hashes": set(chain.get("document_hashes", []) or []),
            })

        return self._evaluate_core(
            base_chain_grade=base_chain_grade,
            base_narrators=base_narrators,
            corroborating_chains=corroborating_raw,
            narrator_metadata=narrator_metadata or {},
            total_corroborating=len(corroborating_raw),
            has_live_contradiction=has_live_contradiction,
            base_document_hashes=base_document_hashes,
        )

    def evaluate_direct(
        self,
        base_chain_grade: ChainGrade,
        base_narrators: list[str],
        corroborating_chains: list[dict],
        narrator_metadata: dict[str, dict] | None = None,
        *,
        has_live_contradiction: bool = False,
        base_document_hashes: set[str] | None = None,
    ) -> CorroborationResult:
        """Evaluate corroboration with pre-matched corroborating chains.

        Use this when claims have already been matched semantically or
        via embeddings — you provide the corroborating chains directly
        without needing exact text matching.

        Args:
            base_chain_grade: Grade of the claim's own chain.
            base_narrators: Narrator IDs in the base claim's chain.
            corroborating_chains: Pre-matched corroborating chain dicts.
                Each dict must have keys: grade (ChainGrade or str),
                narrators (list[str]).  Optional: source (str),
                document_hashes (list[str] or set[str]) for the madār check.
            narrator_metadata: Optional metadata for correlation detection.
            has_live_contradiction: True when content criticism has flagged
                this claim as contradicting an existing claim (issue #11 —
                withhold any corroboration upgrade in that case, rather than
                letting fake-independent parallel chains paper over it).
            base_document_hashes: Retrieved-document content hashes of the
                base chain, used for the madār check against corroborators.

        Returns:
            CorroborationResult with upgrade decision.

        Example:
            # Claims matched semantically via embeddings
            engine = CorroborationEngine()
            result = engine.evaluate_direct(
                base_chain_grade=ChainGrade.DAIF,
                base_narrators=["source:A", "ingest:A", "model:A"],
                corroborating_chains=[
                    {"grade": "hasan", "narrators": ["source:B", "ingest:B", "model:B"]},
                ],
                narrator_metadata={...},
            )
        """
        # Normalise corroborating chains
        normalised: list[dict] = []
        for c in corroborating_chains:
            grade = c.get("grade", "daif")
            if isinstance(grade, str):
                try:
                    grade = ChainGrade(grade)
                except ValueError:
                    grade = ChainGrade.DAIF
            normalised.append({
                "grade": grade,
                "narrators": c.get("narrators", []),
                "source": c.get("source", ""),
                "document_hashes": set(c.get("document_hashes", []) or []),
            })

        return self._evaluate_core(
            base_chain_grade=base_chain_grade,
            base_narrators=base_narrators,
            corroborating_chains=normalised,
            narrator_metadata=narrator_metadata or {},
            total_corroborating=len(normalised),
            has_live_contradiction=has_live_contradiction,
            base_document_hashes=base_document_hashes,
        )

    # ── internal: shared corroboration logic ──────────────────────

    def _evaluate_core(
        self,
        base_chain_grade: ChainGrade,
        base_narrators: list[str],
        corroborating_chains: list[dict],
        narrator_metadata: dict[str, dict],
        total_corroborating: int,
        *,
        has_live_contradiction: bool = False,
        base_document_hashes: set[str] | None = None,
    ) -> CorroborationResult:
        """Core corroboration logic shared by evaluate() and evaluate_direct()."""
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

        # --- Shādhdh gate (issue #11): a live contradiction must not be ---
        # --- papered over by a corroboration bonus, however many         ---
        # --- "independent" chains agree — the contradiction itself takes ---
        # --- precedence over chain-side upgrade math.                   ---
        if has_live_contradiction:
            return CorroborationResult(
                base_grade=base_chain_grade,
                upgraded_grade=base_chain_grade,
                corroborating_chains=total_corroborating,
                independent_chains=0,
                effective_weight=0.0,
                upgraded=False,
                reason="Corroboration withheld: claim has a live content contradiction outstanding",
            )

        # Compute per-chain independence assessments for ALL corroborating
        # chains (not just the independent ones) so the result carries the
        # *why* for every chain evaluated, including discounted ones (#125).
        assessments = [
            self._correlation_detector.detect(
                base_narrators,
                c["narrators"],
                narrator_metadata,
                chain_a_document_hashes=base_document_hashes,
                chain_b_document_hashes=c.get("document_hashes"),
            )
            for c in corroborating_chains
        ]

        # Filter by independence
        independent = [
            c for c, a in zip(corroborating_chains, assessments, strict=True) if a.is_independent
        ]

        if len(independent) < self.min_independent_chains:
            return CorroborationResult(
                base_grade=base_chain_grade,
                upgraded_grade=base_chain_grade,
                corroborating_chains=total_corroborating,
                independent_chains=len(independent),
                effective_weight=0.0,
                upgraded=False,
                chain_independence=assessments,
                reason=(
                    f"Need ≥{self.min_independent_chains} independent chains, "
                    f"have {len(independent)}"
                ),
            )

        # Minimum-grade gate
        if not any(c["grade"] >= self.min_gate_grade for c in independent):
            return CorroborationResult(
                base_grade=base_chain_grade,
                upgraded_grade=base_chain_grade,
                corroborating_chains=total_corroborating,
                independent_chains=len(independent),
                effective_weight=0.0,
                upgraded=False,
                chain_independence=assessments,
                reason=f"No corroborating chain meets min grade {self.min_gate_grade.value}",
            )

        # Compute independence scores (for the independent chains only) and
        # delegate to the policy.
        independent_assessments = [
            a for c, a in zip(corroborating_chains, assessments, strict=True) if a.is_independent
        ]
        independence_scores = [a.score for a in independent_assessments]
        grades = [c["grade"] for c in independent]

        # Per-chain tawātur priors from witness types (the shāhid/mutābaʿa
        # distinction, #54). Derive the base chain's dominant narrator type and
        # each corroborating chain's dominant type from metadata, then ask the
        # policy for the pairwise prior. Falls back to the flat prior when a
        # type is unknown.
        base_type = _chain_narrator_type(base_narrators, narrator_metadata)
        independent_priors = [
            self._policy.blind_spot_prior_for(
                base_type, _chain_narrator_type(c["narrators"], narrator_metadata)
            )
            for c in independent
        ]

        upgraded = self._policy.compute_corroborated_grade(
            base_grade=base_chain_grade,
            corroborating_chains=grades,
            independence_scores=independence_scores,
            chain_blind_spot_priors=independent_priors,
        )

        effective_weight = self._compute_effective_weight(
            base_chain_grade, grades, independence_scores, independent_priors
        )
        upgraded_flag = upgraded != base_chain_grade

        # Effective witnesses: sum of (independence_score × (1 − blind-spot
        # prior)) over the independent chains — the tawātur-discounted count that
        # is always ≤ the nominal count.
        effective_witnesses = sum(
            a.score * (1.0 - prior)
            for a, prior in zip(independent_assessments, independent_priors, strict=True)
        )

        return CorroborationResult(
            base_grade=base_chain_grade,
            upgraded_grade=upgraded,
            corroborating_chains=total_corroborating,
            independent_chains=len(independent),
            effective_weight=effective_weight,
            upgraded=upgraded_flag,
            chain_independence=assessments,
            shared_blind_spot_prior=self._policy.shared_blind_spot_prior,
            effective_witnesses=effective_witnesses,
            reason=(
                f"Upgraded via {len(independent)} independent chains "
                f"(effective weight={effective_weight:.1f}, "
                f"effective witnesses={effective_witnesses:.1f})"
                if upgraded_flag
                else (
                    f"Effective weight {effective_weight:.1f} < {self._policy.MIN_EFFECTIVE_WEIGHT}"
                )
            ),
        )

    def _compute_effective_weight(
        self,
        base_grade: ChainGrade,
        corroborating_grades: list[ChainGrade],
        independence_scores: list[float],
        chain_blind_spot_priors: list[float] | None = None,
    ) -> float:
        """Compute information-theoretic effective weight.

        Each chain's log-error reduction is weighted by its independence score
        (the disjointness discount) AND by (1 - prior_i) (the tawātur discount),
        matching ``CappedCorroborationPolicy.compute_corroborated_grade`` so the
        number reported in ``CorroborationResult.effective_weight`` agrees with
        the number the policy actually used for its decision.
        """
        err = self._policy.ERROR_PROBS
        priors = chain_blind_spot_priors
        combined = sum(
            score
            * (1.0 - (priors[i] if priors is not None else self._policy.shared_blind_spot_prior))
            * math.log(max(err.get(g, 0.30), 0.001))
            for i, (g, score) in enumerate(
                zip(corroborating_grades, independence_scores, strict=True)
            )
        )
        combined += math.log(max(err.get(base_grade, 0.30), 0.001))
        hasan_log = math.log(err[ChainGrade.HASAN])
        return combined / max(hasan_log, -10.0)
