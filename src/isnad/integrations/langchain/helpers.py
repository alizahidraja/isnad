"""Registry helpers and ContentCritic adapter for ISNAD × LangChain.

- seed_registry(): Build and warm-start a Registry from a simple dict.
  Required for practical coverage — the cold-start produces near-zero
  coverage (see §8 experiment results).

- CriticAdapter: Interface for plugging in a real ContentCritic.
  The default deterministic stub cannot judge real text.  Use this
  to wrap an LLM call or an embedding-based classifier.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from isnad.registry import Registry
from isnad.types import (
    AdalahGrade,
    ContentVerdict,
    DabtGrade,
    NarratorGrade,
    NarratorType,
)

# ── Registry seeding ───────────────────────────────────────────


def seed_registry(
    narrator_grades: dict[str, str],
    domain: str = "general",
) -> Registry:
    """Build a Registry from a simple dict of narrator_id → grade.

    This is the REQUIRED warm-start step for practical coverage.
    Without seed grades, the jarḥ–taʿdīl loop starts from UNGRADED
    and nearly all claims are quarantined (cold-start problem).

    Args:
        narrator_grades: Dict mapping narrator_id to grade string.
            Valid grades: reliable, acceptable, weak, rejected.
        domain: Domain tag for all narrators (override per-narrator if needed).

    Returns:
        A Registry with narrators pre-registered at the given grades.

    Example:
        reg = seed_registry({
            "source:my-docs": "reliable",
            "model:gpt-4o": "acceptable",
            "model:gpt-3.5": "weak",
        })
    """
    reg = Registry()
    grade_map = {
        "reliable": NarratorGrade.RELIABLE,
        "acceptable": NarratorGrade.ACCEPTABLE,
        "weak": NarratorGrade.WEAK,
        "rejected": NarratorGrade.REJECTED,
    }

    for narrator_id, grade_str in narrator_grades.items():
        grade = grade_map.get(grade_str.lower())
        if grade is None:
            raise ValueError(
                f"Unknown grade '{grade_str}' for '{narrator_id}'. "
                f"Use: reliable, acceptable, weak, or rejected."
            )

        # Determine narrator type from prefix
        if narrator_id.startswith("source:"):
            ntype = NarratorType.SOURCE
        elif narrator_id.startswith("model:"):
            ntype = NarratorType.MODEL
        elif narrator_id.startswith("tool:") or narrator_id.startswith("retriever:"):
            ntype = NarratorType.SCRAPER
        else:
            ntype = NarratorType.MODEL

        # Set ʿadālah/ḍabṭ based on grade
        if grade == NarratorGrade.RELIABLE:
            adalah = AdalahGrade.HIGH
            dabt = DabtGrade.HIGH
        elif grade == NarratorGrade.ACCEPTABLE:
            adalah = AdalahGrade.ACCEPTABLE
            dabt = DabtGrade.ACCEPTABLE
        elif grade == NarratorGrade.WEAK:
            adalah = AdalahGrade.SUSPECT
            dabt = DabtGrade.LOW
        else:
            adalah = AdalahGrade.COMPROMISED
            dabt = DabtGrade.LOW

        reg.register(
            narrator_id,
            domain,
            narrator_type=ntype,
            grade=grade,
            adalah=adalah,
            dabt=dabt,
        )

    return reg


# ── ContentCritic adapter ──────────────────────────────────────


class CriticAdapter:
    """Adapter for plugging a real ContentCritic into ISNAD.

    The default deterministic critic is a NON-FUNCTIONAL stub on real
    text (returns UNVERIFIABLE for all real-world claims).  This adapter
    lets you wrap any callable that accepts (claim_text, corpus_claims, domain)
    and returns a ContentVerdict.

    There are TWO ways to use it:

    1. Pass a callable directly:
        def my_critic(claim, corpus, domain):
            # your logic here
            return ContentVerdict.CONSISTENT
        critic = CriticAdapter(my_critic)

    2. Use the LLM-backed example (requires an API key):
        critic = CriticAdapter.llm_backed(api_key="...")

    IMPORTANT: The LLM-backed example is a reference integration stub.
    A production critic would add caching, batching, confidence scores,
    and domain-specific prompting.
    """

    def __init__(self, evaluator: Callable[..., Any]):
        self._evaluator = evaluator

    def evaluate(
        self,
        claim_text: str,
        normalized_claim: str,
        corpus_claims: list[str],
        domain: str = "",
    ) -> ContentVerdict:
        """Evaluate a claim against a corpus."""
        result = self._evaluator(claim_text, corpus_claims, domain)
        if isinstance(result, ContentVerdict):
            return result
        if isinstance(result, str):
            try:
                return ContentVerdict(result)
            except ValueError:
                pass
        return ContentVerdict.UNVERIFIABLE

    @classmethod
    def llm_backed(
        cls,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> CriticAdapter:
        """Create a CriticAdapter backed by an Anthropic LLM.

        REFERENCE INTEGRATION STUB.  A production critic should add
        caching, batching, confidence calibration, and multi-model
        ensemble for reliability.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var).
            model: Anthropic model to use.
        """
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

        def _llm_evaluate(claim: str, corpus: list[str], domain: str) -> ContentVerdict:
            if not api_key:
                return ContentVerdict.UNVERIFIABLE

            try:
                import anthropic

                client = anthropic.Anthropic(api_key=api_key)
                corpus_text = "\n".join(f"- {c}" for c in corpus[:10])
                prompt = (
                    f"Does this claim contradict the existing corpus?\n\n"
                    f"Claim: {claim}\n\n"
                    f"Corpus:\n{corpus_text}\n\n"
                    f"Answer with one word: CONSISTENT, CONTRADICTION, or UNVERIFIABLE."
                )
                response = client.messages.create(
                    model=model,
                    max_tokens=16,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = getattr(response.content[0], "text", "").strip().upper()
                if "CONSISTENT" in text:
                    return ContentVerdict.CONSISTENT
                if "CONTRADICTION" in text:
                    return ContentVerdict.CONTRADICTION
                return ContentVerdict.UNVERIFIABLE
            except Exception:
                return ContentVerdict.UNVERIFIABLE

        return cls(_llm_evaluate)
