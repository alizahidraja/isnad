"""Tests for the reproducible-benchmark hash verification (#205)."""

import hashlib

import pytest

from bench.run import PINNED_DB_SHA256, hash_file, verify_db_hash


def test_pinned_db_sha_is_64_hex():
    assert len(PINNED_DB_SHA256) == 64
    assert all(c in "0123456789abcdef" for c in PINNED_DB_SHA256)


def test_hash_file_matches_stdlib(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello isnad\n" * 1000)
    assert hash_file(p) == hashlib.sha256(p.read_bytes()).hexdigest()


def test_verify_db_hash_raises_on_mismatch(tmp_path):
    p = tmp_path / "wrong.db"
    p.write_bytes(b"not the real hadith-kg.db")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_db_hash(p)


def test_verify_db_hash_accepts_matching_hash(tmp_path, monkeypatch):
    p = tmp_path / "ok.bin"
    p.write_bytes(b"hello")
    expected = hashlib.sha256(b"hello").hexdigest()
    monkeypatch.setattr("bench.run.PINNED_DB_SHA256", expected)
    assert verify_db_hash(p) == expected
