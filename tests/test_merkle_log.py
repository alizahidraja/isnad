"""Tests for the Merkle batch audit log (issue #69).

The linear tamper-evidence chain (chainlog.py) is correct but strictly
sequential: parallel agents race on the previous hash. The Merkle batch log
lets independent leaves be built without a back-reference, then sealed into a
batch whose root commits to the full ordered leaf set. Batches chain by linking
roots (Certificate-Transparency style).

These tests are property-first: the new structure must catch every tamper the
linear chain caught (modify, delete, reorder, first-entry rule), plus support
parallel construction and inclusion proofs. The deletion-detection test is the
gate — a structure that needs an external anchor to catch a dropped leaf has
regressed below the linear chain.
"""

from __future__ import annotations

from isnad.audit.merkle_log import (
    MerkleBatch,
    build_batch,
    prove_inclusion,
    seal_batches,
    verify_batches,
    verify_inclusion,
)


def _leaf(i: int) -> tuple[str, str]:
    """(record_id, record_hash) for a synthetic record."""
    return (f"r{i}", f"h{i}" * 8)  # 64-ish char hex-ish string


class TestBatchRootCommitsToLeaves:
    def test_same_leaves_same_root(self) -> None:
        a = build_batch([_leaf(0), _leaf(1), _leaf(2)])
        b = build_batch([_leaf(0), _leaf(1), _leaf(2)])
        assert a.root == b.root

    def test_modifying_a_leaf_changes_the_root(self) -> None:
        a = build_batch([_leaf(0), _leaf(1), _leaf(2)])
        b = build_batch([_leaf(0), ("r1", "tampered" * 8), _leaf(2)])
        assert a.root != b.root

    def test_reordering_leaves_changes_the_root(self) -> None:
        a = build_batch([_leaf(0), _leaf(1), _leaf(2)])
        b = build_batch([_leaf(2), _leaf(1), _leaf(0)])
        assert a.root != b.root

    def test_dropping_a_leaf_changes_the_root(self) -> None:
        """THE GATE: deletion must be detectable from the root alone.

        The linear chain caught deletion internally (the next entry's prev_hash
        stopped matching). The Merkle root must catch it too — a dropped leaf
        changes the committed leaf set, so the root differs.
        """
        full = build_batch([_leaf(0), _leaf(1), _leaf(2)])
        dropped = build_batch([_leaf(0), _leaf(2)])
        assert full.root != dropped.root

    def test_empty_batch_has_a_defined_root(self) -> None:
        empty = build_batch([])
        assert empty.root is not None
        # An empty batch is distinct from any non-empty one.
        assert empty.root != build_batch([_leaf(0)]).root


class TestBatchChainDetectsTamper:
    """Batches chain by linking roots (CT-style), preserving the linear
    guarantees across batch boundaries."""

    def test_intact_batch_chain_verifies(self) -> None:
        b0 = build_batch([_leaf(0), _leaf(1)])
        b1 = build_batch([_leaf(2), _leaf(3)])
        sealed = seal_batches([b0, b1])
        assert verify_batches(sealed) is None

    def test_modified_batch_root_breaks_chain(self) -> None:
        b0 = build_batch([_leaf(0), _leaf(1)])
        b1 = build_batch([_leaf(2), _leaf(3)])
        sealed = seal_batches([b0, b1])
        # Tamper with a sealed batch's leaves after sealing.
        sealed[1].leaves[0] = ("r2", "tampered" * 8)
        assert verify_batches(sealed) is not None

    def test_reordered_batches_break_chain(self) -> None:
        b0 = build_batch([_leaf(0)])
        b1 = build_batch([_leaf(1)])
        sealed = seal_batches([b0, b1])
        swapped = [sealed[1], sealed[0]]
        assert verify_batches(swapped) is not None

    def test_dropped_batch_breaks_chain(self) -> None:
        b0 = build_batch([_leaf(0)])
        b1 = build_batch([_leaf(1)])
        b2 = build_batch([_leaf(2)])
        sealed = seal_batches([b0, b1, b2])
        without_middle = [sealed[0], sealed[2]]
        assert verify_batches(without_middle) is not None

    def test_first_batch_must_have_null_prev(self) -> None:
        b0 = build_batch([_leaf(0)])
        sealed = seal_batches([b0])
        assert sealed[0].prev_root is None
        assert verify_batches(sealed) is None

    def test_tail_truncation_is_not_detected_known_limit(self) -> None:
        """Known limit (parity with the linear chain): dropping the LAST batch is
        not detectable from the batch list alone.

        Nothing commits to the head/count, so a truncated-tail list is internally
        consistent and verifies clean — exactly like truncating trailing JSONL
        entries passes the linear verify_chain. Detecting truncation needs a
        trusted head or count, which is out of scope here. This test pins the
        limit so it is visible, not hidden.
        """
        sealed = seal_batches([
            build_batch([_leaf(0)]),
            build_batch([_leaf(1)]),
            build_batch([_leaf(2)]),
        ])
        truncated = sealed[:2]  # drop the last batch
        assert verify_batches(truncated) is None  # NOT detected — documented limit


