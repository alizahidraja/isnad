"""Tests for the config-driven batch grading (isnad.bench.run_config, #74)."""

from __future__ import annotations

from isnad.bench import run_config


def _config() -> dict:
    return {
        "domain": "physics",
        "narrators": {
            "source:openstax": "reliable",
            "model:gpt-4o": "acceptable",
        },
        "claims": [
            {
                "text": "force equals mass times acceleration",
                "chain": ["source:openstax", "model:gpt-4o"],
            },
            {"text": "energy is conserved", "chain": ["source:openstax"]},
        ],
    }


class TestRunConfig:
    def test_grades_corpus_and_distribution(self):
        result = run_config(_config())
        assert result["claims_graded"] == 2
        # acceptable → ḥasan; all-reliable → ṣaḥīḥ
        assert result["grade_distribution"] == {"hasan": 1, "sahih": 1}
        assert result["claims"][0]["chain_grade"] == "hasan"
        assert result["claims"][1]["chain_grade"] == "sahih"

    def test_unknown_narrator_is_daif(self):
        config = _config()
        config["claims"] = [{"text": "x", "chain": ["source:unknown-model"]}]
        result = run_config(config)
        # unknown narrator → UNGRADED → strict default → ḍaʿīf
        assert result["claims"][0]["chain_grade"] == "daif"
        assert result["grade_distribution"] == {"daif": 1}

    def test_empty_corpus(self):
        config = _config()
        config["claims"] = []
        result = run_config(config)
        assert result["claims_graded"] == 0
        assert result["grade_distribution"] == {}

    def test_rejected_narrator_is_mawdu(self):
        config = _config()
        config["narrators"] = {"source:bad": "rejected"}
        config["claims"] = [{"text": "x", "chain": ["source:bad"]}]
        result = run_config(config)
        assert result["claims"][0]["chain_grade"] == "mawdu"
