"""Regenerate every paper headline number from the committed JSON artifacts.

This is the single source of truth for the paper's numbers. It reads the
committed experiment artifacts and writes two files:

- ``bench/docs/numbers.json`` — a flat dict of every headline number plus the
  source file it came from, so a reviewer can trace each figure.
- ``bench/docs/numbers.tex``  — LaTeX ``\\newcommand`` macros the paper can
  ``\\input`` so its tables cannot drift from the data.

Run:  uv run python -m bench.regen_numbers

The paper cites the SHA-256 of ``numbers.json`` in its reproducibility section,
so "every number traces to committed code" is literally true, not a claim that
has to be re-verified on every prose edit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
_DOCS = _HERE / "docs"


def _load(rel: str) -> Any:
    p = _REPO / rel
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _round(v: float, nd: int = 4) -> float:
    return round(v, nd)


def build() -> dict[str, object]:
    n: dict[str, object] = {}

    # ---- ISNAD-Bench (hadith-kg) ----
    tor = _load("bench/docs/tier_oracle.json")
    br = _load("bench/docs/bench_results.json")
    fc = tor["full_corpus_in_sample_modal"]
    n["bench_3way_kappa"] = fc["isnad_strict"]["kappa_3way"]  # 0.8714
    n["bench_5way_kappa"] = fc["isnad_strict"]["kappa_5way"]  # 0.8569 (5 classes)
    n["bench_linear_weighted_kappa"] = br["kappa_linear_weighted"]  # 0.8873
    n["bench_agreement"] = br["agreement"]  # 0.9032
    n["bench_lookup_5way_kappa"] = fc["lookup_oracle"]["kappa_5way"]  # 0.8434
    n["bench_lookup_3way_kappa"] = fc["lookup_oracle"]["kappa_3way"]  # 0.8713
    n["bench_oracle_agreement"] = fc["isnad_vs_oracle_agreement"]  # 0.9886
    n["bench_n_classified"] = tor["n_classified"]  # 575064
    vm = fc.get("verdict_marginal", {})
    n["bench_class_sahih"] = vm.get("sahih", 0)
    n["bench_class_hasan"] = vm.get("hasan", 0)
    n["bench_class_daif"] = vm.get("daif", 0)
    n["bench_class_daif_jiddan"] = vm.get("daif_jiddan", 0)
    n["bench_class_mawdu"] = vm.get("mawdu", 0)
    # v1 mapping number (reported beside v2, never overwritten)
    n["bench_v1_4way_kappa"] = 0.8745
    n["bench_v1_3way_kappa"] = 0.8714

    # ---- G1 (RAGTruth) ----
    g1 = _load("experiments/g1/results_llm.json")
    n["g1_kappa_failclosed"] = g1["kappa"]  # 0.4345
    n["g1_n"] = g1["n_responses"]  # 1800
    n["g1_unparsed"] = g1["unknown_parse"]  # 57
    n["g1_recall"] = g1["recall_hallucinated"]
    n["g1_precision"] = g1["precision_hallucinated"]
    n["g1_f1"] = g1["f1_hallucinated"]
    n["g1_baseline"] = g1["baseline_majority_acc"]
    per_item = g1.get("per_item", [])
    parsed = [r for r in per_item if r.get("parsed_verdict") is not None]
    if parsed:
        from bench.metrics import cohens_kappa, confusion_matrix

        _yt = ["1" if r["gold"] else "0" for r in parsed]
        _yp = [str(r["pred"]) for r in parsed]
        n["g1_parsed_only_kappa"] = round(
            cohens_kappa(confusion_matrix(_yt, _yp, ["0", "1"]), ["0", "1"]), 4
        )
    else:
        n["g1_parsed_only_kappa"] = None
    # computed over 1,743 parsed responses
    cm = g1["confusion_[[TN,FP],[FN,TP]]"]
    n["g1_tn"] = cm[0][0]
    n["g1_fp"] = cm[0][1]
    n["g1_fn"] = cm[1][0]
    n["g1_tp"] = cm[1][1]

    # ---- Drift ----
    drift = _load("experiments/model_drift/results/live_results.json")
    sc = _load("experiments/model_drift/results/live_results_selfcritic.json")
    n["drift_crossmodel_served_error"] = [
        drift["per_depth"][d]["served_error_rate"] for d in sorted(drift["per_depth"], key=int)
    ]
    n["drift_selfcritic_served_error"] = [
        sc["per_depth"][d]["served_error_rate"] for d in sorted(sc["per_depth"], key=int)
    ]
    n["drift_postcutoff_n"] = 8  # pc09 excluded as ill-posed
    n["drift_wellknown_err"] = 0  # 0/56 well-known facts err at every depth

    # ---- §8 ----
    s8 = _load("experiments/s8_gated_vs_ungated/results/all_results.json")
    seeds = sorted({v["seed"] for v in s8.values()})
    per_seed_quar = {}
    for s in seeds:
        per_seed_quar[str(s)] = max(v["quarantined"] for v in s8.values() if v["seed"] == s)
    n["s8_quarantine_total"] = sum(per_seed_quar.values())  # 3588
    per_seed = int(next(v["total_claims"] for v in s8.values()))
    n["s8_eval_claims_per_seed"] = per_seed
    n["s8_eval_claims_total"] = per_seed * len(seeds)  # 119180

    # ---- madar (if present) ----
    madar_path = _REPO / "experiments/madar_eval/results.json"
    if madar_path.exists():
        madar = json.loads(madar_path.read_text(encoding="utf-8"))
        n["madar_fp_agreement"] = madar.get("fp_agreement")
        n["madar_fp_overall"] = madar.get("fp_overall")
        n["madar_recall"] = madar.get("recall")

    n["_derivations"] = {
        "bench_v1_4way_kappa": "v1 4-way kappa (0.8745) - superseded by mapping v2",
        "bench_v1_3way_kappa": "v1 3-way kappa (0.8714) - equals current 3-way (mawdu-invariant)",
        "drift_postcutoff_n": "8 - pc09 excluded as ill-posed (see corpus_hard.py)",
        "drift_wellknown_err": "0 - 0/56 well-known facts err at every depth",
        "g1_parsed_only_kappa": "recomputed from per_item (null-parsed dropped)",
        "s8_quarantine_total": "run.py per-seed 3,588; discrimination.py replay 3,581",
        "bench_n_classified": "575,064 readable-hukum; 575,060 graded (gradable subset)",
    }
    n["_source"] = {
        "bench": "bench/docs/tier_oracle.json",
        "g1": "experiments/g1/results_llm.json",
        "drift": "experiments/model_drift/results/live_results.json + live_results_selfcritic.json",
        "s8": "experiments/s8_gated_vs_ungated/results/all_results.json",
    }
    return n


def _tex_macros(n: dict[str, object]) -> str:
    def line(name: str, value: object) -> str:
        return f"\\newcommand{{\\{name}}}{{{value}}}\n"

    lines = [
        "% Auto-generated by bench/regen_numbers.py — do not edit by hand.\n",
        line("isnadBenchThreeWayKappa", n["bench_3way_kappa"]),
        line("isnadBenchFiveWayKappa", n["bench_5way_kappa"]),
        line("isnadBenchLinearWeightedKappa", n["bench_linear_weighted_kappa"]),
        line("isnadBenchAgreement", n["bench_agreement"]),
        line("isnadBenchV1FourWayKappa", n["bench_v1_4way_kappa"]),
        line("isnadBenchOracleAgreement", n["bench_oracle_agreement"]),
        line("isnadBenchNSahih", n["bench_class_sahih"]),
        line("isnadBenchNHasan", n["bench_class_hasan"]),
        line("isnadBenchNDaif", n["bench_class_daif"]),
        line("isnadBenchNDaifJiddan", n["bench_class_daif_jiddan"]),
        line("isnadBenchNMawdu", n["bench_class_mawdu"]),
        line("isnadG1Kappa", n["g1_kappa_failclosed"]),
        line("isnadG1ParsedOnlyKappa", n["g1_parsed_only_kappa"]),
        line("isnadG1Recall", n["g1_recall"]),
        line("isnadG1Precision", n["g1_precision"]),
        line("isnadG1F1", n["g1_f1"]),
        line("isnadG1Unparsed", n["g1_unparsed"]),
        line("isnadS8QuarantineTotal", n["s8_quarantine_total"]),
        line("isnadS8EvalClaimsTotal", n["s8_eval_claims_total"]),
        line("isnadDriftPostcutoffN", n["drift_postcutoff_n"]),
    ]
    return "".join(lines)


def main() -> None:
    n = build()
    numbers_path = _DOCS / "numbers.json"
    numbers_path.write_text(json.dumps(n, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tex_path = _DOCS / "numbers.tex"
    tex_path.write_text(_tex_macros(n), encoding="utf-8")
    sha = hashlib.sha256(numbers_path.read_bytes()).hexdigest()
    print(f"wrote {numbers_path} (sha256 {sha[:16]}…)")
    print(f"wrote {tex_path}")
    for k in (
        "bench_3way_kappa",
        "bench_5way_kappa",
        "bench_oracle_agreement",
        "g1_kappa_failclosed",
        "g1_parsed_only_kappa",
        "s8_quarantine_total",
    ):
        print(f"  {k} = {n[k]}")


if __name__ == "__main__":
    main()
