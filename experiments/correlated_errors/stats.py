"""ISNAD φ study — statistics.

Loads ``results/<model>.json``, joins on claim_id, computes per-model-pair:
φ (phi) on the binary error indicators, the same-wrong conditional agreement
(Kim's statistic), and the 2×2 table. Aggregates mean φ̄ → Kish
``n_eff = k / (1 + (k−1)φ̄)`` with a cluster-bootstrap 95% CI (resample by claim).

Retention rule: a model is kept for the φ matrix and for ``k`` only if it covers
≥90% of the corpus facts AND its error rate is inside the pre-reg [1%, 99%] band.
A fact missing from a model's results is treated as MISSING (excluded from that
model's denominator and from pairwise 2×2 tables), never as an error — so stale
results from a different corpus are excluded by coverage, not counted as 100%
parse-failure.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _float(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _is_error(answer: str | None, oracle: str) -> bool:
    a = _float(answer)
    o = _float(oracle)
    if a is None or o is None:
        return True
    if o == 0:
        return abs(a) > 1e-9
    return abs(a - o) / abs(o) > 1e-6


def _family(model: str) -> str:
    return model.split("/", 1)[0]


def _phi(a: int, b: int, c: int, d: int) -> float | None:
    denom = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
    if denom == 0:
        return None
    return (a * d - b * c) / denom


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Linear-interpolated percentile (numpy ``linear`` style)."""
    if not sorted_vals:
        raise ValueError("empty sample")
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _pair_table(
    ei: list[float], ej: list[float], ai: list[str], aj: list[str], ci: list[bool], cj: list[bool]
) -> tuple[int, int, int, int, int, int]:
    """2x2 table + same-wrong counts for one model pair.

    Returns (a, b, c, d, both_wrong, same_wrong). A fact is counted only when BOTH
    models cover it (ci and cj); missing/missing or one-sided-missing is excluded.
    ``same_wrong`` is incremented only for facts where both models are wrong AND
    their parsed answers are numerically equal (``float(u) == float(v)``), never on
    raw-string equality, so ``"9.8"`` and ``"9.80"`` DO count as the same wrong value
    while two missing/refused answers never do.
    """
    a = b = c = d = both_wrong = same_wrong = 0
    for x, y, u, v, ci_, cj_ in zip(ei, ej, ai, aj, ci, cj):
        if not (ci_ and cj_):
            continue
        if x == 1 and y == 1:
            a += 1
            both_wrong += 1
            fu, fv = _float(u), _float(v)
            if fu is not None and fv is not None and fu == fv:
                same_wrong += 1
        elif x == 1 and y == 0:
            b += 1
        elif x == 0 and y == 1:
            c += 1
        else:
            d += 1
    return a, b, c, d, both_wrong, same_wrong


def _bootstrap_ci(
    pairs: list[dict[str, object]],
    models: dict[str, dict[str, dict[str, object]]],
    corpus: list[dict[str, str]],
    k: int,
    n_draws: int = 1000,
    seed: int = 0,
) -> tuple[float | None, float | None]:
    """Cluster-bootstrap 95% CI for n_eff (resample by claim, NOT iid).

    Resamples claim indices once per draw and reuses the SAME sample across all
    pairs, preserving the cross-pair dependence structure. Returns (lo, hi) via
    linear-interpolated percentiles of the n_eff bootstrap distribution.
    """
    rng = random.Random(seed)
    n_claims = len(corpus)
    idx = list(range(n_claims))
    boot: list[float] = []
    for _ in range(n_draws):
        samp = [rng.choice(idx) for _ in range(n_claims)]
        bphis: list[float] = []
        for p in pairs:
            if p["phi"] is None:
                continue
            ei, _, ci = error_vector(models[p["mi"]], corpus)
            ej, _, cj = error_vector(models[p["mj"]], corpus)
            ei = [ei[x] for x in samp]
            ej = [ej[x] for x in samp]
            ci = [ci[x] for x in samp]
            cj = [cj[x] for x in samp]
            a, b, c, d = 0, 0, 0, 0
            for x, y, ci_, cj_ in zip(ei, ej, ci, cj):
                if not (ci_ and cj_):
                    continue
                if x == 1 and y == 1:
                    a += 1
                elif x == 1 and y == 0:
                    b += 1
                elif x == 0 and y == 1:
                    c += 1
                else:
                    d += 1
            bp = _phi(a, b, c, d)
            if bp is not None:
                bphis.append(bp)
        if bphis:
            bb = sum(bphis) / len(bphis)
            if bb > -1 / (k - 1):
                boot.append(k / (1 + (k - 1) * bb))
    if not boot:
        return None, None
    boot.sort()
    return _percentile(boot, 0.025), _percentile(boot, 0.975)


def load_models() -> dict[str, dict[str, dict[str, object]]]:
    models: dict[str, dict[str, dict[str, object]]] = {}
    for p in sorted((_HERE / "results").glob("*.json")):
        rows = json.loads(p.read_text(encoding="utf-8"))
        for r in rows:
            models.setdefault(r["model"], {})[r["claim_id"]] = r
    return models


