"""Tests for the LIVE model-drift phase (#71): the LLM-free numeric oracle, key gating,
cost tracking/cap, and the serve/catch decision path — all without a real API key."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isnad.types import Action, ContentVerdict

from experiments.model_drift.corpus_hard import (
    HARD_CORPUS,
    HardFact,
    corpus_sha256,
    live_label,
)
from experiments.model_drift import live as live_mod
from experiments.model_drift.live import LiveClient, run_depth_live, run_live


def _fact(fid: str) -> HardFact:
    return next(f for f in HARD_CORPUS if f.fact_id == fid)


class FakeClient:
    """Duck-typed stand-in for LiveClient: pops canned responses, records calls."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.retries = 0
        self.model = "deepseek-flash"
        self.base_url = "https://api.deepseek.com/v1"
        self.temperature = 0.0
        self.cap_usd = 2.0
        self.price_in = 0.14
        self.price_out = 0.28

    @property
    def cost_usd(self) -> float:
        return 0.0

    def complete(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        self.calls += 1
        return self._responses.pop(0)


# --- oracle (LLM-free) ---


def test_live_label_faithful_hallucinated_unverifiable():
    f = _fact("e01")  # 206 bones
    assert live_label("An adult human body has 206 bones.", f) == "faithful"
    assert live_label("An adult human body has 207 bones.", f) == "hallucinated"
    assert live_label("The human body has a skeleton.", f) == "unverifiable"


def test_live_label_detects_any_numeric_deviation():
    """The oracle catches deviations NOT in the pre-listed wrong_values (LLM-free)."""
    f = _fact("e01")  # correct 206; wrong_values are 207/208/205
    assert live_label("An adult human body has 210 bones.", f) == "hallucinated"
    assert live_label("An adult human body has 200 bones.", f) == "hallucinated"


def test_live_label_numeric_equivalence():
    f = _fact("h06")  # 5,895 meters
    assert live_label("Kilimanjaro is 5895 meters tall.", f) == "faithful"  # comma stripped
    assert live_label("Kilimanjaro is 5,895 m tall.", f) == "faithful"


def test_live_label_more_precise_answer_is_faithful():
    """A more-precise answer that rounds to the canonical value is NOT hallucinated."""
    f = _fact("h27")  # land speed record: 763 mph
    assert live_label("The land speed record is 763.035 mph.", f) == "faithful"
    assert live_label("The land speed record is 763 mph.", f) == "faithful"
    assert live_label("The land speed record is 700 mph.", f) == "hallucinated"


def test_live_label_handles_spelled_out_numbers():
    """'five' should match the canonical '5' even with extra years in the claim."""
    f = _fact("h11")  # Brazil: 5 World Cups
    claim = "Brazil holds five FIFA World Cup titles, won in 1958, 1962, 1970, 1994, and 2002."
    assert live_label(claim, f) == "faithful"


def test_corpus_sha_deterministic():
    assert corpus_sha256() == corpus_sha256()
    assert len(corpus_sha256()) == 64


# --- key gating (no fabricate) ---


def test_main_refuses_without_key(monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert live_mod.main([]) == 1
    assert "not set" in capsys.readouterr().err


# --- decision path: serve vs catch ---


def test_run_depth_live_catches_contradiction():
    """SAHIH chain + critic says CONTRADICTION -> REVIEW (hallucination not served)."""
    f = _fact("e01")
    # depth 1: one narrator reply (drifted) + one critic reply (CONTRADICTION)
    client = FakeClient(["An adult human body has 207 bones.", "CONTRADICTION"])
    row = run_depth_live(client, 1, f)
    assert row["ground_truth"] == "hallucinated"
    assert row["critic_verdict"] == "contradiction"
    assert row["action"] == Action.REVIEW.value
    assert row["served"] is False


def test_run_depth_live_serves_when_critic_misses():
    """SAHIH chain + critic says UNVERIFIABLE -> SERVE_WITH_CAVEAT (hallucination served)."""
    f = _fact("e01")
    client = FakeClient(["An adult human body has 207 bones.", "UNVERIFIABLE"])
    row = run_depth_live(client, 1, f)
    assert row["ground_truth"] == "hallucinated"
    assert row["action"] == Action.SERVE_WITH_CAVEAT.value
    assert row["served"] is True


def test_run_depth_live_relays_through_all_hops():
    f = _fact("e01")
    # depth 3 -> 3 narrator replies, then 1 critic reply
    client = FakeClient([
        "The body has 206 bones.",
        "A person has 206 bones.",
        "Humans have 207 bones.",
        "CONSISTENT",
    ])
    row = run_depth_live(client, 3, f)
    assert len(row["hops"]) == 3
    assert row["final_claim"] == "Humans have 207 bones."
    assert row["ground_truth"] == "hallucinated"


def test_run_live_aggregates_metrics():
    """Two facts, one depth, both hallucinated, one served -> served_error 0.5."""
    f1, f2 = _fact("e01"), _fact("e02")
    # fact order: e01 then e02; each depth-1 => narrator + critic
    client = FakeClient([
        "The body has 207 bones.",
        "UNVERIFIABLE",  # e01: hallucinated, served
        "A chessboard has 64 squares.",
        "CONSISTENT",  # e02: faithful, served
    ])
    record = run_live(client, depths=(1,), facts=(f1, f2))
    pd = record["per_depth"]["1"]
    assert pd["n"] == 2
    assert pd["n_hallucinated"] == 1
    assert pd["hallucination_rate"] == 0.5
    assert pd["served_error_rate"] == 1.0


# --- cost tracking + cap (real LiveClient, fake HTTP) ---


class _FakeResp:
    status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": "CONSISTENT"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
        }


class _FakeHTTP:
    def __init__(self, resp: _FakeResp | None = None) -> None:
        self._resp = resp or _FakeResp()

    def post(self, *args, **kwargs):
        return self._resp


def test_live_client_tracks_tokens_and_cost():
    client = LiveClient(api_key="x", _client=_FakeHTTP())
    assert client.complete([{"role": "user", "content": "hi"}], 32) == "CONSISTENT"
    assert client.prompt_tokens == 1000
    assert client.completion_tokens == 100
    expected = (1000 / 1_000_000) * 0.14 + (100 / 1_000_000) * 0.28
    assert client.cost_usd == pytest.approx(expected)


def test_live_client_enforces_cap():
    client = LiveClient(api_key="x", cap_usd=0.0, _client=_FakeHTTP())
    with pytest.raises(RuntimeError, match="cap"):
        client.complete([{"role": "user", "content": "hi"}], 32)


def test_live_client_does_not_commit_key():
    """Sanity: the module never writes the key anywhere; it is env-only."""
    src = Path(live_mod.__file__).read_text()
    assert "sk-" not in src
