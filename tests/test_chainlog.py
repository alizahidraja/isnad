"""Tests for the linear hash-chain log (atomic append under lock)."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

from isnad.audit.chainlog import _read_chain, append_record, verify_chain


def test_concurrent_appends_do_not_lose_entries(tmp_path):
    """Concurrent appenders must not interleave or lose entries."""
    path = tmp_path / "chain.jsonl"
    n = 40

    def add(i: int) -> None:
        append_record(path, f"r{i}", f"h{i}" * 8)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(add, range(n)))

    assert verify_chain(path) is None

    entries = _read_chain(Path(path))
    assert len(entries) == n
    assert [e.index for e in entries] == list(range(n))
    assert len({e.record_id for e in entries}) == n