def error_vector(
    model_rows: dict[str, dict[str, object]], corpus: list[dict[str, str]]
) -> tuple[list[float], list[str], list[bool]]:
    """Return (error indicator, answer string, covered mask) over the corpus.

    A fact absent from the model's results is covered=False and carries a
    placeholder (0.0 error, "" answer); callers exclude covered=False entries
    from denominators and 2×2 tables.
    """
    err: list[float] = []
    ans: list[str] = []
    covered: list[bool] = []
    for fact in corpus:
        r = model_rows.get(fact["id"])
        if r is None:
            err.append(0.0)
            ans.append("")
            covered.append(False)
        else:
            a = r["answer_value"]
            err.append(1.0 if _is_error(a, fact["oracle_value"]) else 0.0)
            ans.append(a or "")
            covered.append(True)
    return err, ans, covered


def _rate(err: list[float], covered: list[bool]) -> float:
    n = sum(covered)
    if n == 0:
        return 1.0
    return sum(e for e, c in zip(err, covered) if c) / n


def _coverage(covered: list[bool]) -> float:
    return sum(covered) / len(covered)


def retained_models(rates: dict[str, float], covs: dict[str, float]) -> list[str]:
    """Models kept for the φ matrix and ``k``.

    Retention requires BOTH: coverage ≥ 90% of corpus facts AND error rate
    inside the pre-reg [1%, 99%] band (so stale/foreign result sets and
    near-perfect/near-useless models are excluded, never silently counted).
    """
    return [m for m in sorted(rates) if covs.get(m, 0.0) >= 0.90 and 0.01 <= rates[m] <= 0.99]


def main() -> None:
    corpus = json.loads((_HERE / "corpus.json").read_text(encoding="utf-8"))
    models = load_models()
    if not models:
        print("no results/*.json found — run the runner first")
        return

    rates: dict[str, float] = {}
    covs: dict[str, float] = {}
    for m, rows in models.items():
        ev, _, covered = error_vector(rows, corpus)
        rates[m] = _rate(ev, covered)
        covs[m] = _coverage(covered)
    print("error rates (over covered facts):")
    for m in sorted(models):
        print(f"  {m}: rate {rates[m]:.3f} · coverage {covs[m]:.3f}")

    truncated: dict[str, int] = {}
    refusals: dict[str, int] = {}
    for m, rows in models.items():
        truncated[m] = sum(
            1 for r in rows.values() if str(r.get("error") or "").startswith("truncated")
        )
        refusals[m] = sum(
            1
            for r in rows.values()
            if r.get("answer_value") is None
            and r.get("error") is None
            and r.get("finish_reason") != "length"
        )
    print("truncated / refusals (counted separately from error rate):")
    for m in sorted(models):
        print(f"  {m}: truncated {truncated[m]} · refusals {refusals[m]}")

    retained = retained_models(rates, covs)
    excluded: dict[str, dict[str, object]] = {}
    for m in sorted(models):
        if m not in retained:
            if covs[m] < 0.90:
                reason = f"coverage {covs[m]:.3f} < 0.90 (stale/foreign result set)"
            elif rates[m] < 0.01:
                reason = "error rate < 1% (φ unstable at boundary)"
            else:
                reason = "error rate > 99% (φ unstable at boundary)"
            excluded[m] = {
                "rate": round(rates[m], 4),
                "coverage": round(covs[m], 4),
                "reason": reason,
            }
    if excluded:
        print("excluded (coverage ≥90% AND error rate in [1%,99%]):")
        for m in sorted(excluded):
            print(f"  {m}: {excluded[m]['reason']}")

    names = retained
    pairs: list[dict[str, object]] = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            mi, mj = names[i], names[j]
            ei, ai, ci = error_vector(models[mi], corpus)
            ej, aj, cj = error_vector(models[mj], corpus)
            a, b, c, d, both_wrong, same_wrong = _pair_table(ei, ej, ai, aj, ci, cj)
            phi = _phi(a, b, c, d)
            same_wrong_rate = (same_wrong / both_wrong) if both_wrong else None
            pairs.append({
                "mi": mi,
                "mj": mj,
                "phi": phi,
                "same_wrong": same_wrong_rate,
                "table": {"a": a, "b": b, "c": c, "d": d},
                "same_family": _family(mi) == _family(mj),
                "cross_provider": _family(mi) != _family(mj),
            })
            print(
                f"  φ({mi[:30]}, {mj[:30]}) = {phi if phi is None else round(phi, 4)} "
                f"same_wrong={same_wrong_rate if same_wrong_rate is None else round(same_wrong_rate, 4)} "
                f"table=({a},{b},{c},{d})"
            )

    phis = [p["phi"] for p in pairs if p["phi"] is not None]
    k = len(retained)
    phi_bar = n_eff = lo = hi = None
    if phis:
        phi_bar = sum(phis) / len(phis)  # full precision, NOT from rounded per-pair values
        n_eff = k / (1 + (k - 1) * phi_bar) if phi_bar > -1 / (k - 1) else float("inf")

        lo, hi = _bootstrap_ci(pairs, models, corpus, k)
        if lo is not None and hi is not None:
            print(
                f"\nφ̄ = {phi_bar:.4f} · k = {k} · n_eff = {n_eff:.3f} · 95% CI [{lo:.3f}, {hi:.3f}]"
            )

    out = {
        "k": k,
        "phi_bar": phi_bar,
        "n_eff": n_eff,
        "n_eff_ci": [lo, hi] if (phis and lo is not None and hi is not None) else [],
        "pairs": pairs,
        "error_rates": {m: rates[m] for m in sorted(rates)},
        "coverage": {m: covs[m] for m in sorted(covs)},
        "excluded": excluded,
        "truncated_count": truncated,
        "refusal_count": refusals,
    }
    (_HERE / "stats.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nwrote stats.json")


if __name__ == "__main__":
    main()
