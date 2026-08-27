"""Tests for ISNAD-Bench export (#134).

Locks the per-claim export so the dataset artifact can never drift from the
benchmark's κ.  Uses a tiny SQLite fixture (the real 1.6 GB hadith-kg.db is
gitignored and not present in CI), so the export path is fully exercised without
the source corpus.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from bench._grade import bucket, chain_grade_from_narrators, grade_one_chain
from bench.data import iter_chains
from bench.export import export
from bench.mapping import chain_grade_from_hukum
from bench.metrics import cohens_kappa, confusion_matrix

_CLASSES = ["sahih", "hasan", "daif", "mawdu"]


def _make_db(path: str) -> None:
    """A small fixture: 3 narrators + a gap sentinel, 4 chains, 4 verdict tiers."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE rawis (id INTEGER, rank_no INTEGER, rank TEXT, name TEXT);
        CREATE TABLE sanads (id INTEGER, hukum TEXT, group_id INTEGER);
        CREATE TABLE sanad_rawis (sanad_id INTEGER, pos INTEGER, rawi_id INTEGER);
        """
    )
    # rank 1 = ṣaḥābī (RELIABLE); 3 = thiqah (RELIABLE); 6 = maqbūl (ACCEPTABLE);
    # 8 = ḍaʿīf (WEAK); 12 sentinel = gap.
    conn.execute("INSERT INTO rawis VALUES (1, 1, 'صحابي', 'عائشة')")
    conn.execute("INSERT INTO rawis VALUES (2, 3, 'ثقة', 'الزهري')")
    conn.execute("INSERT INTO rawis VALUES (3, 8, 'ضعيف الحديث', 'فلان')")
    conn.execute("INSERT INTO rawis VALUES (4, 12, NULL, 'موضع إرسال')")
    # Four chains: sahih, hasan, daif-via-weak-narrator, daif-via-gap.
    conn.execute("INSERT INTO sanads VALUES (10, 'إسناده متصل ، رجاله ثقات', 1)")
    conn.execute("INSERT INTO sanads VALUES (11, 'إسناد حسن', 1)")
    conn.execute("INSERT INTO sanads VALUES (12, 'إسناد ضعيف', 1)")
    conn.execute("INSERT INTO sanads VALUES (13, 'إسناد ضعيف لأن به موضع إرسال', 1)")
    conn.execute("INSERT INTO sanad_rawis VALUES (10, 0, 2), (10, 1, 1)")
    conn.execute("INSERT INTO sanad_rawis VALUES (11, 0, 1), (11, 1, 2)")
    conn.execute("INSERT INTO sanad_rawis VALUES (12, 0, 3), (12, 1, 1)")
    conn.execute("INSERT INTO sanad_rawis VALUES (13, 0, 2), (13, 1, 4), (13, 2, 1)")
    conn.commit()
    conn.close()


def _read_rows(path):
    rows, header = [], None
    with open(path) as f:
        for line in f:
            if line.startswith("# "):
                header = json.loads(line[2:])
            else:
                rows.append(json.loads(line))
    return header, rows


def test_export_header_carries_reproducibility(tmp_path):
    db = tmp_path / "t.db"
    _make_db(str(db))
    out = tmp_path / "e.jsonl"
    export(str(db), str(out), sample=None, seed=0, lenient=False)
    header, rows = _read_rows(out)
    assert header["dataset"] == "isnad-bench"
    assert header["derived_from"] == "emadjumaah/hadith-kg (CC-BY-4.0)"
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
    assert len(rows) == 4


def test_export_rows_match_schema_and_truth(tmp_path):
    db = tmp_path / "t.db"
    _make_db(str(db))
    out = tmp_path / "e.jsonl"
    export(str(db), str(out), sample=None, seed=0, lenient=False)
    header, rows = _read_rows(out)
    by_id = {r["sanad_id"]: r for r in rows}
    for r in rows:
        assert set(r.keys()) == set(header["schema"])
        assert r["true_grade"] in _CLASSES
        assert r["predicted_grade"] in _CLASSES
    # The gap chain must be flagged incomplete.
    assert by_id[13]["is_complete"] is False
    assert by_id[13]["has_gap"] is True
    # The clean chain is complete.
    assert by_id[10]["is_complete"] is True


def test_export_kappa_matches_recomputed(tmp_path):
    """Exported grades recompute to the same κ as an independent recomputation."""
    db = tmp_path / "t.db"
    _make_db(str(db))
    out = tmp_path / "e.jsonl"
    export(str(db), str(out), sample=None, seed=0, lenient=False)
    _header, rows = _read_rows(out)

    k_export = cohens_kappa(
        confusion_matrix(
            [r["true_grade"] for r in rows], [r["predicted_grade"] for r in rows], _CLASSES
        ),
        _CLASSES,
    )

    ids = {r["sanad_id"] for r in rows}
    yt, yp = [], []
    for chain in iter_chains(str(db), ids):
        true = chain_grade_from_hukum(chain.hukum)
        if true is None:
            continue
        grades, complete, _rn, _tl, _gap = grade_one_chain(chain.nodes)
        if not grades:
            continue
        yt.append(true.value)
        yp.append(chain_grade_from_narrators(grades, complete, False))
    k_indep = cohens_kappa(confusion_matrix(yt, yp, _CLASSES), _CLASSES)

    assert k_export == pytest.approx(k_indep, abs=1e-9)


def test_export_has_no_tokens_in_payload(tmp_path):
    """The export payload must contain no secrets (security gate)."""
    db = tmp_path / "t.db"
    _make_db(str(db))
    out = tmp_path / "e.jsonl"
    export(str(db), str(out), sample=None, seed=0, lenient=False)
    text = out.read_text()
    assert "hf_" not in text
    assert "sk-" not in text


def test_bucket_is_none_on_agreement():
    assert bucket("sahih", "sahih", False, False, [1], None) is None


def test_bucket_labels_sahih_hasan_boundary():
    assert bucket("sahih", "hasan", False, False, [1], None) == "grade: ṣaḥīḥ ↔ ḥasan boundary"


def test_bucket_labels_corroboration():
    b = bucket("daif", "hasan", False, False, [4], "ضعيف ويحسن إذا توبع")
    assert b == "corroboration: weak-alone → ḥasan-with-mutābaʿa"
