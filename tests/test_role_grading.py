"""Tests for per-role precision grading (issue #3).

The axis split maps onto the role split:

- Integrity (ʿadālah) is per (narrator, domain) — one judgment of the person,
  shared across roles.  Quarantine spans every role.
- Precision (ḍabṭ) is per (narrator, role, domain) — extraction competence
  does not imply synthesis competence.

Backward compatibility: ``role=None`` (the default, and every legacy caller)
keeps the ``(narrator, domain)`` key and today's behaviour bit-for-bit.
"""

from __future__ import annotations

from isnad.core.registry import Registry
from isnad.types import (
    AdalahGrade,
    EvidenceProvenance,
    EvidenceType,
    NarratorGrade,
    Role,
    provenance_of,
)


class TestRoleScopedPrecision:
    def test_same_narrator_independent_grades_per_role(self) -> None:
        reg = Registry()
        reg.register("model-M", "physics", grade=NarratorGrade.RELIABLE)
        reg.register("model-M", "physics", role=Role.SYNTHESIS, grade=NarratorGrade.WEAK)
        reg.register("model-M", "physics", role=Role.EXTRACTION, grade=NarratorGrade.ACCEPTABLE)

        assert reg.get_grade("model-M", "physics") == NarratorGrade.RELIABLE
        assert reg.get_grade("model-M", "physics", role=Role.SYNTHESIS) == NarratorGrade.WEAK
        assert reg.get_grade("model-M", "physics", role=Role.EXTRACTION) == NarratorGrade.ACCEPTABLE

    def test_role_grades_do_not_leak_across_roles(self) -> None:
        reg = Registry()
        reg.register("model-M", "physics", role=Role.SYNTHESIS, grade=NarratorGrade.WEAK)

        # A different role has no record → falls back to default (UNGRADED).
        assert reg.get_grade("model-M", "physics", role=Role.RETRIEVAL) == NarratorGrade.UNGRADED
        # The default record is untouched.
        assert reg.get_grade("model-M", "physics") == NarratorGrade.UNGRADED

    def test_unknown_role_falls_back_to_default(self) -> None:
        reg = Registry()
        reg.register("model-M", "physics", grade=NarratorGrade.ACCEPTABLE)
        # No role record → the default precision grade is the fallback.
        assert reg.get_grade("model-M", "physics", role=Role.TOOL) == NarratorGrade.ACCEPTABLE


class TestLegacyCompatibility:
    def test_no_role_is_unchanged(self) -> None:
        """role=None keeps today's (narrator, domain) behaviour exactly."""
        reg = Registry()
        reg.register("model-M", "physics", grade=NarratorGrade.RELIABLE)
        # A default record has role None and its grade reads back as stored.
        assert reg.get_grade("model-M", "physics") == NarratorGrade.RELIABLE
        assert reg.get("model-M", "physics").role is None
        # Survival recorded without a role lands on the default record.
        reg.record_survival("model-M", "physics", "c1", "gov.uk")
        assert reg.evidence_provenance("model-M", "physics").observed_count == 1
        assert (
            reg.evidence_provenance("model-M", "physics", role=Role.SYNTHESIS).observed_count == 0
        )

    def test_contains_len_are_backward_compatible(self) -> None:
        reg = Registry()
        reg.register("a", "d")
        reg.register("b", "d")
        assert ("a", "d") in reg
        assert len(reg) == 2
        # Adding a role record increments the count but keeps 2-tuple membership.
        reg.register("a", "d", role=Role.SYNTHESIS)
        assert len(reg) == 3
        assert ("a", "d") in reg


