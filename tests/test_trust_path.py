"""Trust-path regressions found auditing v3.0.2 (5 Oct 2026).

Each test encodes a property the paper or the mapping-v2 changelog states.
On v3.0.2 the API tests below fail; each should pass once its fix lands.
The core property tests pass on v3.0.2 and guard the gap fix from now on.

Drop into tests/ (the repo conftest sets ISNAD_API_KEYS).
"""

from __future__ import annotations

import itertools
import os

import pytest
from fastapi.testclient import TestClient

from isnad.api.app import app
from isnad.api.endpoints.claims import _app_state
from isnad.core.grading import grade_chain
from isnad.critics.embedding import _has_contradiction_signal
from isnad.storage.sqlalchemy import drop_db, init_db, reset_engine
from isnad.types import AdalahGrade, ChainGrade, ContentVerdict, NarratorGrade, TransformType

TEST_DB_URL = os.environ.get("ISNAD_TRUST_TEST_DB", "sqlite:///data/isnad_trust_path_test.db")
ADMIN = {"X-API-Key": "isnad-admin"}
SERVED = {"serve", "serve_with_caveat"}
client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_state():
    os.environ["ISNAD_DATABASE_URL"] = TEST_DB_URL
    reset_engine()
    drop_db(TEST_DB_URL)
    init_db(TEST_DB_URL)
    _app_state.claims.clear()
    _app_state._corroboration_index.clear()
    yield
    _app_state.claims.clear()
    _app_state._corroboration_index.clear()


