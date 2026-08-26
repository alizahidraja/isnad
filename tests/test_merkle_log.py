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
    read_batch_log,
    record_to_leaf,
    seal_batches,
    verify_batches,
    verify_inclusion,
    write_batch_log,
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


class TestRecordToLeaf:
    """Wiring: an AuditRecord becomes a leaf via its own integrity hash."""

    def test_record_becomes_a_leaf(self) -> None:
        from isnad.audit.schema import Integrity

        class _Rec:
            record_id = "rec-1"
            integrity = Integrity(record_hash="abc123" * 8)

        assert record_to_leaf(_Rec()) == ("rec-1", "abc123" * 8)

    def test_real_audit_record_seals_and_verifies(self) -> None:
        """A real built AuditRecord → leaf → batch → verifies (production path)."""
        import tempfile
        from pathlib import Path

        from sqlalchemy.orm import Session

        from isnad.audit import build_audit_record
        from isnad.core.chain import Chain, ChainLinkSpec, store_claim
        from isnad.core.registry import RegistryDB
        from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine
        from isnad.types import NarratorGrade, NarratorType

        with tempfile.TemporaryDirectory() as d:
            url = f"sqlite:///{Path(d) / 'r.db'}"
            reset_engine()
            init_db(url)
            engine = create_engine_from_url(url)
            with Session(engine) as s:
                rdb = RegistryDB(session=s)
                rdb.registry.register(
                    "src",
                    "physics",
                    narrator_type=NarratorType.SOURCE,
                    grade=NarratorGrade.RELIABLE,
                )
                chain = Chain([ChainLinkSpec("src", 0, domain="physics")])
                claim = store_claim(s, "E=mc^2", "physics/rel", chain, chain_grade="sahih")
                s.commit()
                rec = build_audit_record(claim.claim_id, s, rdb.registry)
            reset_engine()

        batch = build_batch([record_to_leaf(rec)])
        proof = prove_inclusion(batch, rec.record_id)
        assert proof is not None
        assert verify_inclusion(proof, batch.root) is True


class TestBatchLogPersistence:
    """On-disk batch log: round-trips, and disk tampering is detected."""

    def test_write_read_round_trip_verifies(self, tmp_path) -> None:
        sealed = seal_batches([build_batch([_leaf(0), _leaf(1)]), build_batch([_leaf(2)])])
        log = tmp_path / "batches.jsonl"
        write_batch_log(log, sealed)
        loaded = read_batch_log(log)
        assert verify_batches(loaded) is None
        assert [b.leaves for b in loaded] == [b.leaves for b in sealed]

    def test_empty_log_reads_empty(self, tmp_path) -> None:
        assert read_batch_log(tmp_path / "nonexistent.jsonl") == []

    def test_on_disk_leaf_tamper_is_detected(self, tmp_path) -> None:
        """THE GATE: mutate a byte on disk → reload → verify catches it.

        Round-trip equality only proves serialization. The property that matters
        is that tampering with the file is detected, so we mutate the persisted
        bytes and assert verify_batches reports a break.
        """
        sealed = seal_batches([build_batch([_leaf(0), _leaf(1)])])
        log = tmp_path / "batches.jsonl"
        write_batch_log(log, sealed)

        raw = log.read_text()
        assert "h0h0" in raw  # part of leaf 0's record_hash
        log.write_text(raw.replace("h0h0", "XXXX", 1))  # flip a leaf byte on disk

        loaded = read_batch_log(log)
        assert verify_batches(loaded) is not None  # recomputed root != stored root

    def test_on_disk_batch_drop_is_detected(self, tmp_path) -> None:
        """Delete a (non-tail) batch line on disk → the prev_root link breaks."""
        sealed = seal_batches([
            build_batch([_leaf(0)]),
            build_batch([_leaf(1)]),
            build_batch([_leaf(2)]),
        ])
        log = tmp_path / "batches.jsonl"
        write_batch_log(log, sealed)

        lines = log.read_text().splitlines()
        del lines[1]  # drop the middle batch
        log.write_text("\n".join(lines) + "\n")

        loaded = read_batch_log(log)
        assert verify_batches(loaded) is not None


