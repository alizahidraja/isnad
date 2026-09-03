"""Regression tests for examples/self-maintaining-kb/kb.py (Recipe 1).

The demo lives in a hyphenated directory (``examples/self-maintaining-kb``),
which is not a valid Python module path, so it is loaded by file path and its
pure functions are driven against an in-memory ``Registry`` — no stdout, no
API keys, no database.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from isnad import Registry
from isnad.types import Action, AdalahGrade, ChainGrade, NarratorGrade

_KB_PATH = Path(__file__).resolve().parents[1] / "examples" / "self-maintaining-kb" / "kb.py"
_SPEC = importlib.util.spec_from_file_location("isnad_kb_demo", _KB_PATH)
assert _SPEC is not None and _SPEC.loader is not None
kb = importlib.util.module_from_spec(_SPEC)
sys.modules[kb.__name__] = kb  # dataclasses need the module registered in sys.modules
_SPEC.loader.exec_module(kb)


@pytest.fixture()
def reg() -> Registry:
    registry = Registry()
    kb.seed_priors(registry)
    return registry


def test_weakest_link_and_review(reg: Registry) -> None:
    verdict = kb.grade_claim(reg, kb.CLAIM_B, kb.CHAIN_B, kb.CORPUS_DOCS["B"])
    assert verdict.chain_grade == ChainGrade.DAIF
    assert verdict.weakest_link == "scraper:web-generic"
    assert verdict.weakest_grade == NarratorGrade.WEAK
    assert verdict.action == Action.REVIEW


def test_prior_only_caveat(reg: Registry) -> None:
    provenance = reg.evidence_provenance("source:internal-docs", kb.DOMAIN)
    assert provenance.prior_only is True
    verdict = kb.grade_claim(reg, kb.CLAIM_A, kb.CHAIN_A, kb.CORPUS_DOCS["A"])
    assert verdict.prior_only is True
    assert verdict.action == Action.SERVE_WITH_CAVEAT


def test_survival_upgrades_to_serve(reg: Registry) -> None:
    before = kb.grade_claim(reg, kb.CLAIM_A, kb.CHAIN_A, kb.CORPUS_DOCS["A"])
    reg.record_survival(
        "source:internal-docs",
        kb.DOMAIN,
        kb.make_claim_id(kb.CLAIM_A),
        "source:changelog",
    )
    provenance = reg.evidence_provenance("source:internal-docs", kb.DOMAIN)
    assert provenance.observation_backed is True
    assert provenance.prior_only is False
    after = kb.grade_claim(reg, kb.CLAIM_A, kb.CHAIN_A, kb.CORPUS_DOCS["A"])
    # Only the action/provenance flip; text and chain grade are unchanged.
    assert after.action == Action.SERVE
    assert after.chain_grade == before.chain_grade
    assert after.text == before.text


def test_contradiction_downgrades(reg: Registry) -> None:
    reg.record_survival(
        "source:internal-docs",
        kb.DOMAIN,
        kb.make_claim_id(kb.CLAIM_A),
        "source:changelog",
    )
    served = kb.grade_claim(reg, kb.CLAIM_A, kb.CHAIN_A, kb.CORPUS_DOCS["A"])
    assert served.action == Action.SERVE
    reg.flag_contradiction("source:internal-docs", kb.DOMAIN, "release notes disagree")
    after = kb.grade_claim(reg, kb.CLAIM_A, kb.CHAIN_A, kb.CORPUS_DOCS["A"])
    assert after.action != Action.SERVE
    assert after.chain_grade == ChainGrade.HASAN


def test_quarantine_containment(reg: Registry) -> None:
    va = kb.grade_claim(reg, kb.CLAIM_A, kb.CHAIN_A, kb.CORPUS_DOCS["A"])
    vb = kb.grade_claim(reg, kb.CLAIM_B, kb.CHAIN_B, kb.CORPUS_DOCS["B"])
    vc = kb.grade_claim(reg, kb.CLAIM_C, kb.CHAIN_C, kb.CORPUS_DOCS["C"])
    assert vc.action == Action.REJECT_AND_QUARANTINE_NARRATOR
    assert [v.text for v in kb.served_surface([va, vb, vc])] == [kb.CLAIM_A]

    reg.quarantine("source:fabricated-bot", kb.DOMAIN, "fabricated claims")
    narrator = reg.get("source:fabricated-bot", kb.DOMAIN)
    assert narrator is not None
    assert narrator.grade == NarratorGrade.REJECTED
    assert narrator.adalah_grade == AdalahGrade.COMPROMISED
    assert narrator.is_active is False

    vc_after = kb.grade_claim(reg, kb.CLAIM_C, kb.CHAIN_C, kb.CORPUS_DOCS["C"])
    # Still excluded from the served surface after quarantine.
    assert [v.text for v in kb.served_surface([va, vb, vc_after])] == [kb.CLAIM_A]


def test_honest_survival_noop(reg: Registry) -> None:
    before = reg.get_grade("source:internal-docs", kb.DOMAIN)
    # Self-verified survival is refused: grade unchanged, nothing logged.
    reg.record_survival(
        "source:internal-docs",
        kb.DOMAIN,
        "claim-x",
        "self-seal",
        self_verified=True,
    )
    assert reg.get_grade("source:internal-docs", kb.DOMAIN) == before
    assert reg.evidence_provenance("source:internal-docs", kb.DOMAIN).observed_count == 0

    # Claim-scoped dedup: re-verifying the same (claim, source) is a no-op.
    claim_id = kb.make_claim_id(kb.CLAIM_A)
    reg.record_survival("source:internal-docs", kb.DOMAIN, claim_id, "source:changelog")
    assert reg.evidence_provenance("source:internal-docs", kb.DOMAIN).observed_count == 1
    reg.record_survival("source:internal-docs", kb.DOMAIN, claim_id, "source:changelog")
    assert reg.evidence_provenance("source:internal-docs", kb.DOMAIN).observed_count == 1


def test_survival_dedup_is_alias_aware(reg: Registry) -> None:
    """Re-verifying via a versioned alias of the same source does not double-count."""
    claim_id = kb.make_claim_id(kb.CLAIM_A)
    reg.record_survival("source:internal-docs", kb.DOMAIN, claim_id, "source:changelog")
    reg.record_survival("source:internal-docs", kb.DOMAIN, claim_id, "source:changelog@v1")
    assert reg.evidence_provenance("source:internal-docs", kb.DOMAIN).observed_count == 1


def test_survival_refuses_blank_or_empty_alias_source(reg: Registry) -> None:
    """A blank, whitespace, or alias-less verifier source is refused."""
    grade = reg.get_grade("source:internal-docs", kb.DOMAIN)
    for bad_source in ("", "   ", "@", "@v1"):
        assert (
            reg.record_survival("source:internal-docs", kb.DOMAIN, "claim-blank", bad_source)
            == grade
        )
    assert reg.evidence_provenance("source:internal-docs", kb.DOMAIN).observed_count == 0


def test_survival_refuses_self_seal(reg: Registry) -> None:
    """A self-seal (source == narrator) is refused as non-independent."""
    grade = reg.get_grade("source:internal-docs", kb.DOMAIN)
    assert (
        reg.record_survival(
            "source:internal-docs", kb.DOMAIN, "claim-self-seal", "source:internal-docs"
        )
        == grade
    )
    # A versioned alias of the narrator is still a self-seal.
    assert (
        reg.record_survival(
            "source:internal-docs", kb.DOMAIN, "claim-self-seal-v", "source:internal-docs@v1"
        )
        == grade
    )
    assert reg.evidence_provenance("source:internal-docs", kb.DOMAIN).observed_count == 0
