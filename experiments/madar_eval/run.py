"""Calibrate content-level madār detection (#54): measure it, don't assert it.

``content_madar`` ships a shared-error fingerprint (``ErrorFingerprint`` /
``shares_error_with``) and a corpus-gated wrapper (``detect_content_madar``),
covered by unit tests but never *measured*. This harness measures:

- **False-positive rate on independent agreement** — the dangerous error.
- **Recall on shared errors**, split into **token-bearing** (the fingerprint's
  strength) and **token-less** (reworded same mistake — where recall honestly
  fails).
- **Near-miss boundary FP** — one correct + one wrong claim sharing a subject
  token but differing in value; the current detector false-positives here
  (entity-set-equality fires before the numbers are compared), measured and
  disclosed, NOT fixed here.
- **N-way (3+ chain)** any-match semantics via ``detect_content_madar(base,
  verdict, corroborating)``.

Two layers are reported separately:

1. ``shares_error_with`` — the raw fingerprint, gate-independent.
2. ``detect_content_madar`` — the shipped wrapper, oracle-fed (structural).

The output is a re-runnable calibration record pinned to an ``eval_set_sha256``.
``content_madar`` is pure and dependency-free, so these numbers reproduce on
base deps alone.

Usage:
    python experiments/madar_eval/run.py

Writes ``RESULTS.md`` and ``results.json`` into this directory.
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import cast
from pathlib import Path

from isnad.core.content_madar import ErrorFingerprint, detect_content_madar
from isnad.types import ContentVerdict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from madar_eval_set import all_cases, n_chain_cases  # noqa: E402

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
    """Shipped wrapper layer under an *oracle* critic verdict (structural)."""
    verdict = CONTRADICTION if label in ("shared_error", "shared_error_tokenless") else CONSISTENT
    return detect_content_madar(a, verdict, [(b, verdict)])


def _nway_fires(label: str, base: str, corr: list[str]) -> bool:
    """N-way (3+ chain) evaluation under an oracle verdict (any-match semantics)."""
    if label == "n_chain_shared_error":
        base_v = CONTRADICTION
        corr_v = CONTRADICTION
    else:  # n_chain_negative: correct base, wrong corroborators — gate short-circuits
        base_v = CONSISTENT
        corr_v = CONTRADICTION
    return detect_content_madar(base, base_v, [(c, corr_v) for c in corr])


def _metrics(rows: list[tuple[str, bool]]) -> dict[str, object]:
    """rows = (label, fired). Positives = shared_error (+ tokenless); rest must not fire."""
    shared = [r for r in rows if r[0] == "shared_error"]
    tokenless = [r for r in rows if r[0] == "shared_error_tokenless"]
    all_shared = shared + tokenless
    indep_agree = [r for r in rows if r[0] == "independent_agreement"]
    near_miss = [r for r in rows if r[0] == "near_miss_boundary"]
    indep_diff = [r for r in rows if r[0] == "independent_different"]
    negatives = indep_agree + near_miss + indep_diff

    tp = sum(1 for _, f in all_shared if f)
    fn = len(all_shared) - tp
    fp = sum(1 for _, f in negatives if f)
    tn = len(negatives) - fp

    fp_agree = sum(1 for _, f in indep_agree if f)
    fp_near_miss = sum(1 for _, f in near_miss if f)
    tp_tb = sum(1 for _, f in shared if f)
    tp_tl = sum(1 for _, f in tokenless if f)

    recall = tp / len(all_shared) if all_shared else 0.0
    recall_tb = tp_tb / len(shared) if shared else 0.0
    recall_tl = tp_tl / len(tokenless) if tokenless else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "n": len(rows),
        "n_shared_error": len(shared),
        "n_shared_error_tokenless": len(tokenless),
        "n_independent_agreement": len(indep_agree),
        "n_near_miss_boundary": len(near_miss),
        "n_independent_different": len(indep_diff),
        "recall": round(recall, 3),
        "recall_tokenbearing": round(recall_tb, 3),
        "recall_tokenless": round(recall_tl, 3),
        "precision": round(precision, 3),
        "f1": round(f1, 3),
        "false_positive_rate": round(fp / len(negatives), 3) if negatives else 0.0,
        "false_positive_rate_agreement": round(fp_agree / len(indep_agree), 3)
        if indep_agree
        else 0.0,
        "false_positive_rate_near_miss": round(fp_near_miss / len(near_miss), 3)
        if near_miss
        else 0.0,
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "fp_agreement": fp_agree,
        "fp_near_miss": fp_near_miss,
    }


def build_report(
    raw: dict[str, object],
    gated: dict[str, object],
    raw_rows: list[tuple[str, bool]],
    n_rows: list[tuple[str, bool]],
    sha: str,
) -> str:
    lines = [
        "# Content-madār calibration — committed results (#54)",
        "",
        f"**Eval set:** {raw['n']} pairs "
        f"({raw['n_shared_error']} shared-error token-bearing, "
        f"{raw['n_shared_error_tokenless']} shared-error token-less, "
        f"{raw['n_independent_agreement']} independent-agreement, "
        f"{raw['n_near_miss_boundary']} near-miss boundary, "
        f"{raw['n_independent_different']} independent-different) + "
        f"{len(n_rows)} N-way · `eval_set_sha256={sha[:16]}…`",
        "",
        "| Layer | Recall | Recall (token-bearing) | Recall (token-less) | FP (agreement) | FP (near-miss) |",
        "|---|---|---|---|---|---|",
        f"| `shares_error_with` (raw, **measured**) | {raw['recall']:.3f} | "
        f"{raw['recall_tokenbearing']:.3f} | **{raw['recall_tokenless']:.3f}** | "
        f"**{raw['false_positive_rate_agreement']:.3f}** | **{raw['false_positive_rate_near_miss']:.3f}** |",
        f"| `detect_content_madar` (gated, **oracle — structural**) | {gated['recall']:.3f} | "
        f"— (structural) | — (structural) | — (structural) | — (structural) |",
        "",
        "## Reading the numbers",
        "",
        "- **Recall is no longer saturated at 1.0.** The token-bearing shared errors "
        f"({raw['n_shared_error']}) are caught with recall {raw['recall_tokenbearing']:.3f}; the "
        f"token-less shared errors ({raw['n_shared_error_tokenless']}) — the same mistake reworded "
        f"with no shared salient token — are caught with recall **{raw['recall_tokenless']:.3f}**. "
        "That is the honest recall gap: the fingerprint is a *surface-token* detector and cannot "
        "see a reworded error. Overall recall is "
        f"{raw['recall']:.3f} = {cast(int, raw['tp'])}/{cast(int, raw['tp']) + cast(int, raw['fn'])}.",
        f"- **FP (agreement)** remains the headline hazard: the bare fingerprint fires on "
        f"{raw['fp_agreement']}/{raw['n_independent_agreement']} genuine independent-agreement pairs "
        f"({raw['false_positive_rate_agreement']:.3f}) — correct facts sharing a salient token.",
        f"- **FP (near-miss)** is a *newly measured defect*, not fixed here: the bare fingerprint fires on "
        f"{raw['fp_near_miss']}/{raw['n_near_miss_boundary']} near-miss boundary pairs "
        f"({raw['false_positive_rate_near_miss']:.3f}) — one correct and one wrong claim sharing a subject "
        "token but differing in value (1687 vs 1689). The entity-set-equality rule fires *before* the "
        "numbers are compared, so identically-phrased near-misses collide. This is disclosed, not fixed "
        "(fixing the detector is a separate change).",
        f"- **N-way (3+ chain):** {n_rows[0][1]} of the shared-error N-way case(s) fire and "
        f"{sum(1 for l, f in n_rows if l == 'n_chain_negative' and not f)} negative control(s) correctly "
        "do not fire — API-coverage verification of `detect_content_madar`'s any-match semantics "
        "(oracle-fed, structural).",
        "",
        "- The **gated row is structural, not an empirical FP rate** (oracle-fed verdicts), so its "
        "FP/recall columns are `— (structural)`. The real end-to-end FP is "
        "`fcr_base × fcr_corr × raw_fire_rate`, measured in `experiments/critic_eval`, not here.",
        "",
        "## Honest limits",
        "",
        f"Small pilot set. Headline FP-on-agreement is {raw['fp_agreement']}/{raw['n_independent_agreement']} "
        "with a wide Wilson CI at this n; the token-less recall gap and the near-miss FP are the newly "
        "measured, honest findings. The gated row is structural. Nothing here fixes the detector — it "
        "measures it. `src/isnad/core/content_madar.py` is unchanged by this harness.",
    ]
    return "\n".join(lines) + "\n"


def _compose_end_to_end(raw_fire_rate: float) -> dict[str, dict[str, float]]:
    """Compose the shipped detector's end-to-end FP: fcr_base × fcr_corr × raw_fire_rate.

    Both critic false-contradiction factors come from experiments/critic_eval/results.json;
    raw_fire_rate is the measured fingerprint collision rate from THIS harness. Two models:
    independent errors (fcr × fcr × raw, the headline) and correlated errors (fcr × raw,
    the upper bound for two restatements of the same fact under a deterministic critic).
    """
    critic_path = _HERE.parent / "critic_eval" / "results.json"
    critic = json.loads(critic_path.read_text())
    out: dict[str, dict[str, float]] = {}
    for tier, m in critic.get("metrics", {}).items():
        fcr = float(m.get("false_contradiction_rate", 0.0))
        out[tier] = {
            "false_contradiction_rate": fcr,
            "end_to_end_fp_independent": round(fcr * fcr * raw_fire_rate, 6),
            "end_to_end_fp_correlated_upper": round(fcr * raw_fire_rate, 6),
        }
    return out


def main() -> None:
    cases = all_cases()
    sha = _eval_set_sha256(cases)

    raw_rows = [(label, _raw_fires(a, b)) for label, a, b in cases]
    gated_rows = [(label, _gated_fires(label, a, b)) for label, a, b in cases]

    raw_m = _metrics(raw_rows)
    gated_m = _metrics(gated_rows)
    e2e = _compose_end_to_end(cast(float, raw_m["false_positive_rate_agreement"]))

    n_cases = n_chain_cases()
    n_rows = [(label, _nway_fires(label, base, corr)) for label, base, corr in n_cases]

    print(
        f"raw    recall={raw_m['recall']:.3f} (tb={raw_m['recall_tokenbearing']:.3f}, "
        f"tl={raw_m['recall_tokenless']:.3f}) "
        f"FP(agree)={raw_m['false_positive_rate_agreement']:.3f} "
        f"FP(near-miss)={raw_m['false_positive_rate_near_miss']:.3f}"
    )
    print(f"n-way  {[(l, f) for l, f in n_rows]}")

    record = {
        "schema_version": 2,
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
        "end_to_end_fp": e2e,
        "n_way": [{"label": lbl, "fired": fired} for lbl, fired in n_rows],
        "cases": cases,
    }
    print("\nend-to-end FP (fcr_base x fcr_corr x raw_fire_rate):")
    for tier, v in e2e.items():
        print(
            f"  {tier}: fcr={v['false_contradiction_rate']}  independent={v['end_to_end_fp_independent']}  correlated_upper={v['end_to_end_fp_correlated_upper']}"
        )
    (_HERE / "results.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    (_HERE / "RESULTS.md").write_text(build_report(raw_m, gated_m, raw_rows, n_rows, sha))
    print(f"\nWrote {_HERE / 'RESULTS.md'} and results.json")


if __name__ == "__main__":
    main()
