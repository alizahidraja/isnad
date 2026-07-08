"""Ordinal types, enums, and protocol base classes for the Isnād–Rijāl framework.

Faithful to the paper's epistemic commitments:
- Grades are ordinal tiers; numeric error rates are optional metadata only.
- Domain-conditioned grading: the key is (narrator_id, domain).
- Transform types are first-class attributes of each narrator/link.
- ʿAdālah and ḍabṭ are two distinct axes, not one blended score.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

# ---------------------------------------------------------------------------
# Ordinal narrator grades — the primary trust signal
# ---------------------------------------------------------------------------


class NarratorGrade(Enum):
    """Ordinal narrator grade in descending trust order.

    These are the rijāl tiers from classical hadith science.  The ordering
    is defined: RELIABLE > ACCEPTABLE > WEAK > REJECTED.  Numeric error
    rates are *optional metadata attached only where calibration data exists*
    and MUST NOT be the primary grade or be surfaced to callers as if precise.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  The ordinal categories are fixed; the transition
    arithmetic that moves a narrator between them is pluggable via
    TransitionPolicy.
    """

    RELIABLE = "reliable"  # ṣaḥīḥ-tier narrator
    ACCEPTABLE = "acceptable"  # ḥasan-tier narrator
    WEAK = "weak"  # ḍaʿīf-tier narrator
    REJECTED = "rejected"  # mawḍūʿ-tier narrator (quarantine)
    UNGRADED = "ungraded"  # version-bumped / never evaluated

    def __lt__(self, other: NarratorGrade) -> bool:
        order = {
            NarratorGrade.RELIABLE: 4,
            NarratorGrade.ACCEPTABLE: 3,
            NarratorGrade.WEAK: 2,
            NarratorGrade.REJECTED: 1,
            NarratorGrade.UNGRADED: 0,
        }
        return order[self] < order[other]

    def __le__(self, other: NarratorGrade) -> bool:
        return self < other or self == other

    def __gt__(self, other: NarratorGrade) -> bool:
        return not self <= other

    def __ge__(self, other: NarratorGrade) -> bool:
        return not self < other

    @classmethod
    def min(cls, *grades: NarratorGrade) -> NarratorGrade:
        """Return the lowest (least trusted) grade among the given grades."""
        return min(grades)

    @property
    def is_at_least_acceptable(self) -> bool:
        return self in (NarratorGrade.RELIABLE, NarratorGrade.ACCEPTABLE)


# ---------------------------------------------------------------------------
# Ordinal chain (claim) grades — the trust tier for a full transmission
# ---------------------------------------------------------------------------


class ChainGrade(Enum):
    """Ordinal chain grade for a claim, in descending trust order.

    SAHIH > HASAN > DAIF > MAWDU.  These are the hadith-authenticity
    tiers adapted to AI chains.  A chain's grade is capped by its weakest
    link, refined by transform type (see grading.py), and subject to
    completeness (ittiṣāl) enforcement.
    """

    SAHIH = "sahih"  # sound — all narrators reliable, chain complete
    HASAN = "hasan"  # good — mostly reliable, ≥1 ungraded or acceptable
    DAIF = "daif"  # weak — weak narrator, or munqaṭiʿ (incomplete chain)
    MAWDU = "mawdu"  # rejected / fabricated — quarantined narrator

    def __lt__(self, other: ChainGrade) -> bool:
        order = {ChainGrade.SAHIH: 4, ChainGrade.HASAN: 3, ChainGrade.DAIF: 2, ChainGrade.MAWDU: 1}
        return order[self] < order[other]

    def __le__(self, other: ChainGrade) -> bool:
        return self < other or self == other

    def __gt__(self, other: ChainGrade) -> bool:
        return not self <= other

    def __ge__(self, other: ChainGrade) -> bool:
        return not self < other

    @classmethod
    def min(cls, *grades: ChainGrade) -> ChainGrade:
        return min(grades)


# ---------------------------------------------------------------------------
# Transform type — distinguishes destructive from generative steps
# ---------------------------------------------------------------------------


class TransformType(Enum):
    """The transformation type of a chain link.

    DESTRUCTIVE: extraction, chunking, lossy summarization — information is
      lost; downstream steps cannot recover it.  The strict weakest-link
      minimum applies.

    GENERATIVE: synthesis by a model with broad pre-training — may repair
      upstream noise OR introduce fresh corruption.  Can raise the floor
      only up to its own grade and only when corroboration supports it;
      can always lower it.

    PASS_THROUGH: identity-like transformation; does not affect grading.
    """

    DESTRUCTIVE = "destructive"
    GENERATIVE = "generative"
    PASS_THROUGH = "pass_through"


# ---------------------------------------------------------------------------
# Narrator type — the taxonomy of who/what can transmit a claim
# ---------------------------------------------------------------------------


class NarratorType(Enum):
    SOURCE = "source"  # external source (website, PDF, database)
    SCRAPER = "scraper"  # extraction tool
    MODEL = "model"  # LLM / ML model
    HUMAN = "human"  # human contributor / reviewer


# ---------------------------------------------------------------------------
# ʿAdālah and ḍabṭ — the two-axis narrator evaluation
# ---------------------------------------------------------------------------


class AdalahGrade(Enum):
    """ʿAdālah: integrity / manipulation-resistance axis.

    HIGH: trusted source, well-fenced, injection-resistant.
    ACCEPTABLE: no known integrity failures.
    SUSPECT: potential manipulation vector.
    COMPROMISED: known injection/poisoning source → active quarantine.
    UNASSESSED: never evaluated for integrity.
    """

    HIGH = "high"
    ACCEPTABLE = "acceptable"
    SUSPECT = "suspect"
    COMPROMISED = "compromised"
    UNASSESSED = "unassessed"


class DabtGrade(Enum):
    """Ḍabṭ: precision / error-rate axis.

    HIGH: calibrated error rate below threshold.
    ACCEPTABLE: adequate precision for domain.
    LOW: elevated error rate.
    UNASSESSED: never calibrated.
    """

    HIGH = "high"
    ACCEPTABLE = "acceptable"
    LOW = "low"
    UNASSESSED = "unassessed"


# ---------------------------------------------------------------------------
# Decision matrix actions — the output of the combined chain+content verdict
# ---------------------------------------------------------------------------


class Action(Enum):
    """Actions from the decision matrix (paper §4.4, Table).

    The 4×2 matrix: chain_grade ∈ {SAHIH, HASAN, DAIF, MAWDU}
                   × content_verdict ∈ {CONSISTENT, CONTRADICTION}
    """

    SERVE = "serve"  # serve directly; cache
    SERVE_WITH_CAVEAT = "serve_with_caveat"  # serve with confidence caveat
    REVIEW = "review"  # hold in review queue; do not serve (ʿilal path)
    QUARANTINE = "quarantine"  # quarantine claim
    REJECT_AND_QUARANTINE_NARRATOR = "reject_and_quarantine_narrator"
    # reject claim, quarantine narrator (poisoning mitigation)


# ---------------------------------------------------------------------------
# Evidence types that drive jarḥ–taʿdīl state transitions
# ---------------------------------------------------------------------------


class EvidenceType(Enum):
    """Named evidence types that drive narrator grade transitions.

    The jarḥ–taʿdīl loop is a state machine, not a formula (paper §4.2).
    Transitions are driven by these evidence types, each logged immutably.
    """

    EVAL_HARNESS = "eval_harness"  # per-narrator evaluation harness result
    POST_HOC_AUDIT = "post_hoc_audit"  # audit of served claims
    CORROBORATION_OUTCOME = "corroboration_outcome"  # corroboration/contradiction
    HUMAN_REVIEW = "human_review"  # human reviewer verdict
    VERSION_BUMP = "version_bump"  # model version change → reset
    BOOTSTRAP_SEED = "bootstrap_seed"  # initial seed grade from benchmarks


# ---------------------------------------------------------------------------
# Pluggable strategy protocols
# ---------------------------------------------------------------------------


class GradingStrategy(Protocol):
    """Protocol for combining link grades into a chain grade.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2/§4.3).  Swap freely.

    The default implementation (RefinedWeakestLink) applies:
    - strict minimum for destructive links
    - bounded, corroboration-gated adjustment for generative links
    - completeness cap (ittiṣāl)
    """

    def compute_chain_grade(
        self,
        link_narrator_grades: list[NarratorGrade],
        link_transform_types: list[TransformType],
        is_complete: bool,
        *,
        corroboration_support: bool = False,
    ) -> ChainGrade: ...


class TransitionPolicy(Protocol):
    """Protocol for how logged evidence moves a narrator between ordinal states.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  Swap freely.

    The default implementation (ThresholdTransitionPolicy) uses:
    - threshold counts for adverse evidence → downgrade
    - sustained corroborated accuracy → upgrade (requires N positive evals)
    - version bump → reset to UNGRADED
    """

    def evaluate_transition(
        self,
        current_grade: NarratorGrade,
        evidence_history: list[dict[str, object]],
        new_evidence: dict[str, object],
    ) -> NarratorGrade: ...


class CorroborationPolicy(Protocol):
    """Protocol for how independent chains upgrade a claim's grade.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.3).  Swap freely.

    The default implementation applies:
    - capped upgrade (never reaches SAHIH via corroboration alone)
    - minimum-grade gate (at least one chain must clear threshold)
    - correlation discount (correlated chains don't count independently)
    """

    def compute_corroborated_grade(
        self,
        base_grade: ChainGrade,
        corroborating_chains: list[ChainGrade],
        independence_scores: list[float],
    ) -> ChainGrade: ...


class CorrelationDetector(Protocol):
    """Protocol for deciding whether two transmission chains are truly independent.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.3, §7 — the madār problem).  Swap freely.

    The default implementation checks:
    - shared model family (same base model / provider lineage)
    - shared upstream source (both trace to the same origin)

    Naive set-disjointness of narrator IDs is *wrong*; this detector
    captures correlated chains that share no explicit narrator but
    still fail together.
    """

    def are_independent(
        self,
        chain_a_narrators: list[str],
        chain_b_narrators: list[str],
        narrator_metadata: dict[str, dict[str, object]],
    ) -> bool: ...

    def compute_independence_score(
        self,
        chain_a_narrators: list[str],
        chain_b_narrators: list[str],
        narrator_metadata: dict[str, dict[str, object]],
    ) -> float: ...


# ---------------------------------------------------------------------------
# Content criticism verdict
# ---------------------------------------------------------------------------


class ContentVerdict(Enum):
    """Result of matn criticism — independent of chain grade."""

    CONSISTENT = "consistent"  # no contradiction with corpus
    CONTRADICTION = "contradiction"  # conflicts with existing corpus claim
    UNVERIFIABLE = "unverifiable"  # cannot assess (e.g., novel domain)


# ---------------------------------------------------------------------------
# Chain completeness status
# ---------------------------------------------------------------------------


class ChainStatus(Enum):
    COMPLETE = "complete"  # ittiṣāl holds
    MUNQATI = "munqati"  # gap in chain → automatic DAIF cap
    ACTIVE = "active"  # currently served
    SUPERSEDED = "superseded"  # replaced by newer version


# ---------------------------------------------------------------------------
# Evidence log entry (immutable)
# ---------------------------------------------------------------------------


class EvidenceAction(Enum):
    """Direction of evidence impact on narrator grade."""

    JARH = "jarh"  # criticism — adverse evidence
    TADIL = "tadil"  # accreditation — positive evidence
    NEUTRAL = "neutral"  # logged for record, no grade impact