def _register(nid: str, grade: str, domain: str = "physics") -> None:
    r = client.post(
        "/v1/narrators",
        json={"narrator_id": nid, "domain": domain, "grade": grade},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text


def _submit(text: str, chain: list[dict], domain: str = "physics", **extra: object) -> dict:
    body = {"claim_text": text, "domain": domain, "chain": chain, **extra}
    r = client.post("/v1/claims", json=body, headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


def _grade(nid: str, domain: str = "physics") -> str:
    r = client.get(f"/v1/narrators/{nid}", params={"domain": domain}, headers=ADMIN)
    return r.json()["grade"]


# ---------------------------------------------------------------------------
# API trust path (all three fail on v3.0.2)
# ---------------------------------------------------------------------------

RAG_CHAIN = [
    {"narrator_id": "source:docs", "transform_type": "pass_through"},
    {"narrator_id": "scraper:x", "transform_type": "destructive"},
    {"narrator_id": "model:synth", "transform_type": "generative"},
]


@pytest.mark.parametrize("extractor_grade", ["weak", "ungraded"])
def test_resubmitting_the_same_claim_is_not_corroboration(extractor_grade: str) -> None:
    """A client retry of an identical claim through an identical chain is the same
    lineage, not an independent route (madār). It must not change the grade or
    turn a held claim into a served one. v3.0.2: ḍaʿīf/review, then ṣaḥīḥ/served,
    via claims.py `corroboration_support=has_corroborating` (no lineage check)."""
    _register("source:docs", "reliable")
    _register("scraper:x", extractor_grade)
    _register("model:synth", "reliable")
    text = "Energy is conserved in every closed system"
    first = _submit(text, RAG_CHAIN)
    second = _submit(text, RAG_CHAIN)
    assert first["action"] not in SERVED
    assert second["chain_grade"] == first["chain_grade"]
    assert second["action"] not in SERVED


@pytest.mark.parametrize(
    "text",
    [
        "speed of light is 2.5e8 m/s",
        "water boils at 100 C at 1 atm",
        "the release shipped 2026-08-29",
    ],
)
def test_a_claim_never_contradicts_itself(text: str) -> None:
    """v3.0.2: the numeric check compares every number in one claim with every
    number in the other, so two numbers more than 3x apart self-contradict."""
    assert not _has_contradiction_signal(text, text)


def test_onboarding_example_is_not_a_contradiction() -> None:
    """The exact example in docs/onboard-in-a-day.md, with its own supporting doc.
    v3.0.2: CONTRADICTION on the first call, source drops RELIABLE -> REJECTED."""
    _register("source:internal-docs", "reliable", domain="kb")
    out = _submit(
        "the release shipped 2026-08-29",
        [{"narrator_id": "source:internal-docs"}],
        domain="kb",
        corpus_docs=["release notes: shipped 2026-08-29"],
    )
    assert out["content_verdict"] != "contradiction"
    assert _grade("source:internal-docs", domain="kb") == "reliable"


def test_quarantine_does_not_brand_reliable_co_narrators() -> None:
    """Weakest link: the rejected scraper is the binding constraint, not the source
    or the model. v3.0.2 (admin key): one QUARANTINE sets every narrator in the
    chain REJECTED + COMPROMISED, so the source's next correct claim is mawḍūʿ."""
    _register("source:openstax", "reliable")
    _register("scraper:bad", "rejected")
    _register("model:gpt", "reliable")
    bad = _submit(
        "Rubbish claim from the bad scraper",
        [
            {"narrator_id": "source:openstax"},
            {"narrator_id": "scraper:bad", "transform_type": "destructive"},
            {"narrator_id": "model:gpt", "transform_type": "generative"},
        ],
    )
    assert bad["action"] == "quarantine"
    assert _grade("source:openstax") == "reliable"
    assert _grade("model:gpt") == "reliable"
    good = _submit(
        "Newton's second law states F = ma",
        [
            {"narrator_id": "source:openstax"},
            {"narrator_id": "model:gpt", "transform_type": "generative"},
        ],
    )
    assert good["chain_grade"] in {"sahih", "hasan"}


def test_retries_of_a_correct_claim_do_not_quarantine_its_sources() -> None:
    """End to end. v3.0.2: three submissions of a correct two-number claim through
    an all-RELIABLE chain end in mawḍūʿ, and both narrators stay quarantined."""
    _register("source:openstax", "reliable")
    _register("model:gpt", "reliable")
    chain = [
        {"narrator_id": "source:openstax"},
        {"narrator_id": "model:gpt", "transform_type": "generative"},
    ]
    actions = [_submit("Water boils at 100 C at 1 atm", chain)["action"] for _ in range(3)]
    assert "quarantine" not in actions
    assert "reject_and_quarantine_narrator" not in actions
    assert _grade("source:openstax") == "reliable"


# ---------------------------------------------------------------------------
# Core grading properties, exhaustive over chains of 1-2 links
# (pass on v3.0.2 except the marked spec decision)
# ---------------------------------------------------------------------------

RANK = {
    ChainGrade.SAHIH: 0,
    ChainGrade.HASAN: 1,
    ChainGrade.DAIF: 2,
    ChainGrade.DAIF_JIDDAN: 3,
    ChainGrade.MAWDU: 4,
}  # higher = worse
NARRATOR_WORSE = [
    NarratorGrade.RELIABLE,
    NarratorGrade.ACCEPTABLE,
    NarratorGrade.UNGRADED,
    NarratorGrade.WEAK,
    NarratorGrade.REJECTED,
]
ADALAH = [AdalahGrade.UNASSESSED, AdalahGrade.COMPROMISED]  # grading reads only COMPROMISED
FIDELITY = [ContentVerdict.UNVERIFIABLE, ContentVerdict.CONTRADICTION]
TRANSFORMS = list(TransformType)


def _g(ns, ads, ts, complete, corr, fids, lenient) -> ChainGrade:
    return grade_chain(
        list(ns),
        list(ts),
        complete,
        corroboration_support=corr,
        link_adalah_grades=list(ads),
        link_fidelity_verdicts=list(fids),
        lenient_unknown=lenient,
    )


def _chains():
    for n_links in (1, 2):
        for ns in itertools.product(NARRATOR_WORSE, repeat=n_links):
            for ads in itertools.product(ADALAH, repeat=n_links):
                for ts in itertools.product(TRANSFORMS, repeat=n_links):
                    for fids in itertools.product(FIDELITY, repeat=n_links):
                        for corr, lenient in itertools.product((False, True), repeat=2):
                            yield ns, ads, ts, corr, fids, lenient


def test_a_gap_never_raises_the_grade() -> None:
    """Paper v1 §4: an incomplete chain is 'capped at the weak tier' (a ceiling)."""
    bad = [
        c
        for c in _chains()
        if RANK[_g(c[0], c[1], c[2], False, c[3], c[4], c[5])]
        < RANK[_g(c[0], c[1], c[2], True, c[3], c[4], c[5])]
    ]
    assert not bad, f"{len(bad)} chains improve when a gap is added, e.g. {bad[0]}"


def test_a_worse_narrator_never_raises_the_grade() -> None:
    bad = []
    for ns, ads, ts, corr, fids, lenient in _chains():
        for complete in (True, False):
            base = RANK[_g(ns, ads, ts, complete, corr, fids, lenient)]
            for i, n in enumerate(ns):
                for worse in NARRATOR_WORSE[NARRATOR_WORSE.index(n) + 1 :]:
                    ns2 = ns[:i] + (worse,) + ns[i + 1 :]
                    if RANK[_g(ns2, ads, ts, complete, corr, fids, lenient)] < base:
                        bad.append((ns, ns2, ts, complete, corr))
    assert not bad, f"{len(bad)} cases, e.g. {bad[0]}"


def test_removing_corroboration_never_raises_the_grade() -> None:
    bad = [
        c
        for c in _chains()
        if c[3]
        and RANK[_g(c[0], c[1], c[2], True, False, c[4], c[5])]
        < RANK[_g(c[0], c[1], c[2], True, True, c[4], c[5])]
    ]
    assert not bad, f"{len(bad)} cases, e.g. {bad[0]}"


def test_nothing_downstream_recovers_a_destructive_floor() -> None:
    """Paper v1 §4: nothing downstream recovers what the extractor dropped
    (the destructive floor is permanent). Fixed in 3.0.3."""
    grade = grade_chain(
        [NarratorGrade.WEAK, NarratorGrade.RELIABLE],
        [TransformType.DESTRUCTIVE, TransformType.GENERATIVE],
        True,
        corroboration_support=True,
        link_adalah_grades=[AdalahGrade.UNASSESSED] * 2,
    )
    assert RANK[grade] >= RANK[ChainGrade.DAIF]
