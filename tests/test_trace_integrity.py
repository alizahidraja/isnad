"""Regression: the trace path grades a REJECTED narrator as daif_jiddan, not mawdu.

mapping v2 (3.0.0) keys MAWDU on COMPROMISED integrity; a REJECTED narrator with
merely SUSPECT integrity is very weak (daif_jiddan). The trace schema + callback
must reflect the same split, or the audit record diverges from the served grade.
"""

from __future__ import annotations

from isnad.integrations.langchain.callback import _narrator_grade_to_chain_integrity
from isnad.trace.schema import ChainIntegrity


def test_rejected_narrator_traces_as_daif_jiddan_not_mawdu():
    assert _narrator_grade_to_chain_integrity("rejected") is ChainIntegrity.DAIF_JIDDAN
    assert _narrator_grade_to_chain_integrity("rejected") is not ChainIntegrity.MAWDU


def test_weak_narrator_traces_as_daif():
    assert _narrator_grade_to_chain_integrity("weak") is ChainIntegrity.DAIF


def test_chain_integrity_enum_has_daif_jiddan():
    assert ChainIntegrity.DAIF_JIDDAN.value == "daif_jiddan"
    assert ChainIntegrity.DAIF_JIDDAN in ChainIntegrity


def test_unknown_grade_traces_as_ungraded():
    assert _narrator_grade_to_chain_integrity("not-a-grade") is ChainIntegrity.UNGRADED
