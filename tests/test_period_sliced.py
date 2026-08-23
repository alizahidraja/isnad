"""Tests for period-sliced grades (issue #43 — the ikhtilāṭ remedy).

A narrator who was sound and then declined (or was quarantined) has their
record *dated*, not discarded: ``get_grade_as_of(...)`` re-derives the grade
from the append-only evidence log up to a past instant.

The canonical case is the sleeper narrator (see the xz case study): RELIABLE
for a long genuine run, then caught and quarantined.  The pre-decline slice
must still read RELIABLE; the post-decline slice must read REJECTED.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from isnad.core.registry import Registry
from isnad.types import EvidenceAction, EvidenceType, NarratorGrade, Role


def _sleeper(reg: Registry, domain: str = "xz") -> tuple[datetime, datetime]:
    """Build a sleeper narrator: 30 genuine survivals, then a quarantine.

    Returns (pre_decline, post_decline) timestamps straddling the quarantine.
    """
    reg.register("jia", domain)
    for i in range(30):
        reg.record_survival("jia", domain, f"c-{i}", "gov.uk")
    pre = datetime.now(UTC)
    reg.quarantine("jia", domain, "caught injecting a backdoor")
    post = datetime.now(UTC)
    return pre, post


class TestPeriodSlicedGrades:
    def test_pre_decline_is_reliable_post_decline_is_rejected(self) -> None:
        reg = Registry()
        pre, post = _sleeper(reg)
        assert reg.get_grade_as_of("jia", "xz", pre) == NarratorGrade.RELIABLE
        assert reg.get_grade_as_of("jia", "xz", post) == NarratorGrade.REJECTED
        # The live grade is the post-decline (quarantined) state.
        assert reg.get_grade("jia", "xz") == NarratorGrade.REJECTED

    def test_slice_before_any_evidence_is_ungraded(self) -> None:
        reg = Registry()
        pre, _ = _sleeper(reg)
        assert reg.get_grade_as_of("jia", "xz", pre - timedelta(hours=1)) == NarratorGrade.UNGRADED

    def test_unknown_narrator_is_ungraded(self) -> None:
        reg = Registry()
        assert (
            reg.get_grade_as_of("nobody", "anywhere", datetime.now(UTC)) == NarratorGrade.UNGRADED
        )

    def test_precision_decline_is_reconstructed_without_quarantine(self) -> None:
        """A precision jarḥ (no quarantine) also slices: before it, RELIABLE;
        after it, the precision grade drops."""
        reg = Registry()
        reg.register("m", "d")
        for i in range(10):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk")
        pre = datetime.now(UTC)
        reg.record_evidence("m", "d", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH)
        post = datetime.now(UTC)
        assert reg.get_grade_as_of("m", "d", pre) == NarratorGrade.RELIABLE
        # After a single precision jarḥ, the Beta drops from RELIABLE.
        assert reg.get_grade_as_of("m", "d", post) == NarratorGrade.ACCEPTABLE


class TestRoleScopedSlicing:
    def test_role_precision_slices_independently(self) -> None:
        reg = Registry()
        reg.register("m", "d")
        for i in range(30):
            reg.record_survival("m", "d", f"c-{i}", "gov.uk", role=Role.SYNTHESIS)
        pre = datetime.now(UTC)
        assert reg.get_grade_as_of("m", "d", pre, role=Role.SYNTHESIS) == NarratorGrade.RELIABLE
        # A sibling role was never fed evidence → UNGRADED.
        assert reg.get_grade_as_of("m", "d", pre, role=Role.EXTRACTION) == NarratorGrade.UNGRADED


class TestQuarantineMarkerRoundTrips:
    def test_period_slicing_survives_db_round_trip(self, tmp_path) -> None:
        import tempfile

        from sqlalchemy.orm import Session

        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine

        with tempfile.TemporaryDirectory() as d:
            url = f"sqlite:///{d}/ps.db"
            reset_engine()
            init_db(url)
            engine = create_engine_from_url(url)

            with Session(engine) as s:
                rdb = RegistryDB(session=s)
                pre, _ = _sleeper(rdb.registry)
                rdb.flush()
                s.commit()

            with Session(engine) as s:
                rdb2 = RegistryDB(session=s)
                rdb2.load()
                # The __quarantine__ marker round-tripped, so the slice before
                # the decline still reads RELIABLE and after reads REJECTED.
                assert rdb2.registry.get_grade_as_of("jia", "xz", pre) == NarratorGrade.RELIABLE
                assert (
                    rdb2.registry.get_grade_as_of("jia", "xz", datetime.now(UTC))
                    == NarratorGrade.REJECTED
                )

            reset_engine()
