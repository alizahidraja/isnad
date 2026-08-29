"""Ordinal types, enums, and protocol base classes for the Isnād–Rijāl framework.

Faithful to the paper's epistemic commitments:
- Grades are ordinal tiers; numeric error rates are optional metadata only.
- Domain-conditioned grading: the key is (narrator_id, domain).
- Transform types are first-class attributes of each narrator/link.
- ʿAdālah and ḍabṭ are two distinct axes, not one blended score.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum, StrEnum
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
# Freshness of a narrator grade — the time-decay half of the expiry fix
# ---------------------------------------------------------------------------


class FreshnessStatus(Enum):
    """Freshness of a narrator grade relative to its volatility window.

    A grade is a truth-statement about a window of time, not a permanent
    attribute.  The window is defined by the VolatilityPolicy:
        - FRESH:  inside the window, grade used as stored.
        - STALE:  in the grace window — downgraded one tier + needs re-check.
        - EXPIRED: past best-before — reverts to UNGRADED until re-earned.
    REJECTED (active containment) never decays.
    """

    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"


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


class Role(StrEnum):
    """What a transmitter did at a chain step (the task, not the agent).

    Distinct from ``NarratorType`` (who/what the agent *is*).  Precision (ḍabṭ)
    is graded per ``(narrator, role, domain)`` because competence is
    task-specific: a model can extract faithfully and synthesize carelessly
    (issue #3).  Integrity (ʿadālah) is NOT per-role — it is a judgment of the
    person and is shared across roles.
    """

    RETRIEVAL = "retrieval"  # fetched documents from a store
    EXTRACTION = "extraction"  # extracted claims from documents
    SYNTHESIS = "synthesis"  # generated/synthesized a claim
    TOOL = "tool"  # executed an external tool
    HUMAN = "human"  # human review or input
    SOURCE = "source"  # origin document / external source


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
    SURVIVAL = "survival"  # a claim survived independent (endorsed) verification
    HUMAN_REVIEW = "human_review"  # human reviewer verdict
    DISPUTE = "dispute"  # a narrator contests their grade (issue #38)
    ADJUDICATION = "adjudication"  # an operator resolves a dispute (issue #38)
    VERSION_BUMP = "version_bump"  # model version change → reset
    BOOTSTRAP_SEED = "bootstrap_seed"  # initial seed grade from benchmarks
    FRESHNESS_RENEWAL = "freshness_renewal"  # clock restart only — no grade signal


class EvidenceProvenance(Enum):
    """Where a piece of grading evidence came from — prior or observed instance.

    Issue #6 ("ground rijāl grading in observed in-pipeline survival, not
    benchmark priors") points at a real epistemic distinction the framework
    previously buried: a grade can be built on a *population prior* (a
    benchmark says this model class is ~85% accurate) or on *observed
    instances* (we watched THIS transmitter's claims survive or fail inside
    the pipeline).  Classical rijāl graded individuals on observed instances,
    never on priors.

    - PRIOR:      a population estimate — benchmark seeds, eval harnesses.
      Says nothing about whether THIS transmission is in the 85 or the 15.
    - OBSERVED:   an observed instance inside the operator's own pipeline —
      a post-hoc audit of a served claim, or an independent-chain
      corroboration/contradiction.  Slow to accumulate, but it is a record
      about this transmitter rather than a population estimate.
    - HUMAN:      a human reviewer verdict.  Observed, but by a named human
      critic rather than an automated instance.
    - META:       not grade evidence at all — a lifecycle event (version
      bump) that resets the record.

    This classification is a *signal about the grade*, not a new grading
    axis.  It lets a caller answer "is this narrator's grade an assumption
    or an observation?" without changing how grades are computed.
    """

    PRIOR = "prior"
    OBSERVED = "observed"
    HUMAN = "human"
    META = "meta"


_PRIOR_EVIDENCE = {EvidenceType.BOOTSTRAP_SEED, EvidenceType.EVAL_HARNESS}
_OBSERVED_EVIDENCE = {
    EvidenceType.POST_HOC_AUDIT,
    EvidenceType.CORROBORATION_OUTCOME,
    EvidenceType.SURVIVAL,
}


def provenance_of(evidence_type: EvidenceType) -> EvidenceProvenance:
    """Classify an evidence type as prior, observed, human, or meta.

    - BOOTSTRAP_SEED / EVAL_HARNESS → PRIOR (a population estimate).
    - POST_HOC_AUDIT / CORROBORATION_OUTCOME / SURVIVAL → OBSERVED (an
      in-pipeline instance).
    - HUMAN_REVIEW → HUMAN.
    - VERSION_BUMP / FRESHNESS_RENEWAL → META (a reset or clock restart,
      not grade evidence).
    """
    if evidence_type in _PRIOR_EVIDENCE:
        return EvidenceProvenance.PRIOR
    if evidence_type in _OBSERVED_EVIDENCE:
        return EvidenceProvenance.OBSERVED
    if evidence_type == EvidenceType.HUMAN_REVIEW:
        return EvidenceProvenance.HUMAN
    return EvidenceProvenance.META


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
        link_adalah_grades: list[AdalahGrade] | None = None,
        link_fidelity_verdicts: list[ContentVerdict] | None = None,
        lenient_unknown: bool = False,
    ) -> ChainGrade: ...


class TransitionPolicy(Protocol):
    """Protocol for how logged evidence moves a narrator between ordinal states.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  Swap freely.

    The framework default (``BayesianTransitionPolicy``) derives grades from a
    Beta-distribution posterior mean, so it has no fixed "N adverse events"
    cutoff. The simpler ``ThresholdTransitionPolicy`` is also available and uses:
    - windowed threshold counts for adverse evidence → downgrade
    - sustained corroborated accuracy → upgrade (requires N recent positive evals)
    - version bump → reset to UNGRADED

    (Both count over a sliding window of recent evidence and are edge-triggered
    on the arriving evidence — see issue #9.)
    """

    def evaluate_transition(
        self,
        current_grade: NarratorGrade,
        evidence_history: list[dict[str, object]],
        new_evidence: dict[str, object],
        *,
        is_compromised: bool = False,
    ) -> NarratorGrade: ...


class VolatilityPolicy(Protocol):
    """Protocol for how long a narrator grade stays trustworthy.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2).  Swap freely.

    Defines the time-decay half of the grade-expiry fix:
    - time_to_live(): how long a grade is trusted after it is (re)validated.
    - stale_window(): the grace period at the end of the TTL during which
      the grade is downgraded one tier and flagged for re-check instead of
      being treated as expired outright.
    - valid_until():   convenience — the expiry instant given a reference now.

    The default implementation (FixedVolatilityPolicy) derives TTLs from
    configuration (narrator type + optional per-domain overrides) rather
    than a hardcoded table.
    """

    def time_to_live(self, narrator_type: NarratorType, domain: str) -> timedelta: ...

    def stale_window(self, narrator_type: NarratorType, domain: str) -> timedelta: ...

    def valid_until(
        self,
        narrator_type: NarratorType,
        domain: str,
        now: datetime | None = None,
    ) -> datetime: ...


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
    - shared narrator IDs (hard correlation)
    - shared retrieved-document hashes (hard correlation — the madār case)
    - shared model family (same base model / provider lineage)
    - shared upstream source (both trace to the same origin)

    Naive set-disjointness of narrator IDs is *wrong*; this detector
    captures correlated chains that share no explicit narrator but
    still fail together.

    The document-hash and lineage signals arrive as optional keyword-only
    arguments on the default implementation; custom detectors may ignore
    them (the protocol signatures below stay minimal for backward
    compatibility — callers pass document hashes through the concrete
    ``SharedLineageDetector``, not through this protocol).
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


class EvidenceAxis(Enum):
    """Which reliability axis a piece of evidence bears on (ʿadālah vs ḍabṭ).

    The classical science splits transmitter criticism into two axes that are
    handled very differently over time:

    - INTEGRITY (ʿadālah): honesty / manipulation-resistance. An established
      integrity impugnment (jarḥ against ʿadālah) is *permanent* in the
      record — the corpus is protected regardless of later good conduct. This
      evidence never ages out of a threshold policy's window, and favorable
      precision evidence can never lift a grade capped by an integrity strike.
    - PRECISION (ḍabṭ): accuracy / error rate. Precision genuinely changes over
      time (cf. the mukhtaliṭūn, whose narrations were dated relative to the
      onset of decline). Precision evidence is windowed and recoverable.
    - UNSPECIFIED: axis not declared by the caller. Treated as INTEGRITY-class
      (non-forgettable) by design: forgetting is a privilege a caller earns by
      explicitly declaring a jarḥ to be a precision lapse. Absent that
      declaration, impugnment persists — al-jarḥ muqaddam ʿalā al-taʿdīl.

    See issue #9 (finding #1) and its conceptual follow-up: a windowed policy
    that forgets *integrity* evidence silently reintroduces the
    fabricator-rehabilitation path. Axis-tagging closes it.
    """

    INTEGRITY = "integrity"  # ʿadālah — permanent, never forgotten
    PRECISION = "precision"  # ḍabṭ — windowed, recoverable
    UNSPECIFIED = "unspecified"  # not declared → treated as INTEGRITY-class


def default_axis_for(evidence_type: EvidenceType) -> EvidenceAxis:
    """The axis to assume for an evidence type when a caller does not specify one.

    The *automated* signals are accuracy measurements (ḍabṭ) and resolve to
    PRECISION — an integrity (ʿadālah) verdict is a scholarly determination that
    an automated check cannot make; it only knows an answer was *wrong*, not that
    it was a *lie*:

    - EVAL_HARNESS: a failed eval is an error-rate signal.
    - CORROBORATION_OUTCOME: a contradiction by an independent chain is a factual
      disagreement, not proof of manipulation.
    - POST_HOC_AUDIT: an audit detects a served-claim *error*. Treating it as a
      permanent integrity strike would make exactly the downgrades §8.6 warns are
      *too aggressive* permanent — strictly worse than the ratchet removed in the
      base fix. So audits are precision; whether an error was deliberate is a
      separate, human determination.

    Only HUMAN_REVIEW stays UNSPECIFIED (→ integrity-class, permanent): a human
    reviewer may be recording a genuine ʿadālah violation, so it is resolved
    conservatively unless the reviewer passes an explicit axis. Deliberate
    integrity strikes therefore come from HUMAN_REVIEW, an explicit INTEGRITY
    tag, or ``quarantine`` — never from an automated counter.

    A caller who knows better should always pass an explicit axis; this only
    picks a safe default for the common case where none is given.
    """
    precision_types = {
        EvidenceType.EVAL_HARNESS,
        EvidenceType.CORROBORATION_OUTCOME,
        EvidenceType.POST_HOC_AUDIT,
        EvidenceType.SURVIVAL,
    }
    return EvidenceAxis.PRECISION if evidence_type in precision_types else EvidenceAxis.UNSPECIFIED
