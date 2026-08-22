"""Property-based (randomized) tests for the registry's semantic contract.

These are deliberately NOT white-box.  They generate *random* operation
sequences and assert invariants that must hold for ANY correct implementation
of the framework's published semantics (paper §4.2–§4.4).  A failure here means
the contract is broken — not that a specific happy path is untested.

Every test uses a fixed seed, so a failure reproduces exactly.

The invariants are the product's spine:

1. Quarantine (active containment) is permanent and spans every role.
2. Precision evidence never rehabilitates a quarantined narrator.
3. Domains are isolated — evidence in one domain never moves another's grade.
4. Roles are isolated — precision evidence for one role never moves another's.
5. A version bump is a new narrator: every role resets to UNGRADED, and
   pre-bump evidence no longer counts.
6. Survival is claim-scoped (dedup) and self-verification is refused (tazkiyah).
7. In-memory state and a SQLAlchemy round-trip agree.
8. Arbitrary operation sequences never raise and always yield ordinal grades.
"""

from __future__ import annotations

import random

from isnad.core.registry import Registry
from isnad.types import (
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    Role,
)

NARRATORS = ["model:a", "model:b", "scraper:c", "source:d", "human:e"]
DOMAINS = ["physics", "biology", "general"]
ROLES = [Role.RETRIEVAL, Role.EXTRACTION, Role.SYNTHESIS, Role.TOOL]
ALL_ROLE_OPTIONS = [None, *ROLES]
GRADES = list(NarratorGrade)
ACTIONS = [EvidenceAction.TADIL, EvidenceAction.JARH, EvidenceAction.NEUTRAL]
EVIDENCE_TYPES = [
    EvidenceType.POST_HOC_AUDIT,
    EvidenceType.CORROBORATION_OUTCOME,
    EvidenceType.SURVIVAL,
    EvidenceType.BOOTSTRAP_SEED,
    EvidenceType.EVAL_HARNESS,
    EvidenceType.HUMAN_REVIEW,
]


class TestQuarantineIsPermanentAndCrossRole:
    def test_quarantine_floors_every_role(self) -> None:
        for seed in range(15):
            rng = random.Random(seed)
            reg = Registry()
            for _ in range(40):
                n = rng.choice(NARRATORS)
                d = rng.choice(DOMAINS)
                reg.register(n, d, grade=rng.choice(GRADES), role=rng.choice(ALL_ROLE_OPTIONS))

            n = rng.choice(NARRATORS)
            d = rng.choice(DOMAINS)
            reg.quarantine(n, d, "fuzz")

            assert reg.get_grade(n, d) == NarratorGrade.REJECTED
            for role in ROLES:
                assert reg.get_grade(n, d, role=role) == NarratorGrade.REJECTED

    def test_precision_evidence_cannot_recover_a_quarantined_narrator(self) -> None:
        for seed in range(10):
            rng = random.Random(seed)
            reg = Registry()
            n = rng.choice(NARRATORS)
            d = rng.choice(DOMAINS)
            reg.register(n, d, grade=NarratorGrade.RELIABLE)
            reg.quarantine(n, d, "fuzz")

            for i in range(30):
                reg.record_survival(n, d, f"c-{i}", "gov.uk", role=rng.choice(ROLES))

            assert reg.get_grade(n, d) == NarratorGrade.REJECTED
            for role in ROLES:
                assert reg.get_grade(n, d, role=role) == NarratorGrade.REJECTED


class TestDomainIsolation:
    def test_evidence_in_one_domain_does_not_move_another(self) -> None:
        for seed in range(10):
            rng = random.Random(seed)
            reg = Registry()
            # Build up state in all domains.
            for _ in range(40):
                n = rng.choice(NARRATORS)
                d = rng.choice(DOMAINS)
                reg.record_evidence(n, d, rng.choice(EVIDENCE_TYPES), rng.choice(ACTIONS))

            before = {(n, d): reg.get_grade(n, d) for n in NARRATORS for d in DOMAINS}

            # Hammer one domain hard.
            target = DOMAINS[0]
            for _ in range(60):
                n = rng.choice(NARRATORS)
                reg.record_evidence(n, target, rng.choice(EVIDENCE_TYPES), rng.choice(ACTIONS))

            for d in DOMAINS[1:]:
                for n in NARRATORS:
                    assert reg.get_grade(n, d) == before[(n, d)], (seed, n, d)