class TestIntegritySpansRoles:
    def test_quarantine_floors_every_role(self) -> None:
        reg = Registry()
        reg.register("liar", "d", grade=NarratorGrade.RELIABLE)
        reg.register("liar", "d", role=Role.SYNTHESIS, grade=NarratorGrade.RELIABLE)
        reg.register("liar", "d", role=Role.RETRIEVAL, grade=NarratorGrade.ACCEPTABLE)

        reg.quarantine("liar", "d", "caught fabricating")

        assert reg.get_grade("liar", "d") == NarratorGrade.REJECTED
        assert reg.get_grade("liar", "d", role=Role.SYNTHESIS) == NarratorGrade.REJECTED
        assert reg.get_grade("liar", "d", role=Role.RETRIEVAL) == NarratorGrade.REJECTED

    def test_quarantine_blocks_role_precision_recovery(self) -> None:
        """A flood of role-scoped survival cannot lift an integrity quarantine."""
        reg = Registry()
        reg.register("liar", "d", grade=NarratorGrade.RELIABLE)
        reg.quarantine("liar", "d", "caught fabricating")
        for i in range(20):
            reg.record_survival("liar", "d", f"c-{i}", "gov.uk", role=Role.SYNTHESIS)
        assert reg.get_grade("liar", "d", role=Role.SYNTHESIS) == NarratorGrade.REJECTED

    def test_adalah_is_role_independent(self) -> None:
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE, adalah=AdalahGrade.HIGH)
        reg.register("m", "d", role=Role.SYNTHESIS, grade=NarratorGrade.WEAK)
        # Integrity is read from the default record, not the role record.
        assert reg.get_adalah_grade("m", "d") == AdalahGrade.HIGH


class TestRoleScopedEvidence:
    def test_evidence_routes_to_the_role_record(self) -> None:
        reg = Registry()
        reg.register("m", "d", role=Role.SYNTHESIS, grade=NarratorGrade.UNGRADED)
        # Survival is precision evidence → moves only the synthesis role.
        reg.record_survival("m", "d", "c1", "gov.uk", role=Role.SYNTHESIS)
        prov = reg.evidence_provenance("m", "d", role=Role.SYNTHESIS)
        assert prov.observed_count == 1
        # The default record is untouched.
        assert reg.evidence_provenance("m", "d").observed_count == 0

    def test_evidence_provenance_is_role_scoped(self) -> None:
        reg = Registry()
        reg.register("m", "d")
        reg.record_survival("m", "d", "c1", "gov.uk", role=Role.SYNTHESIS)
        reg.record_survival("m", "d", "c2", "gov.uk", role=Role.SYNTHESIS)
        reg.record_survival("m", "d", "c3", "gov.uk", role=Role.RETRIEVAL)

        assert reg.evidence_provenance("m", "d", role=Role.SYNTHESIS).observed_count == 2
        assert reg.evidence_provenance("m", "d", role=Role.RETRIEVAL).observed_count == 1
        assert reg.evidence_provenance("m", "d").observed_count == 0

    def test_survival_dedup_is_role_scoped(self) -> None:
        reg = Registry()
        reg.register("m", "d", role=Role.SYNTHESIS)
        reg.record_survival("m", "d", "c1", "gov.uk", role=Role.SYNTHESIS)
        reg.record_survival("m", "d", "c1", "gov.uk", role=Role.SYNTHESIS)
        assert reg.evidence_provenance("m", "d", role=Role.SYNTHESIS).observed_count == 1


class TestRolePersistence:
    def test_role_records_survive_db_round_trip(self, tmp_path) -> None:
        import tempfile

        from sqlalchemy.orm import Session

        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine

        with tempfile.TemporaryDirectory() as d:
            url = f"sqlite:///{d}/role.db"
            reset_engine()
            init_db(url)
            engine = create_engine_from_url(url)

            with Session(engine) as s:
                rdb = RegistryDB(session=s)
                rdb.registry.register("m", "d", grade=NarratorGrade.RELIABLE)
                rdb.registry.register("m", "d", role=Role.SYNTHESIS, grade=NarratorGrade.WEAK)
                rdb.registry.record_survival("m", "d", "c1", "gov.uk", role=Role.SYNTHESIS)
                rdb.flush()
                s.commit()

            with Session(engine) as s:
                rdb2 = RegistryDB(session=s)
                rdb2.load()
                assert rdb2.registry.get_grade("m", "d") == NarratorGrade.RELIABLE
                assert rdb2.registry.get_grade("m", "d", role=Role.SYNTHESIS) == NarratorGrade.WEAK
                assert (
                    rdb2.registry.evidence_provenance("m", "d", role=Role.SYNTHESIS).observed_count
                    == 1
                )

            reset_engine()


