"""ISNAD φ study — Experiment B/C: naive vs φ-discounted corroboration.

Pure + deterministic (no network). Two corroboration policies over the same
per-model answers and oracle:

- **B (naive):** k disjoint routes are treated as k independent votes — a claim is
  corroborated (upgraded) when ``>= threshold`` models agree on the same answer.
- **C (φ-discounted):** each *additional* agreeing route is scaled by the Kish
  factor ``n_eff/k = 1/(1+(k−1)φ̄)``, so the corroboration strength of ``m``
  agreeing models is ``1 + (m−1)·n_eff/k`` instead of ``m``. With φ>0, ``n_eff<k``,
  so the discounted policy is strictly more conservative: it can never upgrade MORE
  than naive (the discount only lowers the strength of correlated extra votes).

Primary endpoint: Δfalse-upgrade rate (fraction of claims falsely upgraded) at
matched coverage. Secondary: Δcoverage, Δrisk (P(wrong | upgraded)).

The naive policy is exactly the discounted policy with φ=0 (then n_eff=k and
``1+(m−1)·n_eff/k = m``), so the two share one code path.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def n_eff(phi_bar: float, k: int) -> float:
    """Kish effective sample size n_eff = k / (1 + (k−1)φ̄)."""
    if k <= 1:
        return float(k)
    denom = 1 + (k - 1) * phi_bar
    return k / denom if denom > 0 else float("inf")


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def agreement_counts(answers: dict[str, object]) -> Counter[float]:
    """Count agreeing answers per claim (models agree iff their parsed floats are equal)."""
    vals = [_to_float(a) for a in answers.values()]
    return Counter(v for v in vals if v is not None)


def corroboration_strength(m: int, phi_bar: float, k: int) -> float:
    """Strength of ``m`` agreeing models under Kish equicorrelation.

    Kish's exact form for m routes with pairwise error correlation φ̄:
    strength(m) = m / (1 + (m−1)·φ̄). At m=1 → 1; at m=k → n_eff.
    φ=0 → strength = m (naive). φ>0 → strength < m (discounted).
    """
    if m <= 1:
        return float(m)
    denom = 1 + (m - 1) * phi_bar
    return m / denom if denom > 0 else float(m)


def policy(
    answers_by_claim: dict[str, dict[str, object]], phi_bar: float, k: int, threshold: int = 2
) -> dict[str, tuple[bool, float | None, float]]:
    """Apply a corroboration policy.

    Returns {claim_id: (upgraded, agreed_answer, strength)}. ``agreed_answer`` is the
    mode answer (the value that reached the max count); ``strength`` is the
    discounted corroboration strength of that mode.
    """
    out: dict[str, tuple[bool, float | None, float]] = {}
    for cid, answers in answers_by_claim.items():
        counts = agreement_counts(answers)
        if not counts:
            out[cid] = (False, None, 0.0)
            continue
        agreed, m = counts.most_common(1)[0]
        strength = corroboration_strength(m, phi_bar, k)
        out[cid] = (strength >= threshold, agreed, strength)
    return out


def is_correct(agreed: float | None, oracle: object) -> bool:
    o = _to_float(oracle)
    if agreed is None or o is None:
        return False
    if o == 0:
        return abs(agreed) <= 1e-9
    return abs(agreed - o) / abs(o) <= 1e-6


def evaluate(
    answers_by_claim: dict[str, dict[str, object]],
    oracle_by_claim: dict[str, object],
    phi_bar: float,
    k: int,
    threshold: int = 2,
) -> dict[str, float]:
    """Return metrics for one policy: false-upgrade rate, coverage, risk."""
    pol = policy(answers_by_claim, phi_bar, k, threshold)
    n = len(answers_by_claim)
    upgraded = 0
    false_upgrades = 0
    for cid, (up, agreed, _strength) in pol.items():
        if up:
            upgraded += 1
            if not is_correct(agreed, oracle_by_claim.get(cid)):
                false_upgrades += 1
    coverage = upgraded / n if n else 0.0
    risk = false_upgrades / upgraded if upgraded else 0.0
    false_upgrade_rate = false_upgrades / n if n else 0.0
    return {
        "false_upgrade_rate": false_upgrade_rate,
        "coverage": coverage,
        "risk": risk,
        "upgraded": upgraded,
        "false_upgrades": false_upgrades,
        "n_claims": n,
    }


def compare(
    answers_by_claim: dict[str, dict[str, object]],
    oracle_by_claim: dict[str, object],
    phi_bar: float,
    k: int,
    threshold: int = 2,
) -> dict[str, object]:
    """Compare naive (φ=0) vs φ-discounted (φ=φ̄) at the same threshold."""
    naive = evaluate(answers_by_claim, oracle_by_claim, 0.0, k, threshold)
    discounted = evaluate(answers_by_claim, oracle_by_claim, phi_bar, k, threshold)
    return {
        "phi_bar": phi_bar,
        "k": k,
        "n_eff": n_eff(phi_bar, k),
        "threshold": threshold,
        "naive": naive,
        "discounted": discounted,
        "delta_false_upgrade_rate": naive["false_upgrade_rate"] - discounted["false_upgrade_rate"],
        "delta_coverage": naive["coverage"] - discounted["coverage"],
        "delta_risk": naive["risk"] - discounted["risk"],
    }


def threshold_sweep(
    answers_by_claim: dict[str, dict[str, object]],
    oracle_by_claim: dict[str, object],
    phi_bar: float,
    k: int,
) -> list[dict[str, object]]:
    """Per-threshold metrics for one policy (thresholds 1..k).

    This is the matched-coverage substrate: each threshold yields a
    (coverage, false-upgrade-rate) point; matched-coverage comparison picks the
    naive threshold whose coverage best matches the discounted policy's coverage.
    """
    out: list[dict[str, object]] = []
    for t in range(1, k + 1):
        m = evaluate(answers_by_claim, oracle_by_claim, phi_bar, k, t)
        out.append({"threshold": t, **m})
    return out


def matched_coverage_compare(
    answers_by_claim: dict[str, dict[str, object]],
    oracle_by_claim: dict[str, object],
    phi_bar: float,
    k: int,
    target_threshold: int = 2,
) -> dict[str, object]:
    """Primary endpoint: false-upgrade rate at matched coverage.

    The discounted policy at ``target_threshold`` defines the target coverage.
    Find the naive threshold that achieves the closest coverage, then compare
    false-upgrade rates at that matched coverage (naive is held to the same
    coverage, so any remaining false-upgrade gap is the discount's effect, not
    a coverage artifact).
    """
    disc = threshold_sweep(answers_by_claim, oracle_by_claim, phi_bar, k)
    naive = threshold_sweep(answers_by_claim, oracle_by_claim, 0.0, k)
    d_target = disc[target_threshold - 1]
    target_cov = d_target["coverage"]
    n_matched = min(naive, key=lambda r: abs(r["coverage"] - target_cov))
    return {
        "target_threshold": target_threshold,
        "target_coverage": target_cov,
        "discounted": d_target,
        "naive_matched": n_matched,
        "naive_matched_threshold": n_matched["threshold"],
        "delta_false_upgrade_rate_matched": n_matched["false_upgrade_rate"]
        - d_target["false_upgrade_rate"],
        "delta_coverage_matched": n_matched["coverage"] - target_cov,
        "delta_risk_matched": n_matched["risk"] - d_target["risk"],
        "naive_sweep": naive,
        "discounted_sweep": disc,
    }


def load_answers_and_oracle() -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    corpus = json.loads((_HERE / "corpus.json").read_text(encoding="utf-8"))
    oracle_by_claim = {c["id"]: c["oracle_value"] for c in corpus}
    answers_by_claim: dict[str, dict[str, object]] = {c["id"]: {} for c in corpus}
    for p in sorted((_HERE / "results").glob("*.json")):
        for r in json.loads(p.read_text(encoding="utf-8")):
            cid = r["claim_id"]
            if cid in answers_by_claim:
                answers_by_claim[cid][r["model"]] = r["answer_value"]
    return answers_by_claim, oracle_by_claim


def main() -> None:
    answers_by_claim, oracle_by_claim = load_answers_and_oracle()
    stats = json.loads((_HERE / "stats.json").read_text(encoding="utf-8"))
    phi_bar = stats.get("phi_bar")
    k = int(stats.get("k", 0))
    if phi_bar is None or k < 2:
        print("stats.json has no phi_bar/k — run stats first")
        return
    result = compare(answers_by_claim, oracle_by_claim, float(phi_bar), k)
    matched = matched_coverage_compare(answers_by_claim, oracle_by_claim, float(phi_bar), k)
    result["matched_coverage"] = matched
    (_HERE / "experiment_bc.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
