"""Tests for authority-chain walking (issue #37).

The gap: the integration used to treat a self-declared ``authorizedBy`` as an
endorsement (green). These tests pin that the chain is now *walked*: an
``authorizedBy`` that does not resolve to a real authority is self-verified
(amber), never endorsed.
"""

from __future__ import annotations

import urllib.request

from isnad.integrations.liveverify import verify_claim, walk_authority_chain


def _stub_fetcher(metas: dict):
    def fetch(base_url, timeout=10.0):
        return metas.get(base_url)

    return fetch


class TestWalkAuthorityChain:
    def test_no_authorized_by_is_not_confirmed(self):
        chain = walk_authority_chain(None, fetch_meta=_stub_fetcher({}))
        assert chain.confirmed is False
        assert chain.reached_root is False

    def test_walks_to_root(self):
        metas = {"policing.gov.uk/v1": {"role": "root-authority", "issuer": "HM Gov"}}
        chain = walk_authority_chain("policing.gov.uk/v1", fetch_meta=_stub_fetcher(metas))
        assert chain.confirmed is True
        assert chain.reached_root is True
        assert [e.domain for e in chain.entries] == ["policing.gov.uk"]

    def test_walks_endorser_to_root(self):
        metas = {
            "policing.gov.uk/v1": {
                "role": "endorser",
                "issuer": "HMICFRS",
                "authorizedBy": "gov.uk/v1",
            },
            "gov.uk/v1": {"role": "root-authority", "issuer": "HM Government"},
        }
        chain = walk_authority_chain("policing.gov.uk/v1", fetch_meta=_stub_fetcher(metas))
        assert chain.reached_root is True
        assert [e.domain for e in chain.entries] == ["policing.gov.uk", "gov.uk"]

    def test_unreachable_authorized_by_is_not_confirmed(self):
        # The bug #37 closed: a self-declared authorizedBy that 404s.
        chain = walk_authority_chain("fake.gov/v1", fetch_meta=_stub_fetcher({}))
        assert chain.confirmed is False

    def test_non_authority_target_is_not_confirmed(self):
        # authorizedBy points at an *issuer* (no role), not an authority.
        metas = {"issuer.gov/v1": {"issuer": "Some Issuer", "claimType": "X"}}
        chain = walk_authority_chain("issuer.gov/v1", fetch_meta=_stub_fetcher(metas))
        assert chain.confirmed is False

    def test_cycle_is_detected(self):
        metas = {
            "a.gov": {"role": "endorser", "authorizedBy": "b.gov"},
            "b.gov": {"role": "endorser", "authorizedBy": "a.gov"},
        }
        chain = walk_authority_chain("a.gov", fetch_meta=_stub_fetcher(metas))
        assert chain.reached_root is False
        assert chain.error == "cycle"
        # A pure endorser cycle is self-referential, not independently
        # confirmed — it must NOT render GREEN (issue #183).
        assert chain.confirmed is False


class _FakeResp:
    def read(self):
        return b'{"status": "verified"}'

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestVerifyClaimAuthority:
    def _verify(self, monkeypatch, metadata, metas):
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _FakeResp())
        return verify_claim(
            "Some claim\nverify:issuer.gov/verified",
            metadata=metadata,
            fetch_meta=_stub_fetcher(metas),
        )

    def test_endorsed_when_chain_confirms(self, monkeypatch):
        result = self._verify(
            monkeypatch,
            {"authorizedBy": "policing.gov.uk/v1"},
            {"policing.gov.uk/v1": {"role": "root-authority", "issuer": "HM Gov"}},
        )
        assert result.verified is True
        assert result.self_verified is False  # chain confirmed → green
        assert result.authority_chain is not None
        assert result.authority_chain.confirmed is True

    def test_self_verified_when_chain_unresolvable(self, monkeypatch):
        result = self._verify(monkeypatch, {"authorizedBy": "fake.gov/v1"}, {})
        assert result.verified is True
        assert result.self_verified is True  # chain failed → amber (the fix)
        assert result.authority_chain.confirmed is False

    def test_self_verified_when_no_authorized_by(self, monkeypatch):
        result = self._verify(monkeypatch, {}, {})
        assert result.self_verified is True
