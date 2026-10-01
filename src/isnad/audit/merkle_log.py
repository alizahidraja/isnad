"""Merkle batch audit log — parallel-friendly tamper-evidence (issue #69).

The linear chain in ``chainlog.py`` is correct but strictly sequential: every
appender links its entry to the *previous* entry's hash, so parallel agents
race on that shared "previous hash". This module is the mergeable alternative.

**Shape (Certificate-Transparency style).** Records enter as independent
*leaves* — a leaf carries no back-reference, so any number of agents can produce
leaves concurrently without coordination. A *seal* step then fixes the leaves in
order and builds a Merkle tree whose ``root`` commits to the full, ordered leaf
set. Batches chain by linking roots (``prev_root``), giving the same
modify/delete/reorder detection the linear chain had, across batch boundaries.

**Scaling optimization, not a correctness fix.** The linear chain is correct at
current scale; this is for mass parallel agent batches. The transmission lineage
is already a DAG (``audit/schema.py``'s ``upstream_ids``); only the
tamper-evidence chain was linear, and only that is addressed here.

**Scope.** This is the in-memory structure (build / seal / verify / prove). It is
not yet wired into the audit-record flow and has no on-disk format — converting
an ``AuditRecord`` to a leaf, persistence, and a CLI verify path are follow-ups,
kept out to keep the change reviewable. ``chainlog.py`` is untouched.

**Limit — tail truncation.** ``verify_batches`` confirms the *internal*
consistency of the batch list it is given; it cannot detect that trailing
batches were dropped, because nothing commits to the head or the count. This is
parity with the linear chain (truncating trailing JSONL entries also passes
``verify_chain``). Detecting truncation needs a trusted head/count, which is out
of scope here.

Stdlib only (``hashlib`` via ``audit/canonical.py``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from isnad.audit._lock import exclusive_lock
from isnad.audit.canonical import MalformedLogError, sha256_hex

if TYPE_CHECKING:
    from isnad.audit.schema import AuditRecord

# Domain-separation prefixes keep leaf hashes, internal-node hashes, and the
# empty-tree sentinel in disjoint spaces (guards against second-preimage tricks
# that swap a leaf for an internal node — RFC 6962 §2.1).
_LEAF_PREFIX = "isnad-merkle-leaf:"
_NODE_PREFIX = "isnad-merkle-node:"
_EMPTY = sha256_hex("isnad-merkle-empty")


def _leaf_hash(record_id: str, record_hash: str) -> str:
    """Hash a single leaf, binding record_id to record_hash."""
    return sha256_hex(f"{_LEAF_PREFIX}{record_id}\x00{record_hash}")


def _node_hash(left: str, right: str) -> str:
    """Hash an internal node from its two child hashes."""
    return sha256_hex(f"{_NODE_PREFIX}{left}\x00{right}")


def _merkle_root(leaf_hashes: list[str]) -> str:
    """Compute the Merkle root of an ordered list of leaf hashes.

    An empty list hashes to the ``_EMPTY`` sentinel. A lone node at any level is
    *promoted* unchanged (not duplicated), which avoids the duplicate-sibling
    ambiguity (CVE-2012-2459) while keeping the root a pure function of the
    ordered leaves.
    """
    if not leaf_hashes:
        return _EMPTY
    level = list(leaf_hashes)
    while len(level) > 1:
        nxt: list[str] = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(_node_hash(level[i], level[i + 1]))
            else:
                nxt.append(level[i])  # promote the odd node unchanged
        level = nxt
    return level[0]


@dataclass
class MerkleBatch:
    """A sealed batch: an ordered leaf set plus its committed Merkle root.

    ``leaves`` is the ordered list of ``(record_id, record_hash)`` pairs.
    ``root`` is recomputed from ``leaves`` on demand by verification, so
    tampering with ``leaves`` after sealing is detectable. ``prev_root`` links
    this batch to the previous one in a batch chain (None for the first batch).
    """

    leaves: list[tuple[str, str]]
    root: str
    prev_root: str | None = None


def build_batch(leaves: list[tuple[str, str]]) -> MerkleBatch:
    """Build an unsealed batch (no ``prev_root`` yet) from ordered leaves.

    ``leaves`` is a list of ``(record_id, record_hash)``. The order is part of
    the commitment; the caller (the seal step) fixes it. Leaves themselves carry
    no back-reference, so they can be produced in parallel and ordered here.
    """
    leaf_hashes = [_leaf_hash(rid, rhash) for rid, rhash in leaves]
    return MerkleBatch(leaves=list(leaves), root=_merkle_root(leaf_hashes))


def seal_batches(batches: list[MerkleBatch]) -> list[MerkleBatch]:
    """Link a sequence of batches into a chain by setting each ``prev_root``.

    Returns new ``MerkleBatch`` objects (roots recomputed from leaves) whose
    ``prev_root`` points at the previous batch's root. The first batch has
    ``prev_root=None``. This is the only sequential step, and it happens once per
    batch — not once per record — so parallel agents never contend on it.
    """
    sealed: list[MerkleBatch] = []
    prev: str | None = None
    for b in batches:
        root = _merkle_root([_leaf_hash(rid, rhash) for rid, rhash in b.leaves])
        sealed.append(MerkleBatch(leaves=list(b.leaves), root=root, prev_root=prev))
        prev = root
    return sealed


@dataclass
class BatchBreak:
    """A detected break in a sealed batch chain."""

    index: int
    reason: str


def verify_batches(batches: list[MerkleBatch]) -> BatchBreak | None:
    """Verify a sealed batch chain; return the first break, or None if intact.

    Catches the same tamper classes as the linear chain, at batch granularity:
    - **modification** — a batch's ``root`` no longer matches its leaves;
    - **deletion / reordering** — a batch's ``prev_root`` no longer matches the
      previous batch's recomputed root (so a dropped or swapped batch breaks the
      link);
    - the first batch must have ``prev_root=None``.
    """
    prev: str | None = None
    for i, b in enumerate(batches):
        recomputed = _merkle_root([_leaf_hash(rid, rhash) for rid, rhash in b.leaves])
        if recomputed != b.root:
            return BatchBreak(i, f"batch {i} root {b.root!r} != recomputed {recomputed!r}")
        if i == 0:
            if b.prev_root is not None:
                return BatchBreak(i, "first batch has a non-null prev_root")
        elif b.prev_root != prev:
            return BatchBreak(i, f"batch {i} prev_root {b.prev_root!r} != previous root {prev!r}")
        prev = b.root
    return None


@dataclass
class InclusionProof:
    """An O(log n) proof that ``record_id`` is in a batch with a given root.

    ``audit_path`` is the ordered list of sibling hashes from leaf to root, each
    tagged with whether the sibling sits on the ``"left"`` or ``"right"``.
    ``verify_inclusion`` recomputes the root from the leaf and this path.
    """

    record_id: str
    record_hash: str
    audit_path: list[tuple[str, str]]  # (sibling_hash, "left" | "right")
    leaf_index: int


def prove_inclusion(batch: MerkleBatch, record_id: str) -> InclusionProof | None:
    """Build an inclusion proof for ``record_id``, or None if it is absent.

    If ``record_id`` appears more than once, the first occurrence is proven.
    """
    index = next((i for i, (rid, _) in enumerate(batch.leaves) if rid == record_id), None)
    if index is None:
        return None
    record_hash = batch.leaves[index][1]

    level = [_leaf_hash(rid, rh) for rid, rh in batch.leaves]
    idx = index
    path: list[tuple[str, str]] = []
    while len(level) > 1:
        nxt: list[str] = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                if i == idx:  # our node is the left child; sibling is on the right
                    path.append((level[i + 1], "right"))
                elif i + 1 == idx:  # our node is the right child; sibling on the left
                    path.append((level[i], "left"))
                nxt.append(_node_hash(level[i], level[i + 1]))
            else:
                nxt.append(level[i])  # promoted odd node — no sibling recorded
        idx //= 2
        level = nxt
    return InclusionProof(
        record_id=record_id,
        record_hash=record_hash,
        audit_path=path,
        leaf_index=index,
    )


def verify_inclusion(proof: InclusionProof, root: str) -> bool:
    """Recompute the root from ``proof`` and check it equals ``root``."""
    node = _leaf_hash(proof.record_id, proof.record_hash)
    for sibling, side in proof.audit_path:
        node = _node_hash(sibling, node) if side == "left" else _node_hash(node, sibling)
    return node == root


# ---------------------------------------------------------------------------
# Wiring: AuditRecord → leaf, and on-disk persistence of sealed batches
# ---------------------------------------------------------------------------


def record_to_leaf(record: AuditRecord) -> tuple[str, str]:
    """Turn an ``AuditRecord`` into a Merkle leaf ``(record_id, record_hash)``.

    Uses the record's own self-integrity hash (``integrity.record_hash``), so a
    leaf commits to the exact record the audit layer already hashes — no new
    hash surface. Callers build leaves independently (one per graded claim),
    then hand an ordered list to ``build_batch``/``seal_batches``.

    Honest limit (#97): ``integrity.record_hash`` is a *self*-hash, so the log
    proves **log-integrity** (these records, in this order, unaltered), not
    **authorship** — anyone who can rewrite a record can also produce a matching
    leaf. Anchoring authorship (e.g. a signature) is tracked separately in #97.
    """
    return (record.record_id, record.integrity.record_hash)


def write_batch_log(path: str | Path, batches: list[MerkleBatch]) -> None:
    """Persist sealed batches to a JSONL batch log, one JSON object per batch.

    Written **once per seal**, not once per record: the batch log has a single
    writer by construction (the seal step is already the one sequential point),
    so this persistence layer does not reintroduce the concurrent-append
    contention the batch model exists to avoid. Leaves are produced in parallel
    and stay caller-side; only sealed batches are persisted.

    Overwrites ``path`` with the full ordered batch list (append a new batch by
    passing the extended list). Each line is ``{leaves, root, prev_root}``.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for b in batches:
        obj = {
            "leaves": [[rid, rhash] for rid, rhash in b.leaves],
            "root": b.root,
            "prev_root": b.prev_root,
        }
        lines.append(json.dumps(obj, separators=(",", ":")))
    p.write_text("\n".join(lines) + ("\n" if lines else ""))


def read_batch_log(path: str | Path) -> list[MerkleBatch]:
    """Read a batch log back into ``MerkleBatch`` objects (empty if absent).

    ``root``/``prev_root`` are read as stored; ``verify_batches`` recomputes the
    root from ``leaves`` so a tampered stored ``root`` (or tampered leaves) is
    detected rather than trusted.
    """
    p = Path(path)
    if not p.exists():
        return []
    batches: list[MerkleBatch] = []
    for n, line in enumerate(p.read_text().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MalformedLogError(n, f"invalid JSON ({exc.msg})") from exc
        if not isinstance(d, dict):
            raise MalformedLogError(n, f"not a JSON object (got {type(d).__name__})")
        try:
            leaves = [(str(rid), str(rhash)) for rid, rhash in d["leaves"]]
            root = str(d["root"])
            prev_root = d.get("prev_root")
        except KeyError as exc:
            raise MalformedLogError(n, f"missing key {exc.args[0]!r}") from exc
        except (TypeError, ValueError) as exc:
            raise MalformedLogError(n, f"malformed value: {exc}") from exc
        batches.append(MerkleBatch(leaves=leaves, root=root, prev_root=prev_root))
    return batches


@dataclass
class MerkleAnchor:
    """The persisted head/count of a Merkle batch log.

    This is the trust anchor: an external process (RFC 3161 timestamp service,
    a pinned/published head) commits to ``(head, count, batches)`` so that
    dropping trailing batches is detectable, not just silently consistent.
    """

    head: str | None  # root of the last sealed batch (None when empty)
    count: int  # total records sealed across all batches
    batches: int  # number of sealed batches


class MerkleLog:
    """Persistent, append-only Merkle batch log with an anchored head/count.

    Agents append ``(record_id, record_hash)`` leaves concurrently; ``seal()``
    (or reaching ``batch_size``) links them into a batch chain, persists the
    batch, and advances a sidecar anchor ``{head, count, batches}``. ``verify()``
    recomputes every root and link and fail-closes when the on-disk batch count
    is lower than the anchored count (tail truncation) — the gap
    ``verify_batches`` alone cannot see, because nothing committed to the head.
    """

    def __init__(self, path: str | Path, batch_size: int = 1000) -> None:
        self.path = Path(path)
        self.batch_size = batch_size
        self._open: list[tuple[str, str]] = []
        self._last_root: str | None = None
        self._batches_sealed = 0
        self._count = 0
        self._load()

    @property
    def anchor_path(self) -> Path:
        return self.path.with_name(self.path.name + ".anchor.json")

    def _load(self) -> None:
        a = self.anchor_path
        if not a.exists():
            return
        try:
            data = json.loads(a.read_text())
            self._last_root = data.get("head")
            self._count = int(data.get("count", 0))
            self._batches_sealed = int(data.get("batches", 0))
        except (json.JSONDecodeError, ValueError):
            # A corrupt anchor is a break; surfaced by verify() against on-disk
            # batches. Keep zeroed here so append still works.
            return

    def _save_anchor(self) -> None:
        obj = {"head": self._last_root, "count": self._count, "batches": self._batches_sealed}
        self.anchor_path.write_text(json.dumps(obj, separators=(",", ":")))

    def append(self, record_id: str, record_hash: str) -> None:
        """Add a leaf; auto-seal when the open batch reaches ``batch_size``."""
        self._open.append((record_id, record_hash))
        if len(self._open) >= self.batch_size:
            self._seal_open()

    def seal(self) -> tuple[str, int]:
        """Seal the open batch and return ``(head, count)`` — the trust anchor."""
        self._seal_open()
        return (self._last_root or "", self._count)

    def head(self) -> str | None:
        """Root of the last sealed batch (None when nothing sealed yet)."""
        return self._last_root

    def count(self) -> int:
        """Total records sealed (the count the anchor commits to)."""
        return self._count

    def _seal_open(self) -> None:
        if not self._open:
            return
        batch = build_batch(self._open)
        sealed = MerkleBatch(leaves=batch.leaves, root=batch.root, prev_root=self._last_root)
        self._append_batch_line(sealed)
        self._last_root = sealed.root
        self._batches_sealed += 1
        self._count += len(self._open)
        self._open = []
        self._save_anchor()

    def _append_batch_line(self, batch: MerkleBatch) -> None:
        obj = {
            "leaves": [[rid, rhash] for rid, rhash in batch.leaves],
            "root": batch.root,
            "prev_root": batch.prev_root,
        }
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with exclusive_lock(self.path), self.path.open("a") as f:
            f.write(line)

    def verify(self) -> BatchBreak | None:
        """Verify the persisted batch chain against its anchor, fail-closed.

        Detects (a) a batch root no longer matching its leaves, (b) a broken
        prev_root link, and (c) tail truncation — the on-disk batch count being
        lower than the anchored count.
        """
        batches = read_batch_log(self.path)
        expected_batches = self._batches_sealed
        if len(batches) != expected_batches:
            return BatchBreak(
                len(batches),
                f"tail truncation: {len(batches)} batches on disk vs {expected_batches} anchored",
            )
        brk = verify_batches(batches)
        if brk is not None:
            return brk
        if expected_batches > 0 and batches[-1].root != self._last_root:
            return BatchBreak(len(batches) - 1, f"head mismatch: anchor {self._last_root!r}")
        return None