class TestParallelConstruction:
    """The point of #69: leaves are built independently, with no back-reference,
    so parallel agents never race on a shared previous hash."""

    def test_leaves_produced_concurrently_seal_to_a_deterministic_root(self) -> None:
        """The real parallelism claim: N agents produce leaves concurrently, the
        seal step fixes their order once, and the root is deterministic.

        The linear chain cannot do this — each appender must read the previous
        entry's hash first. Here production is lock-free; only the per-batch seal
        is ordered.
        """
        from concurrent.futures import ThreadPoolExecutor

        n = 64
        with ThreadPoolExecutor(max_workers=8) as pool:
            leaves = list(pool.map(_leaf, range(n)))

        # The seal step imposes the canonical order (here, by record_id index).
        ordered = sorted(leaves, key=lambda lf: int(lf[0][1:]))
        root_a = build_batch(ordered).root
        root_b = build_batch(ordered).root
        assert root_a == root_b  # pure function of the ordered leaves
        assert len(build_batch(ordered).leaves) == n

    def test_root_is_pure_function_of_ordered_leaves(self) -> None:
        # Same ordered leaves always give the same root; a different order gives
        # a different root (order is part of the commitment).
        leaves = [_leaf(i) for i in range(8)]
        assert build_batch(leaves).root == build_batch(list(leaves)).root
        assert build_batch(list(reversed(leaves))).root != build_batch(leaves).root


class TestInclusionProofs:
    """Merkle's justification over a flat batch hash: O(log n) inclusion proofs."""

    def test_valid_inclusion_proof_round_trips(self) -> None:
        leaves = [_leaf(i) for i in range(5)]
        batch = build_batch(leaves)
        proof = prove_inclusion(batch, "r3")
        assert proof is not None
        assert verify_inclusion(proof, batch.root) is True

    def test_every_leaf_has_a_valid_proof(self) -> None:
        leaves = [_leaf(i) for i in range(7)]
        batch = build_batch(leaves)
        for rid, _ in leaves:
            proof = prove_inclusion(batch, rid)
            assert proof is not None, rid
            assert verify_inclusion(proof, batch.root) is True, rid

    def test_proof_for_absent_record_is_none(self) -> None:
        batch = build_batch([_leaf(0), _leaf(1)])
        assert prove_inclusion(batch, "not-here") is None

    def test_proof_fails_against_wrong_root(self) -> None:
        batch = build_batch([_leaf(0), _leaf(1), _leaf(2)])
        proof = prove_inclusion(batch, "r1")
        assert proof is not None
        assert verify_inclusion(proof, "wrong" * 8) is False

    def test_tampered_proof_fails(self) -> None:
        batch = build_batch([_leaf(i) for i in range(4)])
        proof = prove_inclusion(batch, "r2")
        assert proof is not None
        # Flip the claimed record hash; the recomputed root must not match.
        bad = proof.__class__(
            record_id=proof.record_id,
            record_hash="tampered" * 8,
            audit_path=proof.audit_path,
            leaf_index=proof.leaf_index,
        )
        assert verify_inclusion(bad, batch.root) is False


class TestMerkleBatchDataclass:
    def test_batch_exposes_root_and_leaves(self) -> None:
        batch = build_batch([_leaf(0), _leaf(1)])
        assert isinstance(batch, MerkleBatch)
        assert isinstance(batch.root, str)
        assert len(batch.leaves) == 2
