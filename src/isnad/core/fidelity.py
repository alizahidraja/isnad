"""Transformation Fidelity — per-link check that a generative narrator's
output actually follows from its own input, within this one chain, right now.

Implements issue #11's third proposed direction: "make low confidence
diagnostic rather than terminal... degraded chains should surface where they
degraded." This is a third axis, distinct from both:

- NarratorGrade (core/registry.py): a narrator's *general historical* track
  record — does not tell you whether *this specific* output held together.
- Matn criticism (critics/*.py): compares a claim against the *external
  corpus* — cannot catch drift introduced by a generative link mid-chain, and
  cannot verify a claim that has nothing in the corpus yet to compare against.

Only GENERATIVE links can meaningfully drift from their input: DESTRUCTIVE and
PASS_THROUGH transformations can only lose or preserve information, never
invent it (paper §4.1). So this check only applies where a link's own
input_snapshot/output_snapshot were captured (see core/chain.py,
ChainLinkSpec) and the link is GENERATIVE.

Deliberately reuses the existing ContentCritic protocol rather than
introducing a new verdict type or a new NLI-calling module: calling
critic.evaluate(output, output, [input], domain) with the link's own input as
the sole "corpus" entry turns the critic's ordinary
consistent/contradiction/unverifiable judgment into exactly the
entailment/contradiction/not-checked signal this needs. CONSISTENT reads as
"entailed" here, and UNVERIFIABLE — no snapshots captured, or no NLI-capable
critic available — is never penalized, matching the framework's existing
"no data means no penalty" pattern (e.g. UNGRADED narrators).
"""

from __future__ import annotations

from isnad.core.chain import Chain
from isnad.critics.base import ContentCritic
from isnad.types import ContentVerdict, TransformType


def compute_fidelity_verdicts(
    chain: Chain,
    critic: ContentCritic | None,
) -> list[ContentVerdict]:
    """Compute a per-link transformation-fidelity verdict for a chain.

    Args:
        chain: The chain to check.
        critic: A ContentCritic to judge entailment/contradiction between a
            link's input and output snapshots. Pass an NLI-capable critic
            (LocalNLICritic/HybridCritic) for a meaningful directional
            judgment — a symmetric-similarity critic (e.g. EmbeddingCritic)
            cannot distinguish "output follows from input" from "output
            contradicts input" and will tend to just measure wording overlap.
            Pass None to skip fidelity checking entirely (all links return
            UNVERIFIABLE, i.e. no penalty).

    Returns:
        One ContentVerdict per link, aligned with chain.links. Non-generative
        links, links missing either snapshot, and every link when critic is
        None all yield ContentVerdict.UNVERIFIABLE (not checked — no penalty).
    """
    verdicts: list[ContentVerdict] = []
    for link in chain.links:
        if (
            critic is None
            or link.transform_type != TransformType.GENERATIVE
            or not link.input_snapshot
            or not link.output_snapshot
        ):
            verdicts.append(ContentVerdict.UNVERIFIABLE)
            continue

        verdicts.append(
            critic.evaluate(
                link.output_snapshot,
                link.output_snapshot,
                [link.input_snapshot],
                link.domain,
            )
        )
    return verdicts
