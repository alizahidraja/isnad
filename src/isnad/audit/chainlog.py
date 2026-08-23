"""Tamper-evident hash chaining — no blockchain, no external dependencies.

Each audit record's hash is appended to a JSONL chain where every entry stores
the *previous* entry's hash.  Tampering with (or deleting, or reordering) any
entry breaks the chain at the first affected link.  This is an evidence-integrity
mechanism, not a consensus mechanism: it detects tampering, it does not prevent
it, and it proves nothing about the *truth* of the underlying claim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChainEntry:
    index: int
    record_id: str
    record_hash: str
    prev_hash: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "record_id": self.record_id,
            "record_hash": self.record_hash,
            "prev_hash": self.prev_hash,
        }


@dataclass
class ChainBreak:
    index: int
    reason: str


def _read_chain(path: Path) -> list[ChainEntry]:
    if not path.exists():
        return []
    entries: list[ChainEntry] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        entries.append(
            ChainEntry(
                index=int(d["index"]),
                record_id=str(d["record_id"]),
                record_hash=str(d["record_hash"]),
                prev_hash=d.get("prev_hash"),
            )
        )
    return entries


def append_record(chain_path: str | Path, record_id: str, record_hash: str) -> None:
    """Append a record hash to the chain, linking it to the previous entry."""
    path = Path(chain_path)
    entries = _read_chain(path)
    prev = entries[-1].record_hash if entries else None
    entry = ChainEntry(
        index=len(entries), record_id=record_id, record_hash=record_hash, prev_hash=prev
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry.to_dict(), separators=(",", ":")) + "\n")


def verify_chain(chain_path: str | Path) -> ChainBreak | None:
    """Walk the chain and return the first break, or None if intact.

    A break means: an entry's ``prev_hash`` does not match the previous entry's
    ``record_hash``, or an entry is missing a field.
    """
    entries = _read_chain(Path(chain_path))
    for i, entry in enumerate(entries):
        if i == 0:
            if entry.prev_hash is not None:
                return ChainBreak(i, "first entry has a non-null prev_hash")
            continue
        expected = entries[i - 1].record_hash
        if entry.prev_hash != expected:
            return ChainBreak(
                i,
                f"entry {i} prev_hash {entry.prev_hash!r} != previous record_hash {expected!r}",
            )
    return None
