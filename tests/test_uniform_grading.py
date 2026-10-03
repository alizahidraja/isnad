"""Behavioral-equivalence regression test — the 3.0.0 uniform-grading bug.

Mapping v2 keys MAWDU on the integrity axis (COMPROMISED → MAWDU). The 3.0.0
regression: only 3 of 11 ``grade_chain`` call sites passed ``link_adalah_grades``,
so a COMPROMISED narrator graded ``mawdu`` in the API but ``daif_jiddan`` in the
audit exporter and integrations — the audit record contradicted the decision
served. This test pins the fix: the same chain grades the same everywhere.
"""

from __future__ import annotations

from isnad.core.chain import Chain, ChainLinkSpec, grade_chain_from_registry
from isnad.core.registry import Registry
from isnad.integrations.crewai import CrewLineageCollector
from isnad.quick import grade as quick_grade
from isnad.types import AdalahGrade, ChainGrade, NarratorGrade


def _compromised_registry() -> Registry:
    reg = Registry()
    reg.register("src", "physics", grade=NarratorGrade.RELIABLE)
    reg.register(
        "bad",
        "physics",
        grade=NarratorGrade.REJECTED,
        adalah=AdalahGrade.COMPROMISED,
    )
    return reg


def _chain() -> Chain:
    return Chain([
        ChainLinkSpec("src", 0, domain="physics"),
        ChainLinkSpec("bad", 1, domain="physics"),
    ])


def test_helper_grades_compromised_narrator_mawdu() -> None:
    assert grade_chain_from_registry(_compromised_registry(), _chain()) == ChainGrade.MAWDU


def test_quick_grade_matches_helper() -> None:
    reg = _compromised_registry()
    v = quick_grade("p = mv", ["src", "bad"], reg, domain="physics")
    assert v.chain_grade == ChainGrade.MAWDU
    assert v.chain_grade == grade_chain_from_registry(reg, _chain())


def test_crewai_grade_matches_helper() -> None:
    reg = Registry()
    reg.register("src", "physics", grade=NarratorGrade.RELIABLE)
    reg.register(
        "agent:bad",
        "physics",
        grade=NarratorGrade.REJECTED,
        adalah=AdalahGrade.COMPROMISED,
    )
    c = CrewLineageCollector(reg, "physics")
    c.record_agent("bad")
    out = c.grade()
    assert out["chain_grade"] == "mawdu"


def test_suspect_rejected_narrator_grades_daif_jiddan_not_mawdu() -> None:
    reg = Registry()
    reg.register("src", "physics", grade=NarratorGrade.RELIABLE)
    reg.register(
        "bad",
        "physics",
        grade=NarratorGrade.REJECTED,
        adalah=AdalahGrade.SUSPECT,
    )
    chain = Chain([
        ChainLinkSpec("src", 0, domain="physics"),
        ChainLinkSpec("bad", 1, domain="physics"),
    ])
    assert grade_chain_from_registry(reg, chain) == ChainGrade.DAIF_JIDDAN


def test_audit_record_matches_served_grade() -> None:
    import tempfile

    from sqlalchemy.orm import Session

    from isnad.audit import build_audit_record
    from isnad.core.chain import hash_claim_text, normalize_claim_text, store_claim
    from isnad.core.registry import RegistryDB
    from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine

    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite:///{d}/a.db"
        reset_engine()
        init_db(url)
        engine = create_engine_from_url(url)
        with Session(engine) as s:
            rdb = RegistryDB(session=s)
            rdb.registry.register("src", "physics", grade=NarratorGrade.RELIABLE)
            rdb.registry.register(
                "bad",
                "physics",
                grade=NarratorGrade.REJECTED,
                adalah=AdalahGrade.COMPROMISED,
            )
            chain = _chain()
            store_claim(s, "p = mv", "page", chain, chain_grade="mawdu")
            s.commit()
            cid = hash_claim_text(normalize_claim_text("p = mv"))
            rec = build_audit_record(cid, s, rdb.registry)
            assert rec.final_grade == "mawdu"
            assert rec.final_grade == grade_chain_from_registry(rdb.registry, chain).value
        reset_engine()
