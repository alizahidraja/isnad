"""ISNAD-Bench — JSON-LD + page fragment for alizahidraja.com/isnad/bench (#134).

This file holds the structured data (Schema.org Dataset + SoftwareSourceCode +
ScholarlyArticle) and the plain-text leaderboard to paste into the site's
/isnad/bench page.  The JSON-LD is written to be dropped verbatim into a
<script type="application/ld+json"> block; the leaderboard is Markdown.

The values here are the benchmark's frozen numbers — they match
bench/docs/RESULTS.md exactly and must not be edited independently.
"""

from __future__ import annotations

import json

BENCH_RESULTS = {
    "kappa_strict": 0.871,
    "kappa_lenient": 0.761,
    "human_ceiling_critic_vs_critic": 0.331,
    "human_ceiling_critic_vs_consensus": 0.450,
    "shuffled_control": 0.047,
    "majority_control": 0.000,
    "chains": 577024,
    "narrators": 49844,
    "critics": 1015,
    "criticism_statements": 127863,
}

DATASET_JSON_LD = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    "name": "ISNAD-Bench (derived graded output)",
    "description": (
        "Per-chain derived output of ISNAD's weakest-link chain grading against "
        "classical hadith ground truth: the scholar's verdict, ISNAD's predicted "
        "chain grade, and the principled disagreement bucket, across 577,024 chains. "
        "Cohen's kappa = 0.871 vs the scholarly consensus (human ceiling 0.331). "
        "Derived from emadjumaah/hadith-kg (CC-BY-4.0)."
    ),
    "license": "https://creativecommons.org/licenses/by/4.0/",
    "isBasedOn": "https://huggingface.co/datasets/emadjumaah/hadith-kg",
    "url": "https://alizahidraja.com/isnad/bench",
    "sameAs": [
        "https://huggingface.co/datasets/alizahidraja/isnad-bench",
        "https://github.com/alizahidraja/isnad",
    ],
    "creator": {"@type": "Person", "name": "Ali Zahid Raja"},
    "citation": "Raja, A. Z. (2026). Grading the Narrators. arXiv:2607.24117.",
    "variableMeasured": ["sanad_id", "true_grade", "predicted_grade", "disagreement_bucket"],
    "measurementTechnique": "Cohen's kappa (chain-grade agreement)",
    "keywords": ["hadith", "isnad", "provenance", "trust", "chain-grading", "benchmark"],
}

SOFTWARE_JSON_LD = {
    "@context": "https://schema.org",
    "@type": "SoftwareSourceCode",
    "name": "ISNAD",
    "description": ("Isnād–Rijāl framework for claim-level provenance in multi-agent AI systems."),
    "license": "https://www.apache.org/licenses/LICENSE-2.0",
    "codeRepository": "https://github.com/alizahidraja/isnad",
    "programmingLanguage": "Python",
    "version": "2.9.8",
}

SCHOLARLY_ARTICLE_JSON_LD = {
    "@context": "https://schema.org",
    "@type": "ScholarlyArticle",
    "name": (
        "Grading the Narrators: An Isnād–Rijāl Framework for "
        "Claim-Level Provenance in Multi-Agent Knowledge Systems"
    ),
    "author": {"@type": "Person", "name": "Ali Zahid Raja"},
    "identifier": "10.48550/arXiv.2607.24117",
    "url": "https://arxiv.org/abs/2607.24117",
}

LEADERBOARD_MD = (
    "## ISNAD-Bench leaderboard\n\n"
    "| Method | κ (strict) | Human ceiling | Note |\n"
    "|---|---|---|---|\n"
    "| **ISNAD weakest-link (strict)** | **0.871** | 0.331 | "
    "faithfully implements the scholars' consensus |\n"
    "| ISNAD weakest-link (lenient) | 0.761 | 0.331 | "
    "opt-in `lenient_unknown=True` |\n"
    "| shuffled-rank control | 0.047 | — | negative control |\n"
    "| majority-class control | 0.000 | — | negative control |\n"
    "\n"
    "*The human ceiling (κ=0.331) is how well the scholars agree with each other — "
    "ISNAD does not exceed it; it is a deterministic reflection of their average "
    "opinion.*\n"
)


def main() -> None:
    print(json.dumps(DATASET_JSON_LD, indent=2, ensure_ascii=False))
    print("\n--- SOFTWARE ---")
    print(json.dumps(SOFTWARE_JSON_LD, indent=2, ensure_ascii=False))
    print("\n--- ARTICLE ---")
    print(json.dumps(SCHOLARLY_ARTICLE_JSON_LD, indent=2, ensure_ascii=False))
    print("\n--- LEADERBOARD ---")
    print(LEADERBOARD_MD)


if __name__ == "__main__":
    main()
