# mypy: disable-error-code=arg-type,index,return-value,type-arg
"""ISNAD φ study — statistics.

Loads ``results/<model>.json``, joins on claim_id, computes per-model-pair:
φ (phi) on the binary error indicators, the same-wrong conditional agreement
(Kim's statistic), and the 2×2 table. Aggregates mean φ̄ → Kish
``n_eff = k / (1 + (k−1)φ̄)`` with a cluster-bootstrap 95% CI (resample by claim).
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
    # "google/gemma-4-31b-it:free" -> "google"; "deepseek/deepseek-chat" -> "deepseek"
    return model.split("/", 1)[0]


def _provider(model: str) -> str:
    return "deepseek" if model.startswith("deepseek/") else "openrouter"


def _phi(a: int, b: int, c: int, d: int) -> float | None:
    denom = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
    if denom == 0:
        return None  # no variation on at least one side
    return (a * d - b * c) / denom


def load_models() -> dict[str, dict[str, dict[str, object]]]:
    models: dict[str, dict[str, dict[str, object]]] = {}
    for p in sorted((_HERE / "results").glob("*.json")):
        rows = json.loads(p.read_text(encoding="utf-8"))
        for r in rows:
            models.setdefault(r["model"], {})[r["claim_id"]] = r
    return models


def error_vector(model_rows: dict[str, dict[str, object]], corpus: list[dict[str, str]]) -> tuple[list[float], list[str]]:
    """Return (error indicator vector, same-answer id vector) over the corpus."""
    err: list[float] = []
    ans: list[str] = []
    for fact in corpus:
        r = model_rows.get(fact["id"])
        a = r["answer_value"] if r else None
        err.append(1.0 if _is_error(a, fact["oracle_value"]) else 0.0)
        ans.append(a or "")
    return err, ans


def main() -> None:
    corpus = json.loads((_HERE / "corpus.json").read_text(encoding="utf-8"))
    models = load_models()
    if not models:
        print("no results/*.json found — run the runner first")
        return

    # error rate per model (for boundary exclusion)
    rates: dict[str, float] = {}
    for m, rows in models.items():
        ev, _ = error_vector(rows, corpus)
        rates[m] = sum(ev) / len(ev)
    print("error rates:")
    for m, r in sorted(rates.items()):
        print(f"  {m}: {r:.3f}")

    # pair stats
    names = sorted(models)
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            mi, mj = names[i], names[j]
            if rates[mi] < 0.01 or rates[mi] > 0.99 or rates[mj] < 0.01 or rates[mj] > 0.99:
                continue  # φ unstable at the boundary
            ei, ai = error_vector(models[mi], corpus)
            ej, aj = error_vector(models[mj], corpus)
            a = sum(1 for x, y in zip(ei, ej) if x == 1 and y == 1)
            b = sum(1 for x, y in zip(ei, ej) if x == 1 and y == 0)
            c = sum(1 for x, y in zip(ei, ej) if x == 0 and y == 1)
            d = sum(1 for x, y in zip(ei, ej) if x == 0 and y == 0)
            phi = _phi(a, b, c, d)
            both_wrong = a
            same_wrong = sum(
                1 for x, y, u, v in zip(ei, ej, ai, aj)
                if x == 1 and y == 1 and u == v
            )
            same_wrong_rate = (same_wrong / both_wrong) if both_wrong else None
            pairs.append(
                {
                    "mi": mi, "mj": mj,
                    "phi": round(phi, 4) if phi is not None else None,
                    "same_wrong": round(same_wrong_rate, 4) if same_wrong_rate is not None else None,
                    "table": {"a": a, "b": b, "c": c, "d": d},
                    "same_family": _family(mi) == _family(mj),
                    "cross_provider": _provider(mi) != _provider(mj),
                }
            )
            print(f"  φ({mi[:30]}, {mj[:30]}) = {phi if phi is None else round(phi,4)} "
                  f"same_wrong={same_wrong_rate if same_wrong_rate is None else round(same_wrong_rate,4)} "
                  f"table=({a},{b},{c},{d})")

    phis = [p["phi"] for p in pairs if p["phi"] is not None]
    k = len(names)
    if phis:
        phi_bar = sum(phis) / len(phis)
        n_eff = k / (1 + (k - 1) * phi_bar) if phi_bar > -1 / (k - 1) else float("inf")
        # cluster bootstrap by claim
        rng = random.Random(0)
        boot = []
        n_claims = len(corpus)
        idx = list(range(n_claims))
        for _ in range(1000):
            samp = [rng.choice(idx) for _ in range(n_claims)]
            # recompute phi_bar on the resampled claims (per pair phi)
            bphis = []
            for p in pairs:
                if p["phi"] is None:
                    continue
                ei, _ = error_vector(models[p["mi"]], corpus)
                ej, _ = error_vector(models[p["mj"]], corpus)
                ei = [ei[x] for x in samp]
                ej = [ej[x] for x in samp]
                a = sum(1 for x, y in zip(ei, ej) if x == 1 and y == 1)
                b = sum(1 for x, y in zip(ei, ej) if x == 1 and y == 0)
                c = sum(1 for x, y in zip(ei, ej) if x == 0 and y == 1)
                d = sum(1 for x, y in zip(ei, ej) if x == 0 and y == 0)
                bp = _phi(a, b, c, d)
                if bp is not None:
                    bphis.append(bp)
            if bphis:
                bb = sum(bphis) / len(bphis)
                if bb > -1 / (k - 1):
                    boot.append(k / (1 + (k - 1) * bb))
        if boot:
            boot.sort()
            lo = boot[int(0.025 * len(boot))]
            hi = boot[int(0.975 * len(boot))]
            print(f"\nφ̄ = {phi_bar:.4f} · k = {k} · n_eff = {n_eff:.3f} · 95% CI [{lo:.3f}, {hi:.3f}]")

    out = {
        "k": k,
        "phi_bar": round(phi_bar, 4) if phis else None,
        "n_eff": round(n_eff, 4) if phis else None,
        "n_eff_ci": [round(lo, 4), round(hi, 4)] if (phis and boot) else [],
        "pairs": pairs,
        "error_rates": {m: round(r, 4) for m, r in rates.items()},
    }
    (_HERE / "stats.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote stats.json")


if __name__ == "__main__":
    main()
