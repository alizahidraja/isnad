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
        r = client.get("/v1/claims")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

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
