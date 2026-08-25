"""Batch grading — grade a user-supplied corpus through a narrator set.

This is the adoption vector (issue #74): a stranger runs ISNAD's grader on
*their own* claims and narrator grades and gets a scorecard back — a smaller
ask than adopting the library, and a stickier one.

It lives in the *installed* package (not the repo-only ``bench/``), so
``isnad bench --config mine.json`` works from ``pip install isnad`` with no
dataset. The classical ISNAD-Bench (hadith ground truth) lives in ``bench/``
and needs the repo + ``hadith-kg.db``.

Config (JSON — no YAML dependency):

    {
      "domain": "physics",
      "narrators": {"source:openstax": "reliable", "model:gpt-4o": "acceptable"},
      "claims": [
        {"text": "force equals mass times acceleration",
         "chain": ["source:openstax", "model:gpt-4o"]}
      ]
    }
"""

from __future__ import annotations

from collections import Counter

from isnad.core.chain import ChainLinkSpec
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.types import NarratorGrade


def run_config(config: dict[str, object]) -> dict[str, object]:
    """Grade a config-specified corpus through a config-specified narrator set.

    Returns a scorecard: per-claim chain grade + the grade distribution.
    Unknown narrator ids in a chain resolve to UNGRADED (strict default → ḍaʿīf).
    The config is untrusted JSON, so every field is read defensively.
    """
    domain = str(config.get("domain", "general"))
    reg = Registry()
    narrators = config.get("narrators", {})
    if isinstance(narrators, dict):
        for nid, grade in narrators.items():
            if isinstance(nid, str) and isinstance(grade, str):
                reg.register(nid, domain, grade=NarratorGrade(grade))

    graded: list[dict[str, object]] = []
    claims = config.get("claims", [])
    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            text = str(claim.get("text", ""))
            raw_chain = claim.get("chain", [])
            chain_ids = [str(nid) for nid in raw_chain] if isinstance(raw_chain, list) else []
            links = [ChainLinkSpec(nid, i, domain=domain) for i, nid in enumerate(chain_ids)]
            grades = [
                reg.get_grade_for_link(link.narrator_id, link.domain, link.version)
                for link in links
            ]
            chain_grade = grade_chain(
                grades,
                [link.transform_type for link in links],
                is_complete=True,
            )
            graded.append({"claim": text, "chain": chain_ids, "chain_grade": chain_grade.value})

    distribution = Counter(str(g["chain_grade"]) for g in graded)
    return {
        "domain": domain,
        "claims_graded": len(graded),
        "grade_distribution": dict(sorted(distribution.items())),
        "claims": graded,
    }
