"""Tests for version-aware narrator identity (endpoint drift fix)."""

from isnad.core.chain import Chain, ChainLinkSpec, grades_for_chain, resolved_narrator_ids_for_chain
from isnad.core.decision import decide
from isnad.core.grading import grade_chain
from isnad.core.identity import is_unknown_version, parse_narrator_id, resolve_narrator_id
from isnad.core.registry import Registry
from isnad.matn import DeterministicRuleCritic
from isnad.types import NarratorGrade, TransformType


class TestResolveNarratorId:
    def test_version_appended(self) -> None:
        assert resolve_narrator_id("ingest-model-v3", "2.0") == "ingest-model-v3@2.0"

    def test_unknown_version_returns_alias(self) -> None:
        assert resolve_narrator_id("ingest-model-v3", "unknown") == "ingest-model-v3"
        assert resolve_narrator_id("ingest-model-v3", None) == "ingest-model-v3"

    def test_already_versioned_is_idempotent(self) -> None:
        assert resolve_narrator_id("ingest-model-v3@1.0", "2.0") == "ingest-model-v3@1.0"

    def test_parse_roundtrip(self) -> None:
        assert parse_narrator_id("ingest-model-v3@2.0") == ("ingest-model-v3", "2.0")
        assert parse_narrator_id("plain-source") == ("plain-source", None)

    def test_is_unknown_version(self) -> None:
        assert is_unknown_version("unknown") is True
        assert is_unknown_version("2.0") is False


class TestVersionedRegistryGrading:
    def test_different_version_does_not_inherit_grade(self) -> None:
        reg = Registry()
        reg.register_versioned("ingest-model-v3", "physics", "1.0", grade=NarratorGrade.RELIABLE)

        chain = Chain([
            ChainLinkSpec("ingest-model-v3", 0, domain="physics", version="2.0"),
        ])
        grades = grades_for_chain(reg, chain)
        assert grades == [NarratorGrade.UNGRADED]

    def test_same_version_gets_grade(self) -> None:
        reg = Registry()
        reg.register_versioned("ingest-model-v3", "physics", "1.0", grade=NarratorGrade.RELIABLE)

        chain = Chain([
            ChainLinkSpec("ingest-model-v3", 0, domain="physics", version="1.0"),
        ])
        assert grades_for_chain(reg, chain) == [NarratorGrade.RELIABLE]

    def test_legacy_alias_not_used_when_version_present(self) -> None:
        reg = Registry()
        reg.register("ingest-model-v3", "physics", grade=NarratorGrade.RELIABLE)

        chain = Chain([
            ChainLinkSpec("ingest-model-v3", 0, domain="physics", version="2.0"),
        ])
        assert grades_for_chain(reg, chain) == [NarratorGrade.UNGRADED]

    def test_legacy_unknown_version_uses_alias(self) -> None:
        reg = Registry()
        reg.register("ingest-model-v3", "physics", grade=NarratorGrade.RELIABLE)

        chain = Chain([
            ChainLinkSpec("ingest-model-v3", 0, domain="physics", version="unknown"),
        ])
        assert grades_for_chain(reg, chain) == [NarratorGrade.RELIABLE]

    def test_endpoint_drift_pipeline_outcome(self) -> None:
        reg = Registry()
        reg.register_versioned("openstax-textbook", "physics", "2024", grade=NarratorGrade.RELIABLE)
        reg.register_versioned("ingest-model-v3", "physics", "1.0", grade=NarratorGrade.RELIABLE)

        chain = Chain([
            ChainLinkSpec("openstax-textbook", 0, domain="physics", version="2024"),
            ChainLinkSpec(
                "ingest-model-v3",
                1,
                domain="physics",
                version="2.0",
                transform_type=TransformType.GENERATIVE,
            ),
        ])
        link_grades = grades_for_chain(reg, chain)
        cg = grade_chain(link_grades, [l.transform_type for l in chain.links], is_complete=True)
        action = decide(cg, DeterministicRuleCritic().evaluate("p=h/l", "p=h/l", [], "physics"))

        assert resolved_narrator_ids_for_chain(chain) == [
            "openstax-textbook@2024",
            "ingest-model-v3@2.0",
        ]
        assert link_grades[1] == NarratorGrade.UNGRADED
        assert action.value == "review"


class TestAliasGradedIndex:
    def test_has_graded_sibling_versions(self) -> None:
        reg = Registry()
        reg.register_versioned("ingest-model-v3", "physics", "1.0", grade=NarratorGrade.RELIABLE)

        assert reg.has_graded_sibling_versions(
            "ingest-model-v3",
            "physics",
            "ingest-model-v3@2.0",
        )
        assert not reg.has_graded_sibling_versions(
            "ingest-model-v3",
            "physics",
            "ingest-model-v3@1.0",
        )

    def test_sibling_index_cleared_when_grade_removed(self) -> None:
        reg = Registry()
        reg.register_versioned("ingest-model-v3", "physics", "1.0", grade=NarratorGrade.RELIABLE)
        reg.bump_version("ingest-model-v3@1.0", "physics", "1.1")

        assert not reg.has_graded_sibling_versions(
            "ingest-model-v3",
            "physics",
            "ingest-model-v3@2.0",
        )

    def test_scale_independent_of_unrelated_narrators(self) -> None:
        reg = Registry()
        for i in range(1000):
            reg.register(f"other-narrator-{i}", "physics", grade=NarratorGrade.RELIABLE)
        reg.register_versioned("ingest-model-v3", "physics", "1.0", grade=NarratorGrade.RELIABLE)

        assert reg.has_graded_sibling_versions(
            "ingest-model-v3",
            "physics",
            "ingest-model-v3@2.0",
        )

    def test_rebuild_index_after_db_load(self) -> None:
        import os

        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import drop_db, get_session_factory, init_db, reset_engine

        db_url = "sqlite:///data/isnad_alias_index_test.db"
        os.environ["ISNAD_DATABASE_URL"] = db_url
        reset_engine()
        drop_db(db_url)
        init_db(db_url)

        factory = get_session_factory()
        session = factory()
        try:
            reg_db = RegistryDB(session=session)
            reg_db.registry.register_versioned(
                "ingest-model-v3",
                "physics",
                "1.0",
                grade=NarratorGrade.RELIABLE,
            )
            reg_db.flush()
            session.commit()

            session2 = factory()
            try:
                reloaded = RegistryDB(session=session2)
                reloaded.load()
                assert reloaded.registry.has_graded_sibling_versions(
                    "ingest-model-v3",
                    "physics",
                    "ingest-model-v3@2.0",
                )
            finally:
                session2.close()
        finally:
            session.close()
            drop_db(db_url)
            reset_engine()
