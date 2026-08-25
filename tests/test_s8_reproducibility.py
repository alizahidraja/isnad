"""§8 reproducibility regression (issue #92).

Pins the experiment's transition policy and verifies the two invariants that
broke when the repo default drifted to Bayesian:

1. `calibrate()` uses the post-#9 `ThresholdTransitionPolicy` and honors
   operator seed grades (`source:*` → RELIABLE, not WEAK).
2. A high-fault narrator is *discovered* from audit evidence and driven down,
   and a chain through it grades MAWDU → quarantine (the weakest-link rule).

The committed 20k-claim corpus is not loaded here; a small synthetic corpus
exercises the same `calibrate()` code path deterministically.
"""

from __future__ import annotations

import sys
from pathlib import Path

from isnad.core.grading import grade_chain
from isnad.core.registry import Registry, ThresholdTransitionPolicy
from isnad.types import Action, ChainGrade, NarratorGrade

_EXP = Path(__file__).resolve().parents[1] / "experiments" / "s8_gated_vs_ungated"
if str(_EXP) not in sys.path:
    sys.path.insert(0, str(_EXP))

from calibrate import calibrate  # noqa: E402


def _build_synthetic(
    domain: str = "physics", n_good: int = 30, n_bad: int = 30
) -> tuple[list, list]:
    """A tiny corpus: a reliable source/scraper, one clean ingest, one broken ingest.

    ``ingest@bad`` corrupts every claim it touches, so the audit drives it to
    REJECTED under the threshold policy regardless of shuffle order.
    """
    enriched: list[dict] = []
    ground_truth: list[dict] = []
    for i in range(n_good + n_bad):
        bad = i >= n_good
        cid = f"c-{i:04d}"
        ingest = "ingest@bad" if bad else "ingest@good"
        enriched.append({
            "claim_id": cid,
            "domain": domain,
            "assigned_scraper": "pdf-scraper@1.2",
            "assigned_ingest": ingest,
            "chain_json": [
                {"narrator_id": "source:openstax", "domain": domain},
                {"narrator_id": "pdf-scraper@1.2", "domain": domain},
                {"narrator_id": ingest, "domain": domain},
            ],
        })
        ground_truth.append({
            "claim_id": cid,
            "corrupted": bad,
            "responsible_narrator": ingest if bad else "none",
        })
    return enriched, ground_truth


def test_calibrate_pins_threshold_policy_and_honors_seeds() -> None:
    enriched, gt = _build_synthetic()
    reg, _cal, _eval = calibrate(enriched, gt, ["physics"], seed=42)

    # The experiment is pinned to the post-#9 threshold policy.
    assert isinstance(reg.transition_policy, ThresholdTransitionPolicy)

    # Seeds are honored (issue #90) — not clobbered to WEAK.
    assert reg.get_grade("source:openstax", "physics") == NarratorGrade.RELIABLE
    assert reg.get_grade("pdf-scraper@1.2", "physics") == NarratorGrade.RELIABLE
    assert reg.get_grade("ingest@good", "physics") == NarratorGrade.ACCEPTABLE


def test_calibrate_discovers_broken_narrator_and_quarantines_it() -> None:
    enriched, gt = _build_synthetic()
    reg, _cal, _eval = calibrate(enriched, gt, ["physics"], seed=42)

    # 100% fault → discovered as REJECTED from audit evidence alone.
    assert reg.get_grade("ingest@bad", "physics") == NarratorGrade.REJECTED

    # Weakest-link quarantine: a chain through the rejected narrator grades
    # MAWDU and routes to REJECT_AND_QUARANTINE_NARRATOR.
    from isnad.core.decision import decide
    from isnad.types import ContentVerdict, TransformType

    grades = [
        reg.get_grade("source:openstax", "physics"),
        reg.get_grade("pdf-scraper@1.2", "physics"),
        reg.get_grade("ingest@bad", "physics"),
    ]
    chain_grade = grade_chain(
        grades,
        [
            TransformType.PASS_THROUGH,
            TransformType.DESTRUCTIVE,
            TransformType.GENERATIVE,
        ],
        is_complete=True,
    )
    assert chain_grade == ChainGrade.MAWDU

    action = decide(chain_grade, ContentVerdict.CONSISTENT)
    assert action == Action.REJECT_AND_QUARANTINE_NARRATOR
