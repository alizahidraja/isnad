"""Tests for core/fidelity.py — per-link transformation-fidelity checking.

Verifies issue #11 (direction 3): does a generative link's output actually
follow from its own input, within this chain — distinct from matn criticism
(corpus comparison) and from NarratorGrade (general track record). Uses a
deterministic fake critic rather than a real NLI model, to keep the checking
logic (which links get checked, with what arguments) independent of any
particular model's judgment quality.
"""

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.fidelity import compute_fidelity_verdicts
from isnad.types import ContentVerdict, TransformType


class _FakeCritic:
    """Records calls and returns a fixed verdict — for testing the wiring,
    not the underlying NLI judgment quality."""

    def __init__(self, verdict: ContentVerdict = ContentVerdict.CONSISTENT):
        self.verdict = verdict
        self.calls: list[tuple] = []

    def evaluate(self, claim_text, normalized_claim, corpus_claims, domain):
        self.calls.append((claim_text, normalized_claim, corpus_claims, domain))
        return self.verdict


class TestComputeFidelityVerdicts:
    def test_generative_link_with_snapshots_is_checked(self) -> None:
        critic = _FakeCritic(verdict=ContentVerdict.CONTRADICTION)
        chain = Chain([
            ChainLinkSpec(
                "model:gpt",
                0,
                transform_type=TransformType.GENERATIVE,
                domain="physics",
                input_snapshot="the speed is 10 m/s",
                output_snapshot="the speed is 100 m/s",
            ),
        ])
        verdicts = compute_fidelity_verdicts(chain, critic)
        assert verdicts == [ContentVerdict.CONTRADICTION]
        assert critic.calls == [
            (
                "the speed is 100 m/s",
                "the speed is 100 m/s",
                ["the speed is 10 m/s"],
                "physics",
            )
        ]

    def test_non_generative_links_are_not_checked(self) -> None:
        critic = _FakeCritic(verdict=ContentVerdict.CONTRADICTION)
        chain = Chain([
            ChainLinkSpec(
                "scraper",
                0,
                transform_type=TransformType.DESTRUCTIVE,
                input_snapshot="raw source text",
                output_snapshot="extracted text",
            ),
            ChainLinkSpec(
                "passthrough-db",
                1,
                transform_type=TransformType.PASS_THROUGH,
                input_snapshot="extracted text",
                output_snapshot="extracted text",
            ),
        ])
        verdicts = compute_fidelity_verdicts(chain, critic)
        assert verdicts == [ContentVerdict.UNVERIFIABLE, ContentVerdict.UNVERIFIABLE]
        assert critic.calls == []  # never called for non-generative links

    def test_generative_link_missing_output_snapshot_is_not_checked(self) -> None:
        critic = _FakeCritic()
        chain = Chain([
            ChainLinkSpec(
                "model:gpt",
                0,
                transform_type=TransformType.GENERATIVE,
                input_snapshot="the speed is 10 m/s",
                # output_snapshot omitted
            ),
        ])
        verdicts = compute_fidelity_verdicts(chain, critic)
        assert verdicts == [ContentVerdict.UNVERIFIABLE]
        assert critic.calls == []

    def test_generative_link_missing_input_snapshot_is_not_checked(self) -> None:
        critic = _FakeCritic()
        chain = Chain([
            ChainLinkSpec(
                "model:gpt",
                0,
                transform_type=TransformType.GENERATIVE,
                output_snapshot="the speed is 100 m/s",
                # input_snapshot omitted
            ),
        ])
        verdicts = compute_fidelity_verdicts(chain, critic)
        assert verdicts == [ContentVerdict.UNVERIFIABLE]
        assert critic.calls == []

    def test_critic_none_skips_everything(self) -> None:
        chain = Chain([
            ChainLinkSpec(
                "model:gpt",
                0,
                transform_type=TransformType.GENERATIVE,
                input_snapshot="the speed is 10 m/s",
                output_snapshot="the speed is 100 m/s",
            ),
        ])
        verdicts = compute_fidelity_verdicts(chain, None)
        assert verdicts == [ContentVerdict.UNVERIFIABLE]

    def test_verdicts_align_with_chain_link_order(self) -> None:
        critic = _FakeCritic(verdict=ContentVerdict.CONSISTENT)
        chain = Chain([
            ChainLinkSpec(
                "source:a",
                0,
                transform_type=TransformType.PASS_THROUGH,
            ),
            ChainLinkSpec(
                "model:gpt",
                1,
                transform_type=TransformType.GENERATIVE,
                input_snapshot="F = ma",
                output_snapshot="force equals mass times acceleration",
            ),
            ChainLinkSpec(
                "model:claude",
                2,
                transform_type=TransformType.GENERATIVE,
                input_snapshot="force equals mass times acceleration",
                output_snapshot="the object accelerates proportionally to force",
            ),
        ])
        verdicts = compute_fidelity_verdicts(chain, critic)
        assert len(verdicts) == 3
        assert verdicts[0] == ContentVerdict.UNVERIFIABLE  # pass-through, not checked
        assert verdicts[1] == ContentVerdict.CONSISTENT
        assert verdicts[2] == ContentVerdict.CONSISTENT
        assert len(critic.calls) == 2
