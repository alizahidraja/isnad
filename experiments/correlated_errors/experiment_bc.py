"""ISNAD φ study — Experiment B/C: naive vs φ-discounted corroboration.

Pure + deterministic (no network). Two corroboration policies over the same
per-model answers and oracle:

- **B (naive):** k disjoint routes are treated as k independent votes — a claim is
  corroborated (upgraded) when ``>= threshold`` models agree on the same answer.
- **C (φ-discounted):** the corroboration strength of ``m`` agreeing models is
  ``m / (1 + (m−1)·φ̄)`` (Kish's exact form: equals ``n_eff`` at ``m=k``, equals
  ``m`` at φ=0). With φ>0, strength < m, so the discounted policy is strictly more
  conservative: it can never upgrade MORE than naive.

Primary endpoint: the false-upgrade gap at the corroboration bar (threshold=2).
With φ̄>0 the maximum strength is ``n_eff``; when ``n_eff < threshold`` the bar is
unreachable under the discount, so coverage is a STEP FUNCTION and the
pre-registered "matched coverage" comparison is not applicable. That limit is
reported honestly rather than forcing a matched-coverage number. Secondary:
Δcoverage, Δrisk (P(wrong | upgraded)).

The naive policy is exactly the discounted policy with φ=0 (then n_eff=k and
``m/(1+(m−1)φ̄) = m``), so the two share one code path.
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


def step_function_primary(
    answers_by_claim: dict[str, dict[str, object]],
    oracle_by_claim: dict[str, object],
    phi_bar: float,
    k: int,
    threshold: int = 2,
) -> dict[str, object]:
    """Primary endpoint: the false-upgrade gap AT the corroboration bar.

    With φ̄>0 the maximum corroboration strength is n_eff = k/(1+(k−1)φ̄). When
    n_eff < threshold, the discounted policy can never reach the bar, so coverage
    is a STEP FUNCTION (full at threshold=1, zero at threshold>=2) — not a tunable
    trade-off — and a matched-coverage comparison is not applicable. The honest
    statement is the step itself, reported here, with the naive threshold sweep
    retained so the coverage/risk curve stays visible.
    """
    n_eff_val = n_eff(phi_bar, k)
    naive_at_bar = evaluate(answers_by_claim, oracle_by_claim, 0.0, k, threshold)
    discounted_at_bar = evaluate(answers_by_claim, oracle_by_claim, phi_bar, k, threshold)
    bar_unreachable = n_eff_val < threshold
    return {
        "phi_bar": phi_bar,
        "k": k,
        "n_eff": n_eff_val,
        "threshold": threshold,
        "bar_unreachable": bar_unreachable,
        "explanation": (
            f"maximum corroboration strength is n_eff={n_eff_val:.3f} < threshold={threshold}; "
            "the discounted policy can never reach the corroboration bar, so coverage is a "
            "step function and matched coverage is not applicable."
        ),
        "naive_at_bar": naive_at_bar,
        "discounted_at_bar": discounted_at_bar,
        "delta_false_upgrade_rate": naive_at_bar["false_upgrade_rate"]
        - discounted_at_bar["false_upgrade_rate"],
        "delta_coverage": naive_at_bar["coverage"] - discounted_at_bar["coverage"],
        "delta_risk": naive_at_bar["risk"] - discounted_at_bar["risk"],
        "naive_sweep": threshold_sweep(answers_by_claim, oracle_by_claim, 0.0, k),
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
    primary = step_function_primary(answers_by_claim, oracle_by_claim, float(phi_bar), k)
    result["step_function"] = primary
    (_HERE / "experiment_bc.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
