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

from dataclasses import dataclass

from isnad.audit.canonical import sha256_hex

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
