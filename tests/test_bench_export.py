"""Tests for ISNAD-Bench export (#134).

Locks the per-claim export so the dataset artifact can never drift from the
benchmark's κ: the exported grades must recompute to exactly the κ that
``bench.run`` reports on the same sample.
"""

from __future__ import annotations

import json

import pytest

from bench._grade import bucket, chain_grade_from_narrators, grade_one_chain
from bench.data import Node
from bench.export import export
from bench.metrics import cohens_kappa, confusion_matrix

_CLASSES = ["sahih", "hasan", "daif", "mawdu"]


def _read_rows(path):
    rows = []
    header = None
    with open(path) as f:
        for line in f:
            if line.startswith("# "):
                header = json.loads(line[2:])
            else:
                rows.append(json.loads(line))
    return header, rows


def test_export_header_carries_reproducibility(tmp_path):
    out = tmp_path / "e.jsonl"
    export("data/hadith-kg.db", str(out), sample=200, seed=0, lenient=False)
    header, rows = _read_rows(out)
    assert header["dataset"] == "isnad-bench"
    assert header["derived_from"] == "emadjumaah/hadith-kg (CC-BY-4.0)"
    assert header["source_sha256"].startswith("d5280843")
    assert header["mapping_sha256"]  # non-empty
    assert header["schema"] == [
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
    ]
    assert len(rows) > 0


def test_export_rows_match_schema(tmp_path):
    out = tmp_path / "e.jsonl"
    export("data/hadith-kg.db", str(out), sample=200, seed=0, lenient=False)
    header, rows = _read_rows(out)
    for r in rows:
        assert set(r.keys()) == set(header["schema"])
        assert r["true_grade"] in _CLASSES
        assert r["predicted_grade"] in _CLASSES


def test_export_kappa_matches_bench_run(tmp_path):
    """The exported grades recompute to the same κ as bench.run on the sample."""
    out = tmp_path / "e.jsonl"
    export("data/hadith-kg.db", str(out), sample=2000, seed=0, lenient=False)
    _header, rows = _read_rows(out)
    cm = confusion_matrix(
        [r["true_grade"] for r in rows], [r["predicted_grade"] for r in rows], _CLASSES
    )
    k = cohens_kappa(cm, _CLASSES)

    # Recompute the same κ via the shared grading functions independently.
    from bench.data import iter_chains
    from bench.mapping import chain_grade_from_hukum

    ids = {r["sanad_id"] for r in rows}
    yt, yp = [], []
    for chain in iter_chains("data/hadith-kg.db", ids):
        true = chain_grade_from_hukum(chain.hukum)
        if true is None:
            continue
        grades, complete, _rn, _tl, _gap = grade_one_chain(chain.nodes)
        if not grades:
            continue
        yt.append(true.value)
        yp.append(chain_grade_from_narrators(grades, complete, False))
    cm2 = confusion_matrix(yt, yp, _CLASSES)
    k2 = cohens_kappa(cm2, _CLASSES)

    assert k == pytest.approx(k2, abs=1e-9)


def test_bucket_is_none_on_agreement():
    assert bucket("sahih", "sahih", False, False, [1], None) is None


def test_bucket_labels_sahih_hasan_boundary():
    assert bucket("sahih", "hasan", False, False, [1], None) == "grade: ṣaḥīḥ ↔ ḥasan boundary"


def test_bucket_labels_corroboration():
    b = bucket("daif", "hasan", False, False, [4], "ضعيف ويحسن إذا توبع")
    assert b == "corroboration: weak-alone → ḥasan-with-mutābaʿa"
