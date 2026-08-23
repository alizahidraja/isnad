"""Tests for bench.data — chain loading and sentinel handling (tiny SQLite)."""

from __future__ import annotations

import sqlite3

from bench.data import iter_chains


def _make_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE rawis (id INTEGER, rank_no INTEGER, rank TEXT, name TEXT);
        CREATE TABLE sanads (id INTEGER, hukum TEXT, group_id INTEGER);
        CREATE TABLE sanad_rawis (sanad_id INTEGER, pos INTEGER, rawi_id INTEGER);
        """
    )
    conn.execute("INSERT INTO rawis VALUES (1, 1, 'صحابي', 'عائشة')")
    conn.execute("INSERT INTO rawis VALUES (2, 3, 'ثقة', 'الزهري')")
    conn.execute("INSERT INTO rawis VALUES (3, 8, 'ضعيف الحديث', 'فلان')")
    conn.execute("INSERT INTO rawis VALUES (4, 12, NULL, 'موضع إرسال')")
    conn.execute("INSERT INTO sanads VALUES (10, 'إسناده متصل ، رجاله ثقات', 1)")
    conn.execute("INSERT INTO sanads VALUES (20, 'إسناد ضعيف لأن به موضع إرسال', 1)")
    conn.execute("INSERT INTO sanad_rawis VALUES (10, 0, 2), (10, 1, 1)")
    conn.execute("INSERT INTO sanad_rawis VALUES (20, 0, 2), (20, 1, 4), (20, 2, 1)")
    conn.commit()
    conn.close()


def test_iter_chains_builds_ordered_chains(tmp_path):
    p = tmp_path / "test.db"
    _make_db(str(p))
    chains = list(iter_chains(p))
    assert len(chains) == 2
    by_id = {c.sanad_id: c for c in chains}

    c10 = by_id[10]
    assert [n.rawi_id for n in c10.nodes] == [2, 1]
    assert c10.hukum == "إسناده متصل ، رجاله ثقات"

    c20 = by_id[20]
    assert [n.name for n in c20.nodes] == ["الزهري", "موضع إرسال", "عائشة"]
    # the sentinel node carries rank_no=12 with no grade label
    assert c20.nodes[1].rank_no == 12
    assert c20.nodes[1].rank is None


def test_iter_chains_filters_by_sanad_ids(tmp_path):
    p = tmp_path / "test.db"
    _make_db(str(p))
    chains = list(iter_chains(p, sanad_ids={10}))
    assert [c.sanad_id for c in chains] == [10]