class TestRolePrecisionIsolation:
    def test_precision_evidence_for_one_role_does_not_move_another(self) -> None:
        for seed in range(10):
            rng = random.Random(seed)
            reg = Registry()
            n = "model:a"
            d = "physics"
            reg.register(n, d, grade=NarratorGrade.UNGRADED)

            for i in range(40):
                reg.record_survival(n, d, f"c-{i}", "gov.uk", role=Role.SYNTHESIS)

            # The default record and sibling roles must be untouched.
            assert reg.get_grade(n, d) == NarratorGrade.UNGRADED
            for role in [Role.RETRIEVAL, Role.EXTRACTION, Role.TOOL]:
                assert reg.get_grade(n, d, role=role) == NarratorGrade.UNGRADED
            # The synthesis role itself must have accumulated the evidence.
            assert reg.evidence_provenance(n, d, role=Role.SYNTHESIS).observed_count == 40


class TestVersionBumpIsEpochBoundary:
    def test_bump_resets_every_role(self) -> None:
        for seed in range(10):
            rng = random.Random(seed)
            reg = Registry()
            n = "model:a"
            d = "physics"
            reg.register(n, d, grade=NarratorGrade.RELIABLE)
            for role in ROLES:
                reg.register(n, d, role=role, grade=rng.choice(GRADES))

            reg.bump_version(n, d, "v2")

            assert reg.get_grade(n, d) == NarratorGrade.UNGRADED
            for role in ROLES:
                assert reg.get_grade(n, d, role=role) == NarratorGrade.UNGRADED

    def test_pre_bump_evidence_does_not_count_after_bump(self) -> None:
        for seed in range(10):
            rng = random.Random(seed)
            reg = Registry()
            n = "model:a"
            d = "physics"
            # Flood with positive precision evidence (pre-bump).
            for i in range(20):
                reg.record_survival(n, d, f"c-{i}", "gov.uk")
            reg.bump_version(n, d, "v2")
            assert reg.get_grade(n, d) == NarratorGrade.UNGRADED
            # A single post-bump jarḥ must grade on post-bump evidence alone:
            # for the Bayesian default, one jarḥ → REJECTED, not softened by
            # the 20 pre-bump taʿdīl.
            reg.record_evidence(n, d, EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH)
            assert reg.get_grade(n, d) == NarratorGrade.REJECTED


class TestSurvivalContract:
    def test_survival_dedups_and_self_verification_is_refused(self) -> None:
        for seed in range(10):
            rng = random.Random(seed)
            reg = Registry()
            n = "model:a"
            d = "physics"
            reg.register(n, d)

            for _ in range(15):
                reg.record_survival(n, d, "same-claim", "gov.uk")
            assert reg.evidence_provenance(n, d).observed_count == 1

            for i in range(5):
                reg.record_survival(n, d, f"self-{i}", "blog.example", self_verified=True)
            assert reg.evidence_provenance(n, d).observed_count == 1  # refused


class TestUnknownNarrator:
    def test_unknown_narrator_and_role_are_ungraded(self) -> None:
        reg = Registry()
        assert reg.get_grade("nobody", "anywhere") == NarratorGrade.UNGRADED
        assert reg.get_grade("nobody", "anywhere", role=Role.SYNTHESIS) == NarratorGrade.UNGRADED


