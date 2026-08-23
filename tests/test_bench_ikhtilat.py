"""Tests for bench.ikhtilat — the ikhtilāṭ data loader."""

from __future__ import annotations

import sqlite3

from bench.ikhtilat import _load_ikhtilat


def _make_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE rawis (id INTEGER, rank_no INTEGER, rank TEXT, name TEXT, has_ikhtilat INTEGER)"
    )
    conn.execute("INSERT INTO rawis VALUES (1, 3, 'ثقة', 'clean', 0)")
    conn.execute("INSERT INTO rawis VALUES (2, 3, 'ثقة اختلط قبل موته', 'declined-1', 1)")
    conn.execute("INSERT INTO rawis VALUES (3, 4, 'صدوق تغير بآخره', 'declined-2', 1)")
    conn.execute("INSERT INTO rawis VALUES (4, 3, 'ثقة', 'flag-only', 1)")
    conn.commit()
    conn.close()


def test_load_ikhtilat_returns_ids_and_decline_texts(tmp_path):
    p = tmp_path / "t.db"
    _make_db(str(p))
    ids, texts = _load_ikhtilat(str(p))
    assert ids == {2, 3, 4}
    assert set(texts) == {"ثقة اختلط قبل موته", "صدوق تغير بآخره"}
