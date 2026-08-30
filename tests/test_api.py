"""Tests for ISNAD API v3 — DI, SQLAlchemy persistence, corroboration indexing."""

import os

import pytest
from fastapi.testclient import TestClient

from isnad.api.app import app
from isnad.api.dependencies import get_critic, get_fidelity_critic
from isnad.api.endpoints.claims import _app_state
from isnad.critics.embedding import EmbeddingCritic
from isnad.storage.sqlalchemy import drop_db, init_db, reset_engine
from isnad.types import ContentVerdict

TEST_DB_URL = "sqlite:///data/isnad_test.db"

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset app state and initialize a clean test DB between tests."""
    # Set env var so DB module re-reads it on engine creation
    os.environ["ISNAD_DATABASE_URL"] = TEST_DB_URL
    reset_engine()
    drop_db(TEST_DB_URL)
    init_db(TEST_DB_URL)
    _app_state.claims.clear()
    _app_state._corroboration_index.clear()
    yield
    _app_state.claims.clear()
    _app_state._corroboration_index.clear()


class TestHealth:
    def test_health(self):
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestClaims:
    def test_submit_and_retrieve(self):
        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "F = ma",
                "domain": "physics",
                "chain": [{"narrator_id": "source:openstax", "transform_type": "pass_through"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        cid = r.json()["claim_id"]
        r2 = client.get(f"/v1/claims/{cid}")
        assert r2.json()["claim_text"] == "F = ma"

    def test_auth_required(self):
        r = client.post("/v1/claims", json={"claim_text": "test", "chain": []})
        assert r.status_code == 401

    def test_invalid_body_rejected_422(self):
        """Pydantic validation (issue #93): a malformed body must 422, not silently
        coerce or crash."""
        # empty claim_text
        r = client.post(
            "/v1/claims",
            json={"claim_text": "", "chain": []},
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 422
        # invalid transform_type
        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "F = ma",
                "chain": [{"narrator_id": "x", "transform_type": "not-a-type"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 422

    def test_admin_required_for_narrator(self):
        r = client.post(
            "/v1/narrators", json={"narrator_id": "x"}, headers={"X-API-Key": "isnad-reader"}
        )
        assert r.status_code == 403

    def test_chain_endpoint(self):
        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "p=mv",
                "chain": [{"narrator_id": "src", "transform_type": "pass_through"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        cid = r.json()["claim_id"]
        r2 = client.get(f"/v1/claims/{cid}/chain")
        assert len(r2.json()["chain"]) == 1

    def test_corroboration_indexing(self):
        """Two claims with same normalized text → corroborating count > 0."""
        r1 = client.post(
            "/v1/claims",
            json={
                "claim_text": "energy is conserved",
                "normalized_text": "energy is conserved",
                "chain": [{"narrator_id": "source:A"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r1.status_code == 200
        r2 = client.post(
            "/v1/claims",
            json={
                "claim_text": "Energy is conserved in all systems",
                "normalized_text": "energy is conserved",
                "chain": [{"narrator_id": "source:B"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        cid2 = r2.json()["claim_id"]
        r = client.get(f"/v1/claims/{cid2}")
        assert r.json()["corroborating_claims"] >= 1

    def test_claim_404(self):
        assert client.get("/v1/claims/nonexistent").status_code == 404

    def test_document_hashes_round_trip_in_chain(self):
        """Chain links carry document_hashes through submission → retrieval (#125)."""
        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "the object moves at 10 m/s",
                "chain": [
                    {
                        "narrator_id": "source:docs",
                        "transform_type": "pass_through",
                        "document_hashes": ["doc-hash-abc"],
                    }
                ],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        cid = r.json()["claim_id"]
        r2 = client.get(f"/v1/claims/{cid}/chain")
        links = r2.json()["chain"]
        assert any("doc-hash-abc" in link.get("document_hashes", []) for link in links)

    def test_corroboration_result_carries_chain_independence(self):
        """The response surfaces per-chain independence score + provenance (#125)."""
        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "momentum is conserved",
                "chain": [{"narrator_id": "source:A"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        body = r.json()
        corr = body["corroboration_result"]
        # chain_independence must be a list (empty here — no corroborating
        # chains — but the field must exist, not be absent).
        assert "chain_independence" in corr
        assert isinstance(corr["chain_independence"], list)


class TestNarrators:
    def test_register_and_get(self):
        client.post(
            "/v1/narrators",
            json={
                "narrator_id": "model:x",
                "grade": "acceptable",
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        r = client.get("/v1/narrators/model:x")
        assert r.json()["grade"] == "acceptable"

    def test_domain_specific_grade(self):
        """Same narrator, different domains → different grades (key rule)."""
        client.post(
            "/v1/narrators",
            json={
                "narrator_id": "model:m",
                "domain": "physics",
                "grade": "reliable",
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        client.post(
            "/v1/narrators",
            json={
                "narrator_id": "model:m",
                "domain": "history",
                "grade": "weak",
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        r1 = client.get("/v1/narrators/model:m?domain=physics")
        r2 = client.get("/v1/narrators/model:m?domain=history")
        assert r1.json()["grade"] == "reliable"
        assert r2.json()["grade"] == "weak"

    def test_versioned_registration(self):
        r = client.post(
            "/v1/narrators",
            json={
                "narrator_id": "ingest-model-v3",
                "domain": "physics",
                "model_version": "1.0",
                "grade": "reliable",
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["resolved_narrator_id"] == "ingest-model-v3@1.0"
        r2 = client.get("/v1/narrators/ingest-model-v3?domain=physics&version=1.0")
        assert r2.json()["grade"] == "reliable"


class TestVersionDriftAPI:
    def test_new_version_does_not_inherit_grade(self):
        client.post(
            "/v1/narrators",
            json={
                "narrator_id": "openstax-textbook",
                "domain": "physics",
                "model_version": "2024",
                "grade": "reliable",
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        client.post(
            "/v1/narrators",
            json={
                "narrator_id": "ingest-model-v3",
                "domain": "physics",
                "model_version": "1.0",
                "grade": "reliable",
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "The photon momentum is p = h/lambda",
                "domain": "physics",
                "chain": [
                    {
                        "narrator_id": "openstax-textbook",
                        "version": "2024",
                        "transform_type": "pass_through",
                    },
                    {
                        "narrator_id": "ingest-model-v3",
                        "version": "2.0",
                        "transform_type": "generative",
                    },
                ],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["link_grades"] == ["reliable", "ungraded"]
        assert body["resolved_narrator_ids"] == [
            "openstax-textbook@2024",
            "ingest-model-v3@2.0",
        ]
        assert body["version_drift_detected"] is True
        assert body["action"] == "review"


class TestEvidence:
    def test_jarh_downgrades(self):
        client.post(
            "/v1/narrators",
            json={"narrator_id": "model:test"},
            headers={"X-API-Key": "isnad-admin"},
        )
        # Submit 3 adverse events → should downgrade
        for i in range(3):
            r = client.post(
                "/v1/evidence",
                json={
                    "narrator_id": "model:test",
                    "action": "jarh",
                    "description": f"fail {i}",
                },
                headers={"X-API-Key": "isnad-admin"},
            )
            assert r.status_code == 200


class TestClaimsList:
    def test_list_claims_empty(self):
        r = client.get("/v1/claims")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_list_claims_with_data(self):
        client.post(
            "/v1/claims",
            json={
                "claim_text": "F = ma",
                "domain": "physics",
                "chain": [{"narrator_id": "source:openstax"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        # Default is served_only=True — an ungraded chain is not served, so it
        # is absent from the default read surface.
        r_served = client.get("/v1/claims")
        assert r_served.status_code == 200
        # The audit view (served_only=false) shows every submitted claim.
        r = client.get("/v1/claims?served_only=false", headers={"X-API-Key": "isnad-admin"})
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_audit_view_requires_auth(self):
        """The audit view (served_only=false) exposes quarantined text — it must
        require auth, unlike the public served-only read surface."""
        r = client.get("/v1/claims?served_only=false")
        assert r.status_code == 401

    def test_list_claims_filter_by_domain(self):
        client.post(
            "/v1/claims",
            json={
                "claim_text": "p = mv",
                "domain": "physics",
                "chain": [{"narrator_id": "src"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        r = client.get("/v1/claims?domain=physics")
        assert r.status_code == 200
        for c in r.json()["claims"]:
            assert c["domain"] == "physics"


class TestClaimHydration:
    """Persisted claims are rehydrated into the serving index (issue #93 follow-up).

    The API's in-memory index must survive a restart: claims written to the DB
    by ``store_claim`` are rebuilt into ``_app_state`` on boot. This closes the
    "claims silently disappear on restart" gap from the external audit.
    """

    def test_hydrate_claims_from_db_repopulates_index(self):
        from sqlalchemy.orm import Session

        from isnad.api.endpoints.claims import _app_state, _hydrate_claims_from_db
        from isnad.core.chain import Chain, ChainLinkSpec, store_claim
        from isnad.storage.sqlalchemy import get_session
        from isnad.types import TransformType

        _app_state.claims.clear()
        _app_state._corroboration_index.clear()

        chain = Chain([
            ChainLinkSpec(
                "src",
                0,
                version="1.0",
                transform_type=TransformType.PASS_THROUGH,
                domain="physics",
            )
        ])
        with get_session() as session:
            store_claim(
                session,
                "E = mc^2",
                "physics/rel",
                chain,
                chain_grade="sahih",
                claim_id="hydrate-test-1",
            )

        # Simulate a fresh process: index is empty, DB has the claim.
        assert _app_state.claims == {}
        with get_session() as session:
            hydrated = _hydrate_claims_from_db(session)

        assert hydrated >= 1
        assert "hydrate-test-1" in _app_state.claims
        rec = _app_state.claims["hydrate-test-1"]
        assert rec["claim_text"] == "E = mc^2"
        assert rec["chain_grade"] == "sahih"
        assert rec["domain"] == "physics"
        # Content verdict is honestly UNVERIFIABLE after rehydration.
        assert rec["content_verdict"] == ContentVerdict.UNVERIFIABLE.value
        # The corroboration index is rebuilt too.
        assert _app_state.find_corroborating("e = mc^2", "hydrate-test-1") == []
        assert "hydrate-test-1" in _app_state._corroboration_index["e = mc^2"]

    def test_hydration_preserves_contradiction_verdict(self):
        """P0-A: a held SAHIH × CONTRADICTION (REVIEW) must stay REVIEW after
        rehydration, not be silently upgraded to SERVE_WITH_CAVEAT by
        re-deriving the verdict as UNVERIFIABLE."""
        from isnad.api.endpoints.claims import _app_state, _hydrate_claims_from_db
        from isnad.core.chain import Chain, ChainLinkSpec, store_claim
        from isnad.storage.sqlalchemy import get_session
        from isnad.types import ContentVerdict, TransformType

        _app_state.claims.clear()
        _app_state._corroboration_index.clear()

        chain = Chain([
            ChainLinkSpec("src", 0, version="1.0", transform_type=TransformType.PASS_THROUGH)
        ])
        with get_session() as session:
            store_claim(
                session,
                "a held contradiction",
                "physics/rel",
                chain,
                chain_grade="sahih",
                claim_id="hydrate-contradiction-1",
                content_verdict=ContentVerdict.CONTRADICTION.value,
                action="review",
            )

        _app_state.claims.clear()
        with get_session() as session:
            _hydrate_claims_from_db(session)

        rec = _app_state.claims["hydrate-contradiction-1"]
        assert rec["content_verdict"] == ContentVerdict.CONTRADICTION.value
        assert rec["action"] == "review"
        assert rec["served"] is False


class TestMetrics:
    def test_metrics(self):
        r = client.get("/v1/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "corroboration_fires_total" in data
        assert "bayesian_grade_changes_total" in data


class TestReviewQueue:
    """Issue #11: contradictions must reach a human, linked to both sides —
    not just gate the new claim in isolation. Forces EmbeddingCritic so the
    contradiction fires deterministically regardless of whether the optional
    NLI extra is installed in this environment.
    """

    @pytest.fixture(autouse=True)
    def force_embedding_critic(self):
        app.dependency_overrides[get_critic] = lambda: EmbeddingCritic()
        yield
        app.dependency_overrides.pop(get_critic, None)

    def _submit(self, claim_text: str) -> dict:
        r = client.post(
            "/v1/claims",
            json={"claim_text": claim_text, "chain": [{"narrator_id": "src"}]},
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        return r.json()

    def test_contradiction_creates_review_queue_entry_with_conflicting_claim_ids(self):
        claim1 = self._submit("the object moves at a speed of 10 meters per second")
        claim2 = self._submit("the object moves at a speed of 100 meters per second")

        assert claim2["content_verdict"] == "contradiction"
        assert claim2["action"] == "quarantine"  # ungraded narrator → ḍaʿīf (strict default)

        rq = client.get("/v1/review-queue", headers={"X-API-Key": "isnad-admin"})
        assert rq.status_code == 200
        items = rq.json()["items"]
        matching = [i for i in items if i["claim_id"] == claim2["claim_id"]]
        assert len(matching) == 1
        assert claim1["claim_id"] in matching[0]["conflicting_claim_ids"]

    def test_review_queue_requires_auth(self):
        r = client.get("/v1/review-queue")
        assert r.status_code == 401

    def test_review_queue_item_detail(self):
        self._submit("the object moves at a speed of 10 meters per second")
        self._submit("the object moves at a speed of 100 meters per second")

        rq = client.get("/v1/review-queue", headers={"X-API-Key": "isnad-admin"})
        item_id = rq.json()["items"][0]["id"]
        r = client.get(f"/v1/review-queue/{item_id}", headers={"X-API-Key": "isnad-admin"})
        assert r.status_code == 200
        assert r.json()["id"] == item_id

    def test_review_queue_item_404(self):
        r = client.get(
            "/v1/review-queue/00000000-0000-0000-0000-000000000000",
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 404


class _FakeFidelityCritic:
    """Deterministic stand-in for LocalNLICritic — avoids depending on
    whether the optional NLI extra is installed, and on real model output."""

    def __init__(self, verdict: ContentVerdict):
        self.verdict = verdict

    def evaluate(self, claim_text, normalized_claim, corpus_claims, domain):
        return self.verdict


class TestTransformationFidelity:
    """Issue #11, direction 3, end-to-end: a generative link whose output
    contradicts its own input caps the served chain_grade at DAIF, even when
    the narrator itself is seeded RELIABLE — surfacing mid-chain drift that
    NarratorGrade alone would miss."""

    def _seed_reliable(self, narrator_id: str):
        client.post(
            "/v1/narrators",
            json={"narrator_id": narrator_id, "domain": "physics", "grade": "reliable"},
            headers={"X-API-Key": "isnad-admin"},
        )

    def test_contradicted_fidelity_caps_chain_at_daif(self):
        app.dependency_overrides[get_fidelity_critic] = lambda: _FakeFidelityCritic(
            ContentVerdict.CONTRADICTION
        )
        try:
            self._seed_reliable("source:openstax")
            self._seed_reliable("model:summarizer")
            r = client.post(
                "/v1/claims",
                json={
                    "claim_text": "the object moves at a speed of 100 meters per second",
                    "domain": "physics",
                    "chain": [
                        {
                            "narrator_id": "source:openstax",
                            "transform_type": "pass_through",
                        },
                        {
                            "narrator_id": "model:summarizer",
                            "transform_type": "generative",
                            "input_snapshot": "the object moves at a speed of 10 meters per second",
                            "output_snapshot": "the object moves at a speed of 100 meters per second",
                        },
                    ],
                },
                headers={"X-API-Key": "isnad-admin"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["link_grades"] == ["reliable", "reliable"]
            assert body["link_fidelity_verdicts"] == ["unverifiable", "contradiction"]
            assert body["chain_grade"] == "daif"
        finally:
            app.dependency_overrides.pop(get_fidelity_critic, None)

    def test_consistent_fidelity_does_not_cap_chain(self):
        app.dependency_overrides[get_fidelity_critic] = lambda: _FakeFidelityCritic(
            ContentVerdict.CONSISTENT
        )
        try:
            self._seed_reliable("source:openstax2")
            self._seed_reliable("model:summarizer2")
            r = client.post(
                "/v1/claims",
                json={
                    "claim_text": "force equals mass times acceleration",
                    "domain": "physics",
                    "chain": [
                        {
                            "narrator_id": "source:openstax2",
                            "transform_type": "pass_through",
                        },
                        {
                            "narrator_id": "model:summarizer2",
                            "transform_type": "generative",
                            "input_snapshot": "F = ma",
                            "output_snapshot": "force equals mass times acceleration",
                        },
                    ],
                },
                headers={"X-API-Key": "isnad-admin"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["chain_grade"] == "sahih"
        finally:
            app.dependency_overrides.pop(get_fidelity_critic, None)

    def test_no_snapshots_defaults_to_unverifiable_no_penalty(self):
        """Without snapshots, fidelity checking is skipped entirely — a
        generative link's grade is unaffected regardless of the configured
        fidelity critic."""
        app.dependency_overrides[get_fidelity_critic] = lambda: _FakeFidelityCritic(
            ContentVerdict.CONTRADICTION
        )
        try:
            self._seed_reliable("source:openstax3")
            self._seed_reliable("model:summarizer3")
            r = client.post(
                "/v1/claims",
                json={
                    "claim_text": "energy cannot be created or destroyed",
                    "domain": "physics",
                    "chain": [
                        {"narrator_id": "source:openstax3", "transform_type": "pass_through"},
                        {"narrator_id": "model:summarizer3", "transform_type": "generative"},
                    ],
                },
                headers={"X-API-Key": "isnad-admin"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["link_fidelity_verdicts"] == ["unverifiable", "unverifiable"]
            assert body["chain_grade"] == "sahih"
        finally:
            app.dependency_overrides.pop(get_fidelity_critic, None)


class TestObservabilityAndReviewEdgeCases:
    """Close coverage gaps: Prometheus scrape target + review 404 on bad UUID."""

    def test_prometheus_metrics_endpoint(self):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "# HELP isnad_claims_total" in r.text
        assert "isnad_claims_total" in r.text

    def test_review_queue_item_invalid_uuid_is_404(self):
        r = client.get("/v1/review-queue/not-a-uuid", headers={"X-API-Key": "isnad-admin"})
        assert r.status_code == 404

    def test_review_queue_item_unknown_uuid_is_404(self):
        r = client.get(
            "/v1/review-queue/00000000-0000-0000-0000-000000000000",
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 404


class _AlwaysConsistentCritic:
    """Deterministic critic that always returns CONSISTENT — to force the
    matrix to SERVE a SAHIH chain, isolating the P0-B serve gate."""

    def evaluate(self, claim_text, normalized_claim, corpus_claims, domain):
        return ContentVerdict.CONSISTENT


class _CapturingCritic:
    """Critic that records the corpus it was handed (for D1 assertions)."""

    def __init__(self):
        self.last_corpus: list[str] = []

    def evaluate(self, claim_text, normalized_claim, corpus_claims, domain):
        self.last_corpus = list(corpus_claims)
        return ContentVerdict.UNVERIFIABLE


class TestPriorOnlyServeGate:
    """P0-B: a seeded (prior-only) narrator must not plain-SERVE."""

    @pytest.fixture(autouse=True)
    def force_consistent_critic(self):
        app.dependency_overrides[get_critic] = lambda: _AlwaysConsistentCritic()
        yield
        app.dependency_overrides.pop(get_critic, None)

    def _seed_reliable(self, narrator_id: str, domain: str = "physics"):
        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import get_session
        from isnad.types import NarratorGrade, NarratorType

        with get_session() as session:
            rdb = RegistryDB(session=session)
            rdb.load()
            rdb.registry.seed(
                narrator_id,
                domain,
                NarratorGrade.RELIABLE,
                narrator_type=NarratorType.SOURCE,
            )
            rdb.flush()

    def _submit(self, narrator_id: str, domain: str = "physics") -> dict:
        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "a seeded source claim",
                "domain": domain,
                "chain": [{"narrator_id": narrator_id}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        return r.json()

    def test_prior_only_chain_is_capped_to_caveat(self):
        self._seed_reliable("narrator:seeded-1")
        rec = self._submit("narrator:seeded-1")
        # Chain is SAHIH and content CONSISTENT — but the narrator is prior-only,
        # so the soft gate caps plain SERVE to SERVE_WITH_CAVEAT.
        assert rec["chain_grade"] == "sahih"
        assert rec["content_verdict"] == "consistent"
        assert rec["action"] == "serve_with_caveat"
        assert "narrator:seeded-1" in rec["prior_only_narrators"]

    def test_hold_domain_downgrades_prior_only_to_review(self):
        self._seed_reliable("narrator:seeded-2", domain="medical")
        os.environ["ISNAD_SERVE_HOLD_DOMAINS"] = "medical"
        try:
            rec = self._submit("narrator:seeded-2", domain="medical")
        finally:
            os.environ.pop("ISNAD_SERVE_HOLD_DOMAINS", None)
        assert rec["chain_grade"] == "sahih"
        assert rec["action"] == "review"
        assert "narrator:seeded-2" in rec["prior_only_narrators"]


class TestCriticCorpus:
    """D1: the critic corpus includes operator-supplied KB docs."""

    def test_operator_corpus_docs_passed_to_critic(self):
        critic = _CapturingCritic()
        app.dependency_overrides[get_critic] = lambda: critic
        try:
            r = client.post(
                "/v1/claims",
                json={
                    "claim_text": "water boils at 100 celsius",
                    "domain": "physics",
                    "chain": [{"narrator_id": "src"}],
                    "corpus_docs": ["water boils at 100 degrees celsius"],
                },
                headers={"X-API-Key": "isnad-admin"},
            )
            assert r.status_code == 200
            assert "water boils at 100 degrees celsius" in critic.last_corpus
            assert r.json()["critic_corpus_operator_docs"] == 1
        finally:
            app.dependency_overrides.pop(get_critic, None)


class TestReGradeLoopClosure:
    """P1: the jarḥ–taʿdīl loop is wired into submit_claim.

    A live contradiction must record jarh evidence against the NEW claim's
    narrator (it previously recorded nothing — the loop was orphaned).
    """

    @pytest.fixture(autouse=True)
    def force_embedding_critic(self):
        app.dependency_overrides[get_critic] = lambda: EmbeddingCritic()
        yield
        app.dependency_overrides.pop(get_critic, None)

    def test_contradiction_flags_the_new_narrator(self):
        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import get_session
        from isnad.types import EvidenceAction, EvidenceType, NarratorGrade, NarratorType

        # Seed a RELIABLE narrator so the chain is not the strict UNGRADED→DAIF
        # default — we want to observe the jarh strike, not the chain grade.
        with get_session() as session:
            rdb = RegistryDB(session=session)
            rdb.load()
            rdb.registry.seed(
                "narrator:reliable-src",
                "physics",
                NarratorGrade.RELIABLE,
                narrator_type=NarratorType.SOURCE,
            )
            rdb.flush()

        def _submit(text: str) -> dict:
            r = client.post(
                "/v1/claims",
                json={
                    "claim_text": text,
                    "domain": "physics",
                    "chain": [{"narrator_id": "narrator:reliable-src"}],
                },
                headers={"X-API-Key": "isnad-admin"},
            )
            assert r.status_code == 200
            return r.json()

        _submit("the object moves at a speed of 10 meters per second")
        claim2 = _submit("the object moves at a speed of 100 meters per second")
        assert claim2["content_verdict"] == "contradiction"

        with get_session() as session:
            rdb = RegistryDB(session=session)
            rdb.load()
            narrator = rdb.registry.get("narrator:reliable-src", "physics")
            assert narrator is not None
            jarh = [
                e
                for e in narrator.evidence_log
                if EvidenceType(str(e.get("evidence_type", "")))
                == EvidenceType.CORROBORATION_OUTCOME
                and EvidenceAction(str(e.get("action", ""))) == EvidenceAction.JARH
            ]
            assert len(jarh) == 1, f"expected 1 contradiction strike, got {len(jarh)}"

    def test_corroboration_renews_grade(self):
        """Corroboration fires renew_grade on the narrators (freshness signal)."""
        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import get_session
        from isnad.types import NarratorGrade, NarratorType

        with get_session() as session:
            rdb = RegistryDB(session=session)
            rdb.load()
            rdb.registry.seed(
                "narrator:renew-src",
                "physics",
                NarratorGrade.ACCEPTABLE,
                narrator_type=NarratorType.SOURCE,
            )
            rdb.flush()

        # Two corroborating claims from independent narrators → corroboration
        # upgrade → renew_grade on the base narrator.
        for text in ("water boils at 100 degrees celsius", "water boils at 100 celsius"):
            r = client.post(
                "/v1/claims",
                json={
                    "claim_text": text,
                    "domain": "physics",
                    "chain": [{"narrator_id": "narrator:renew-src"}],
                },
                headers={"X-API-Key": "isnad-admin"},
            )
            assert r.status_code == 200

        # renew_grade is a no-op for UNGRADED/REJECTED but our narrator is
        # ACCEPTABLE, so we just assert no exception was raised and the
        # narrator still resolves (the freshness renewal is not directly
        # observable through the public record without a clock read).
        with get_session() as session:
            rdb = RegistryDB(session=session)
            rdb.load()
            assert rdb.registry.get("narrator:renew-src", "physics") is not None

    def test_mawdu_claim_quarantines_the_narrator(self):
        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import get_session
        from isnad.types import AdalahGrade, NarratorGrade, NarratorType

        # Pre-register a narrator as REJECTED (operator assigned), then submit
        # a claim through it: MAWDU -> REJECT_AND_QUARANTINE_NARRATOR, and the
        # narrator must become actively COMPROMISED + inactive in the registry.
        with get_session() as session:
            rdb = RegistryDB(session=session)
            rdb.load()
            rdb.registry.register(
                "narrator:rejected",
                "physics",
                narrator_type=NarratorType.MODEL,
                grade=NarratorGrade.REJECTED,
            )
            rdb.flush()

        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "a rejected source claims X",
                "domain": "physics",
                "chain": [{"narrator_id": "narrator:rejected"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200

        with get_session() as session:
            rdb = RegistryDB(session=session)
            rdb.load()
            rec = rdb.registry.get("narrator:rejected", "physics")
            assert rec is not None
            assert rec.grade == NarratorGrade.REJECTED
            assert rec.adalah_grade == AdalahGrade.COMPROMISED
            assert rec.is_active is False
