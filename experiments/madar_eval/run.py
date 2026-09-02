"""Calibrate content-level madār detection (#54): measure it, don't assert it.

``content_madar`` ships a shared-error fingerprint (``ErrorFingerprint`` /
``shares_error_with``) and a corpus-gated wrapper (``detect_content_madar``),
covered by unit tests but never *measured*. This harness measures the two things
that matter:

- **False-positive rate on independent agreement** — the dangerous error. When
  two genuinely independent chains state the same *correct* fact and the detector
  fires, it discounts the very corroboration it exists to reward. This is the
  headline number.
- **Recall on shared errors** — of the pairs that truly echo the same specific
  mistake, how many the detector catches.

Two layers are reported separately:

1. ``shares_error_with`` — the raw fingerprint, gate-independent. This is the
   worst case: no corpus verdict protects it, so its FP rate is the fingerprint's
   intrinsic hazard.
2. ``detect_content_madar`` — the shipped wrapper, which only compares
   fingerprints when the base verdict is CONTRADICTION. This layer is fed an
   *oracle* verdict (from the ground-truth label), so it demonstrates only the
   **structural** fact that a CONSISTENT claim is never fingerprinted — its 0 FP
   is by construction of the oracle, NOT an empirical measurement that the gate
   removes false positives. The gate's real FP contribution is
   ``critic_false_contradiction_rate × raw_fire_rate``, and the first factor is
   measured in ``experiments/critic_eval``, not here.

The output is a re-runnable calibration record pinned to an ``eval_set_sha256``,
in the same idiom as the affirmation-gate eval records and ``co_failure`` — a
measurement is evidence only if someone else can reproduce it.

``content_madar`` is pure and dependency-free, so these numbers reproduce on base
deps alone — no ``nli`` extra, no model download, no API key. (Stated explicitly
because this repo's critic behavior silently depends on the ``nli`` extra; this
harness does not.)

Usage:
    python experiments/madar_eval/run.py

Writes ``RESULTS.md`` and ``results.json`` into this directory.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from isnad.core.content_madar import ErrorFingerprint, detect_content_madar
from isnad.types import ContentVerdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_set import all_cases  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRADICTION = ContentVerdict.CONTRADICTION
CONSISTENT = ContentVerdict.CONSISTENT


def _eval_set_sha256(cases: list[tuple[str, str, str]]) -> str:
    """Deterministic hash of the labeled set — the re-runnability pin."""
    payload = json.dumps(cases, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _raw_fires(a: str, b: str) -> bool:
    """Raw fingerprint layer: does shares_error_with fire, gate aside?"""
    return ErrorFingerprint.from_claim(a).shares_error_with(ErrorFingerprint.from_claim(b))


def _gated_fires(label: str, a: str, b: str) -> bool:
    """Shipped wrapper layer under an *oracle* critic verdict.

    IMPORTANT — this row is STRUCTURAL, not an empirical false-positive rate.

    ``detect_content_madar`` only fingerprints a claim whose base verdict is
    CONTRADICTION. Here we feed the verdict *from the ground-truth label* —
    CONTRADICTION for shared_error, CONSISTENT otherwise. So on every
    independent-agreement pair the gate returns False before the fingerprint is
    ever computed, and its FP rate is 0 *by construction of this oracle*,
    independent of the detector's behaviour. Break ``shares_error_with`` to fire
    on everything and this row still reads 0 FP.

    What this row therefore shows is only the structural fact that gating on
    CONTRADICTION means a CONSISTENT claim is never fingerprinted. It is NOT a
    measurement that "the gate removes false positives" — the real gate FP
    contribution is ``critic_false_contradiction_rate × raw_fire_rate``, and the
    first factor is measured in ``experiments/critic_eval`` (``false_contradiction_rate``),
    not here. This harness sets it to 0 by fiat via the oracle label.
    """
    verdict = CONTRADICTION if label == "shared_error" else CONSISTENT
    return detect_content_madar(a, verdict, [(b, verdict)])


def _metrics(rows: list[tuple[str, bool]]) -> dict[str, object]:
    """rows = (label, fired). Positive class = shared_error; the rest must not fire."""
    shared = [r for r in rows if r[0] == "shared_error"]
    indep_agree = [r for r in rows if r[0] == "independent_agreement"]
    indep_diff = [r for r in rows if r[0] == "independent_different"]
    negatives = indep_agree + indep_diff

    tp = sum(1 for _, fired in shared if fired)
    fn = len(shared) - tp
    fp = sum(1 for _, fired in negatives if fired)
    tn = len(negatives) - fp

    # The dangerous FP: firing on genuine independent AGREEMENT (discounting real
    # corroboration). Reported on its own because independent_different collisions
    # are far less likely and far less costly.
    fp_agree = sum(1 for _, fired in indep_agree if fired)

    recall = tp / len(shared) if shared else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "n": len(rows),
        "n_shared_error": len(shared),
        "n_independent_agreement": len(indep_agree),
        "n_independent_different": len(indep_diff),
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "f1": round(f1, 3),
        "false_positive_rate": round(fp / len(negatives), 3) if negatives else 0.0,
        "false_positive_rate_agreement": round(fp_agree / len(indep_agree), 3)
        if indep_agree
        else 0.0,
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "fp_agreement": fp_agree,
    }


def build_report(
    raw: dict[str, object],
    gated: dict[str, object],
    raw_rows: list[tuple[str, bool]],
    sha: str,
) -> str:
    misfires = [
        label
        for (label, fired) in raw_rows
        if fired and label in ("independent_agreement", "independent_different")
    ]
    lines = [
        "# Content-madār calibration — committed results (#54)",
        "",
        f"**Eval set:** {raw['n']} pairs "
        f"({raw['n_shared_error']} shared-error, "
        f"{raw['n_independent_agreement']} independent-agreement, "
        f"{raw['n_independent_different']} independent-different) · "
        f"`eval_set_sha256={sha[:16]}…`",
        "",
        "| Layer | Recall | Precision | F1 | FP rate (all neg.) | FP rate (agreement — danger) |",
        "|---|---|---|---|---|---|",
        f"| `shares_error_with` (raw fingerprint, **measured**) | {raw['recall']:.3f} | "
        f"{raw['precision']:.3f} | {raw['f1']:.3f} | {raw['false_positive_rate']:.3f} | "
        f"**{raw['false_positive_rate_agreement']:.3f}** |",
        f"| `detect_content_madar` (gated, **oracle — structural**) | {gated['recall']:.3f} | "
        f"{gated['precision']:.3f} | {gated['f1']:.3f} | {gated['false_positive_rate']:.3f} | "
        f"{gated['false_positive_rate_agreement']:.3f} |",
        "",
        "## Reading the numbers",
        "",
        "- The **raw `shares_error_with` row is the measurement.** Its **FP rate",
        "  (agreement)** is the headline: how often the bare fingerprint fires on two",
        "  *independent, correct* witnesses of the same fact — i.e. how often it would",
        "  discount the exact corroboration corroboration exists to reward. That is the",
        "  fingerprint's *intrinsic* hazard, and it is why the fingerprint is never used",
        "  bare — only behind the corpus gate.",
        "- **Recall** — of the pairs that truly echo the same specific mistake, how many",
        "  the fingerprint catches.",
        "- The **gated row is structural, not an empirical FP rate.** `detect_content_madar`",
        "  only fingerprints a claim already flagged CONTRADICTION; this harness feeds the",
        "  verdict *from the ground-truth label*, so on every independent-agreement pair the",
        "  gate short-circuits before the fingerprint runs and FP is 0 **by construction of",
        "  that oracle** — not because the detector was validated. Break `shares_error_with`",
        "  to fire on everything and this row still reads 0.",
        "- The gate's *real* false-positive contribution in production is",
        "  `critic_false_contradiction_rate × raw_fire_rate` — the chance the critic wrongly",
        "  calls an agreement a contradiction, times the ~0.75 chance the fingerprint then",
        "  collides. The first factor is measured in `experiments/critic_eval`",
        "  (`false_contradiction_rate`), not here. This harness does not measure it; it",
        "  assumes a perfect critic. The honest claim is narrow: **the bare fingerprint is",
        "  hazardous (measured), and gating on a prior CONTRADICTION verdict is what keeps",
        "  it away from correct agreement (structural).**",
        "",
        "## What this measures — and what it does not",
        "",
        "This calibrates the **detectable** half of content-level madār: claims whose",
        "wrongness the corpus can verify. It says nothing about the *undetectable* half —",
        "two independent sources repeating the same received error on a claim the corpus",
        "cannot check. That case is undecidable by construction (there is no wrongness",
        "oracle to turn *same content* into *same error*), and #54 discloses it as a",
        "permanent limit, not a gap to close. See `src/isnad/core/content_madar.py`.",
    ]
    if misfires:
        lines += [
            "",
            "## Raw-fingerprint misfires (why the gate matters)",
            "",
            f"On the raw layer, {len(misfires)} negative pair(s) fired — "
            f"{misfires.count('independent_agreement')} on independent *agreement*. Each is a",
            "correct, independent restatement that shares a salient token (a number, name,",
            "or date). These are exactly the collisions the corpus gate is there to stop:",
            "the fingerprint alone cannot tell *same correct fact* from *same mistake*.",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    cases = all_cases()
    sha = _eval_set_sha256(cases)

    raw_rows = [(label, _raw_fires(a, b)) for label, a, b in cases]
    gated_rows = [(label, _gated_fires(label, a, b)) for label, a, b in cases]

    raw_m = _metrics(raw_rows)
    gated_m = _metrics(gated_rows)

    print(
        f"raw    recall={raw_m['recall']:.3f} "
        f"FP(agreement)={raw_m['false_positive_rate_agreement']:.3f}"
    )
    print(
        f"gated  recall={gated_m['recall']:.3f} "
        f"FP(agreement)={gated_m['false_positive_rate_agreement']:.3f}"
    )

    # Re-runnable calibration record — evidence, pinned to the eval-set hash.
    record = {
        "schema_version": 1,
        "component": "content_madar",
        "eval_set_sha256": sha,
        "layers": {
            "shares_error_with": raw_m,
            "detect_content_madar": gated_m,
        },
        "per_case": {
            "raw": [{"label": lbl, "fired": fired} for lbl, fired in raw_rows],
            "gated": [{"label": lbl, "fired": fired} for lbl, fired in gated_rows],
        },
        "cases": cases,
    }
    (_HERE / "results.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    (_HERE / "RESULTS.md").write_text(build_report(raw_m, gated_m, raw_rows, sha))
    print(f"\nWrote {_HERE / 'RESULTS.md'} and results.json")


if __name__ == "__main__":
    main()