class TestVerifyMerkleCLI:
    """The wiring's real entry point: `isnad verify-merkle --log PATH`."""

    def _run(self, argv: list[str]) -> int:
        import pytest

        from isnad.cli.main import main

        with pytest.raises(SystemExit) as exc:
            main(argv)
        return exc.value.code if isinstance(exc.value.code, int) else 1

    def test_cli_intact_log_exits_zero(self, tmp_path, capsys) -> None:
        log = tmp_path / "batches.jsonl"
        write_batch_log(log, seal_batches([build_batch([_leaf(0), _leaf(1)])]))
        code = self._run(["verify-merkle", "--log", str(log)])
        assert code == 0
        assert "intact" in capsys.readouterr().out

    def test_cli_tampered_log_exits_one(self, tmp_path, capsys) -> None:
        log = tmp_path / "batches.jsonl"
        write_batch_log(log, seal_batches([build_batch([_leaf(0), _leaf(1)])]))
        raw = log.read_text()
        log.write_text(raw.replace("h0h0", "XXXX", 1))
        code = self._run(["verify-merkle", "--log", str(log)])
        assert code == 1
        assert "broken" in capsys.readouterr().out


class TestMalformedLogsDoNotCrash:
    """Issue #108: a corrupted/partial log reports 'broken', never a traceback.

    A tamper-evidence verifier must survive exactly the corrupted input it exists
    to detect. read_batch_log raises a structured MalformedLogError; the CLI and
    verify path turn that into exit 1 with a readable message.
    """

    def _run(self, argv: list[str]) -> int:
        import pytest

        from isnad.cli.main import main

        with pytest.raises(SystemExit) as exc:
            main(argv)
        return exc.value.code if isinstance(exc.value.code, int) else 1

    # Every corruption flavor the RCA found — incl. the ValueError cases the
    # issue's JSONDecodeError/KeyError/TypeError list missed.
    _CORRUPTIONS = {
        "invalid_json": "{not valid json\n",
        "truncated_line": '{"leaves":[["r","h"]],"roo',
        "missing_key": '{"root":"x"}\n',
        "leaves_not_iterable": '{"leaves":5,"root":"x"}\n',
        "leaf_not_a_pair": '{"leaves":[[1]],"root":"x"}\n',
    }

    def test_read_batch_log_raises_structured_error(self, tmp_path) -> None:
        import pytest

        from isnad.audit import MalformedLogError, read_batch_log

        for name, content in self._CORRUPTIONS.items():
            log = tmp_path / f"{name}.jsonl"
            log.write_text(content)
            with pytest.raises(MalformedLogError) as exc:
                read_batch_log(log)
            assert exc.value.index == 0, name  # first (0th) non-blank line

    def test_cli_verify_merkle_reports_malformed_not_crash(self, tmp_path, capsys) -> None:
        for name, content in self._CORRUPTIONS.items():
            log = tmp_path / f"{name}.jsonl"
            log.write_text(content)
            code = self._run(["verify-merkle", "--log", str(log)])
            assert code == 1, name
            assert "malformed" in capsys.readouterr().out, name

    def test_malformed_line_index_points_at_the_bad_line(self, tmp_path) -> None:
        import pytest

        from isnad.audit import MalformedLogError, read_batch_log

        # One good batch, then a corrupt line → the error names index 1.
        good = seal_batches([build_batch([_leaf(0)])])
        write_batch_log(tmp_path / "m.jsonl", good)
        log = tmp_path / "m.jsonl"
        log.write_text(log.read_text() + "{garbage\n")
        with pytest.raises(MalformedLogError) as exc:
            read_batch_log(log)
        assert exc.value.index == 1
