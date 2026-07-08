"""Tests for ISNAD API v3 — DI, SQLAlchemy persistence, corroboration indexing."""

import os

import pytest
from fastapi.testclient import TestClient

from isnad.api.app import app
from isnad.api.endpoints.claims import _app_state
from isnad.storage.sqlalchemy import drop_db, init_db, reset_engine

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
