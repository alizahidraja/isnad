"""ISNAD-Bench — per-claim graded-output export (#134).

Emits the benchmark's *derived* output — one JSONL row per graded chain — plus a
reproducibility header, so the κ=0.871 result is citable and verifiable without
cloning the repo or re-running against the 1.6 GB source database.

This is NOT a re-host of ``emadjumaah/hadith-kg`` (CC-BY-4.0).  It is the
derived grading: the scholar's verdict, ISNAD's predicted chain grade, and the
principled disagreement bucket, computed by the exact shared functions the
benchmark's κ is computed from (``bench/_grade.py``).

Run:
    uv run python -m bench.export --db data/hadith-kg.db -o data/export/isnad-bench.jsonl
    uv run python -m bench.export --sample 5000 -o /tmp/sample.jsonl   # smoke test

Output schema (one JSON object per line, after the leading ``#`` header lines):
    sanad_id, hukum, true_grade, predicted_grade, disagreement_bucket,
    is_complete, has_gap, has_taliq, narrator_rank_nos, mode
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
from pathlib import Path

from bench._grade import bucket, chain_grade_from_narrators, grade_one_chain
from bench.data import iter_chains
from bench.mapping import chain_grade_from_hukum

# The mapping file is the scientific claim; its hash is embedded in the header
# so a downstream consumer can verify the export used the preregistered mapping.
_MAPPING_PATH = Path(__file__).parent / "docs" / "mapping.md"
_SOURCE_SHA256 = "d528084321e715006712e0e2461809a3afc9408065a1d1af90238c8b723815a6"


def _mapping_hash() -> str:
    return hashlib.sha256(_MAPPING_PATH.read_bytes()).hexdigest()


def _load_sanad_ids(db_path: str) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT id FROM sanads")]
    finally:
        conn.close()


def export(db_path: str, out_path: str, *, sample: int | None, seed: int, lenient: bool) -> int:
    """Stream per-claim graded rows to ``out_path``; return rows written."""
    all_ids = _load_sanad_ids(db_path)
    if sample is not None:
        rng = random.Random(seed)
        ids = rng.sample(all_ids, sample)
    else:
        ids = all_ids
    id_set = set(ids)

    header = {
        "dataset": "isnad-bench",
        "derived_from": "emadjumaah/hadith-kg (CC-BY-4.0)",
        "source_sha256": _SOURCE_SHA256,
        "mapping": "bench/docs/mapping.md (preregistered)",
        "mapping_sha256": _mapping_hash(),
        "mode": "lenient" if lenient else "strict",
        "invocation": f"bench.export --db {db_path} --sample {sample} --seed {seed}"
        + (" --lenient" if lenient else ""),
        "schema": [
            "sanad_id",
            "hukum",
            "true_grade",
            "predicted_grade",
            "disagreement_bucket",
            "is_complete",
            "has_gap",
            "has_taliq",
            "narrator_rank_nos",
            "mode",
        ],
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with out.open("w", encoding="utf-8") as f:
        # Reproducibility header as JSON comment lines (the ``# `` prefix keeps
        # the file valid JSONL — every non-comment line is one JSON object).
        f.write("# " + json.dumps(header, ensure_ascii=False) + "\n")
        for chain in iter_chains(db_path, id_set):
            true = chain_grade_from_hukum(chain.hukum)
            if true is None:
                continue
            narrator_grades, is_complete, rank_nos, has_taliq, has_gap = grade_one_chain(
                chain.nodes
            )
            if not narrator_grades:
                continue
            pred = chain_grade_from_narrators(narrator_grades, is_complete, lenient)
            row = {
                "sanad_id": chain.sanad_id,
                "hukum": chain.hukum,
                "true_grade": true.value,
                "predicted_grade": pred,
                "disagreement_bucket": bucket(
                    true.value, pred, has_gap, has_taliq, rank_nos, chain.hukum
                ),
                "is_complete": is_complete,
                "has_gap": has_gap,
                "has_taliq": has_taliq,
                "narrator_rank_nos": rank_nos,
                "mode": "lenient" if lenient else "strict",
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows += 1
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/hadith-kg.db", help="path to hadith-kg.db")
    parser.add_argument("-o", "--out", default="data/export/isnad-bench.jsonl")
    parser.add_argument("--sample", type=int, default=None, help="random sample of N sanads")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--lenient", action="store_true", help="UNGRADED → ḥasan (opt-in)")
    args = parser.parse_args()

    rows = export(args.db, args.out, sample=args.sample, seed=args.seed, lenient=args.lenient)
    print(f"wrote {rows} rows to {args.out}")


if __name__ == "__main__":
    main()
