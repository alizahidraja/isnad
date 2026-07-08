"""Tests for ISNAD API service."""

import pytest
from fastapi.testclient import TestClient

from isnad.api.main import app, AppState
from isnad.registry import Registry

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    app.state.isnad = AppState(registry=Registry())


class TestHealth:
    def test_health(self):
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_metrics(self):
        r = client.get("/v1/metrics")
        assert r.status_code == 200
        assert "claims_total" in r.json()


class TestClaims:
    def test_submit_claim(self):
        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "F = ma",
                "domain": "physics",
                "chain": [
                    {"narrator_id": "source:book", "transform_type": "pass_through"},
                    {"narrator_id": "model:gpt4", "transform_type": "generative"},
                ],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["claim_text"] == "F = ma"
        assert "chain_grade" in data
        assert "action" in data

    def test_submit_claim_no_key(self):
        r = client.post("/v1/claims", json={"claim_text": "test", "chain": []})
        assert r.status_code == 401

    def test_submit_claim_wrong_key(self):
        r = client.post(
            "/v1/claims",
            json={"claim_text": "test", "chain": []},
            headers={"X-API-Key": "wrong"},
        )
        assert r.status_code == 401

    def test_get_claim(self):
        r = client.post(
            "/v1/claims",
            json={"claim_text": "E = mc^2", "chain": []},
            headers={"X-API-Key": "isnad-admin"},
        )
        cid = r.json()["claim_id"]
        r2 = client.get(f"/v1/claims/{cid}")
        assert r2.status_code == 200
        assert r2.json()["claim_text"] == "E = mc^2"

    def test_get_claim_chain(self):
        r = client.post(
            "/v1/claims",
            json={
                "claim_text": "p = mv",
                "chain": [{"narrator_id": "src", "transform_type": "pass_through"}],
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        cid = r.json()["claim_id"]
        r2 = client.get(f"/v1/claims/{cid}/chain")
        assert r2.status_code == 200
        assert len(r2.json()["chain"]) == 1

    def test_claim_not_found(self):
        r = client.get("/v1/claims/nonexistent")
        assert r.status_code == 404


class TestNarrators:
    def test_register_narrator(self):
        r = client.post(
            "/v1/narrators",
            json={"narrator_id": "model:test", "domain": "physics", "grade": "reliable"},
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        assert r.json()["grade"] == "reliable"

    def test_get_narrator(self):
        client.post(
            "/v1/narrators",
            json={"narrator_id": "model:gpt4", "grade": "acceptable"},
            headers={"X-API-Key": "isnad-admin"},
        )
        r = client.get("/v1/narrators/model:gpt4")
        assert r.status_code == 200
        assert r.json()["grade"] == "acceptable"

    def test_register_requires_admin(self):
        r = client.post(
            "/v1/narrators",
            json={"narrator_id": "test"},
            headers={"X-API-Key": "isnad-reader"},
        )
        assert r.status_code == 403


class TestEvidence:
    def test_submit_evidence(self):
        client.post(
            "/v1/narrators",
            json={"narrator_id": "model:test"},
            headers={"X-API-Key": "isnad-admin"},
        )
        r = client.post(
            "/v1/evidence",
            json={
                "narrator_id": "model:test",
                "evidence_type": "post_hoc_audit",
                "action": "jarh",
                "description": "Claim was incorrect",
            },
            headers={"X-API-Key": "isnad-admin"},
        )
        assert r.status_code == 200
        assert "new_grade" in r.json()