class TestVersionBumpResetsRoles:
    def test_bump_version_resets_role_precision(self) -> None:
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.RELIABLE)
        reg.register("m", "d", role=Role.SYNTHESIS, grade=NarratorGrade.RELIABLE)

        reg.bump_version("m", "d", "v2")

        assert reg.get_grade("m", "d") == NarratorGrade.UNGRADED
        assert reg.get_grade("m", "d", role=Role.SYNTHESIS) == NarratorGrade.UNGRADED


class TestAliasIndexNotCorruptedByRoles:
    def test_role_ungraded_does_not_mask_graded_default(self) -> None:
        """A role record's UNGRADED must not remove a graded default version
        from the version-drift alias index."""
        reg = Registry()
        reg.register("model:X@v1", "d", grade=NarratorGrade.RELIABLE)
        reg.register("model:X@v1", "d", role=Role.SYNTHESIS, grade=NarratorGrade.UNGRADED)
        assert reg.has_graded_sibling_versions("model:X", "d", exclude_resolved="model:X@v2")

    def test_ungraded_default_does_not_mask_graded_role(self) -> None:
        """Conversely, a graded role keeps the narrator in the alias index even
        when the default record is UNGRADED."""
        reg = Registry()
        reg.register("model:X@v1", "d", grade=NarratorGrade.UNGRADED)
        reg.register("model:X@v1", "d", role=Role.SYNTHESIS, grade=NarratorGrade.RELIABLE)
        assert reg.has_graded_sibling_versions("model:X", "d", exclude_resolved="model:X@v2")


class TestSurvivalClassification:
    def test_survival_is_observed(self) -> None:
        assert provenance_of(EvidenceType.SURVIVAL) == EvidenceProvenance.OBSERVED


class TestRoleIdentityAndIntegrity:
    def test_role_inherits_narrator_type_from_default(self) -> None:
        """narrator_type drives the volatility TTL; a role must not default to MODEL."""
        from isnad.types import NarratorType

        reg = Registry()
        reg.register("src", "d", narrator_type=NarratorType.SOURCE, grade=NarratorGrade.RELIABLE)
        reg.register("src", "d", role=Role.SOURCE, grade=NarratorGrade.RELIABLE)
        role_rec = reg.get("src", "d", role=Role.SOURCE)
        assert role_rec.narrator_type == NarratorType.SOURCE

    def test_adalah_is_unassessed_when_only_role_record_exists(self) -> None:
        """Integrity lives on the default record; no default → UNASSESSED."""
        reg = Registry()
        reg.register("m", "d", role=Role.SYNTHESIS, grade=NarratorGrade.WEAK)
        assert reg.get_adalah_grade("m", "d") == AdalahGrade.UNASSESSED

    def test_rejected_default_floors_role_even_without_quarantine(self) -> None:
        """Conservative floor: a REJECTED default record floors every role."""
        reg = Registry()
        reg.register("m", "d", grade=NarratorGrade.REJECTED)
        reg.register("m", "d", role=Role.SYNTHESIS, grade=NarratorGrade.RELIABLE)
        assert reg.get_grade("m", "d", role=Role.SYNTHESIS) == NarratorGrade.REJECTED

    def test_flag_contradiction_routes_to_role(self) -> None:
        """A role-scoped contradiction only impugns that role's precision."""
        reg = Registry()
        reg.register("m", "d", role=Role.SYNTHESIS, grade=NarratorGrade.RELIABLE)
        reg.register("m", "d", role=Role.RETRIEVAL, grade=NarratorGrade.RELIABLE)
        reg.flag_contradiction("m", "d", "contradicted", role=Role.SYNTHESIS)
        # The synthesis role's precision was impugned; retrieval was not.
        assert reg.evidence_provenance("m", "d", role=Role.SYNTHESIS).observed_count == 1
        assert reg.evidence_provenance("m", "d", role=Role.RETRIEVAL).observed_count == 0

    def test_renew_grade_scoped_to_role(self) -> None:
        """Freshness renewal applies to the role it targets, not the default."""
        from datetime import UTC, datetime, timedelta

        reg = Registry()
        reg.register(
            "m",
            "d",
            role=Role.SYNTHESIS,
            grade=NarratorGrade.ACCEPTABLE,
            graded_at=datetime.now(UTC) - timedelta(days=200),
        )
        assert reg.renew_grade("m", "d", role=Role.SYNTHESIS) is True
