"""ISNAD-Bench: load the hadith knowledge graph and yield chains.

Reads ``hadith-kg.db`` (the canonical relational KG from
``emadjumaah/hadith-kg``) and yields each isnād as an ordered list of narrator
nodes. Pure extraction — no grading or mapping here (see ``mapping.py``).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Node:
    """One narrator (or gap sentinel) in a chain."""

    rawi_id: int
    rank_no: int | None
    rank: str | None
    name: str | None


@dataclass(frozen=True)
class RawChain:
    """One isnād: the scholar's verdict plus its ordered narrator nodes."""

    sanad_id: int
    hukum: str | None
    nodes: tuple[Node, ...]


def _load_rawis(conn: sqlite3.Connection) -> dict[int, tuple[int | None, str | None, str | None]]:
    rows = conn.execute("SELECT id, rank_no, rank, name FROM rawis").fetchall()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def iter_chains(
    db_path: str | Path,
    sanad_ids: set[int] | None = None,
) -> Iterator[RawChain]:
    """Yield chains from ``hadith-kg.db``.

    Args:
        db_path: path to ``hadith-kg.db``.
        sanad_ids: restrict to these sanads (``None`` = all, streamed).
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rawis = _load_rawis(conn)

        rows = conn.execute("SELECT id, hukum FROM sanads").fetchall()
        hukum_by_id = {r["id"]: r["hukum"] for r in rows}
        sanad_set = set(hukum_by_id) if sanad_ids is None else set(sanad_ids)

        cur = conn.execute("SELECT sanad_id, pos, rawi_id FROM sanad_rawis ORDER BY sanad_id, pos")
        current_sid: int | None = None
        nodes: list[Node] = []
        for sid, _pos, rid in cur:
            if sid not in sanad_set:
                continue
            if sid != current_sid:
                if current_sid is not None and nodes:
                    yield RawChain(current_sid, hukum_by_id.get(current_sid), tuple(nodes))
                current_sid = sid
                nodes = []
            rank_no, rank, name = rawis.get(rid, (None, None, None))
            nodes.append(Node(rid, rank_no, rank, name))
        if current_sid is not None and nodes:
            yield RawChain(current_sid, hukum_by_id.get(current_sid), tuple(nodes))
    finally:
        conn.close()
