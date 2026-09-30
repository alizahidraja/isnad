"""Regression tests for the P0 audit sweep (audit verifiability, corroboration,
security, adalah version resolution)."""

from __future__ import annotations

import asyncio

from isnad.core.chain import Chain, ChainLinkSpec, adalah_grades_for_chain
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.types import AdalahGrade, ChainGrade, NarratorGrade, TransformType


def test_adalah_versioned_compromised_yields_mawdu():
    """A versioned COMPROMISED narrator must force MAWDU (alias@version resolution)."""
    reg = Registry()
    reg.register_versioned(
        "alias", "physics", "v1", grade=NarratorGrade.RELIABLE, adalah=AdalahGrade.COMPROMISED
    )
    chain = Chain([
        ChainLinkSpec(
            "alias",
            step=0,
            version="v1",
            domain="physics",
            transform_type=TransformType.PASS_THROUGH,
        )
    ])
    adalah = adalah_grades_for_chain(reg, chain)
    assert AdalahGrade.COMPROMISED in adalah  # the fix: resolves alias@v1, not alias
    cg = grade_chain(
        [NarratorGrade.RELIABLE],
        [TransformType.PASS_THROUGH],
        is_complete=True,
        link_adalah_grades=adalah,
    )
    assert cg == ChainGrade.MAWDU


class _FakeRegistry:
    def get_metadata(self, nid: str, domain: str) -> dict[str, object]:
        return {"narrator_id": nid}


def test_narrator_metadata_union_includes_corroborating_narrators():
    """Corroborating chains' narrators must be in the metadata (else UNKNOWN_LINEAGE)."""
    from isnad.api.endpoints.claims import _narrator_metadata_for_claims

    meta = _narrator_metadata_for_claims(
        _FakeRegistry(),
        base_narrator_ids=["base-src"],
        all_chain_dicts=[
            {"narrator_ids": ["corr-src"]},
            {"narrator_ids": ["base-src", "corr-2"]},
        ],
        domain="general",
    )
    assert "base-src" in meta
    assert "corr-src" in meta
    assert "corr-2" in meta


def test_list_claims_redacts_claim_text(monkeypatch):
    """The public (served_only) list must not leak raw claim_text (PII)."""
    from isnad.api.endpoints import claims as claims_mod

    class _State:
        claims = {
            "c1": {
                "claim_id": "c1",
                "claim_text": "SECRET-PATIENT-PII",
                "chain_grade": "sahih",
                "action": "serve",
                "domain": "general",
                "corroborating_claims": 0,
                "served": True,
                "normalized_text": "secret",
            }
        }

        def find_corroborating(self, normalized_text, exclude_id):
            return []

    monkeypatch.setattr(claims_mod, "get_state", lambda: _State())

    result = asyncio.run(
        claims_mod.list_claims(served_only=True, api_key=None, domain=None, limit=50, offset=0)
    )
    claim = result["claims"][0]
    assert "claim_text" not in claim
    assert claim.get("claim_text_redacted") is True