class TestDbRoundTrip:
    def test_random_state_round_trips_through_sqlalchemy(self, tmp_path) -> None:
        import tempfile

        from sqlalchemy.orm import Session

        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine

        for seed in range(5):
            rng = random.Random(seed)
            with tempfile.TemporaryDirectory() as td:
                url = f"sqlite:///{td}/p-{seed}.db"
                reset_engine()
                init_db(url)
                engine = create_engine_from_url(url)

                with Session(engine) as s:
                    rdb = RegistryDB(session=s)
                    reg = rdb.registry
                    for _ in range(30):
                        n = rng.choice(NARRATORS)
                        d = rng.choice(DOMAINS)
                        role = rng.choice(ALL_ROLE_OPTIONS)
                        if rng.random() < 0.5:
                            reg.register(n, d, grade=rng.choice(GRADES), role=role)
                        else:
                            reg.record_evidence(
                                n, d, rng.choice(EVIDENCE_TYPES), rng.choice(ACTIONS), role=role
                            )
                    rdb.flush()
                    s.commit()

                    snapshot = {
                        (n, d, role): reg.get_grade(n, d, role=role)
                        for n in NARRATORS
                        for d in DOMAINS
                        for role in ALL_ROLE_OPTIONS
                    }

                with Session(engine) as s:
                    rdb2 = RegistryDB(session=s)
                    rdb2.load()
                    for (n, d, role), expected in snapshot.items():
                        got = rdb2.registry.get_grade(n, d, role=role)
                        assert got == expected, (seed, n, d, role, expected, got)

                reset_engine()


class TestFuzzNoCrash:
    def test_arbitrary_sequences_never_crash_and_yield_ordinals(self) -> None:
        for seed in range(40):
            rng = random.Random(seed)
            reg = Registry()
            for _ in range(120):
                n = rng.choice(NARRATORS)
                d = rng.choice(DOMAINS)
                role = rng.choice(ALL_ROLE_OPTIONS)
                op = rng.randrange(6)
                if op == 0:
                    reg.register(n, d, grade=rng.choice(GRADES), role=role)
                elif op == 1:
                    reg.record_evidence(
                        n, d, rng.choice(EVIDENCE_TYPES), rng.choice(ACTIONS), role=role
                    )
                elif op == 2:
                    reg.record_survival(
                        n,
                        d,
                        f"c-{rng.randint(0, 9999)}",
                        rng.choice(["gov.uk", "blog.example", ""]),
                        self_verified=rng.random() < 0.5,
                        role=role,
                    )
                elif op == 3:
                    reg.quarantine(n, d, "fuzz")
                elif op == 4:
                    reg.bump_version(n, d, f"v{rng.randint(1, 20)}")
                else:
                    reg.flag_contradiction(n, d, role=role)

                g = reg.get_grade(n, d, role=role)
                assert isinstance(g, NarratorGrade)
                assert g in GRADES


class TestIntegrityCapInvariant:
    """Integrity strikes impose a permanent ceiling that precision cannot lift (#30)."""

    def test_random_strike_count_caps_precision_grade(self) -> None:
        from isnad.types import EvidenceAxis

        ladder = [
            NarratorGrade.RELIABLE,
            NarratorGrade.ACCEPTABLE,
            NarratorGrade.WEAK,
            NarratorGrade.REJECTED,
        ]
        for seed in range(15):
            rng = random.Random(seed)
            reg = Registry()
            reg.register("m", "d")
            for i in range(30):
                reg.record_survival("m", "d", f"c-{i}", "gov.uk")
            assert reg.get_grade("m", "d") == NarratorGrade.RELIABLE

            strikes = rng.randint(0, 5)
            for _ in range(strikes):
                reg.record_evidence(
                    "m",
                    "d",
                    EvidenceType.HUMAN_REVIEW,
                    EvidenceAction.JARH,
                    axis=EvidenceAxis.INTEGRITY,
                )
            # A flood of precision evidence cannot lift past the permanent ceiling.
            for i in range(30):
                reg.record_survival("m", "d", f"d-{i}", "gov.uk")

            cap = ladder[min(strikes, 3)]
            assert reg.get_grade("m", "d") == cap, (seed, strikes, cap)
