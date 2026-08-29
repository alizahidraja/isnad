"""Tests for the ISNAD CLI (serve/seed dispatcher + seed logic)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from isnad.cli import main as cli_main


class TestMainDispatcher:
    def test_no_args_prints_usage_and_exits(self, capsys):
        with pytest.raises(SystemExit) as e:
            cli_main.main([])
        assert e.value.code == 1
        assert (
            "Usage: isnad [serve|seed|export|verify|verify-chain|verify-merkle|ingest|bench]"
            in capsys.readouterr().out
        )

    def test_unknown_command_exits_1(self, capsys):
        with pytest.raises(SystemExit) as e:
            cli_main.main(["frobnicate"])
        assert e.value.code == 1
        assert "Unknown command: frobnicate" in capsys.readouterr().out

    def test_serve_is_reachable(self, monkeypatch, capsys):
        """serve() should not be import-able-error when dispatched; we just
        assert the dispatcher routes to it without running uvicorn."""
        called = {}

        def fake_serve():
            called["serve"] = True

        monkeypatch.setattr(cli_main, "serve", fake_serve)
        cli_main.main(["serve"])
        assert called.get("serve") is True


class TestSeed:
    def test_seed_empty_config_exits_1(self, monkeypatch, capsys):
        monkeypatch.setenv("ISNAD_SEED_CONFIG", "[]")
        with pytest.raises(SystemExit) as e:
            cli_main.seed()
        assert e.value.code == 1
        assert "ISNAD_SEED_CONFIG is empty" in capsys.readouterr().out

    def test_seed_registers_narrators(self, monkeypatch, tmp_path, capsys):
        """Seed writes narrators into a fresh DB and reports the count."""
        db_path = tmp_path / "cli_seed.db"
        monkeypatch.setenv("ISNAD_DATABASE_URL", f"sqlite:///{db_path}")
        monkeypatch.setenv(
            "ISNAD_SEED_CONFIG",
            json.dumps([
                {"narrator_id": "src:openstax", "domain": "physics", "grade": "reliable"},
                {"narrator_id": "model:gpt-4o", "domain": "physics", "grade": "acceptable"},
            ]),
        )

        # Reset any cached engine so the new URL takes effect.
        from isnad.storage import sqlalchemy as storage

        storage.reset_engine()

        cli_main.seed()

        out = capsys.readouterr().out
        assert "Seeded 2 narrators" in out

        # Verify the grades actually landed.
        from isnad.storage.sqlalchemy import get_session
        from isnad.core.registry import RegistryDB
        from isnad.types import NarratorGrade

        with get_session() as session:
            reg = RegistryDB(session=session)
            reg.load()
            assert reg.registry.get_grade("src:openstax", "physics") == NarratorGrade.RELIABLE
            assert reg.registry.get_grade("model:gpt-4o", "physics") == NarratorGrade.ACCEPTABLE


class TestVerifyDetachedSignature:
    """`isnad verify` checks the detached signature, not just the self-hash (#97)."""

    def _write_signed_record(self, tmp_path: Path, secret: str, tamper: bool = False) -> Path:
        from isnad.audit import hmac_signer, sign_detached
        from isnad.audit.canonical import canonical_hash
        from isnad.audit.schema import (
            RECORD_VERSION,
            AuditRecord,
            ChainNodeAudit,
            Environment,
            GradingStrategy,
            SourceDocument,
            WeakestLink,
            new_record_id,
            utcnow_iso,
        )

        rec = AuditRecord(
            record_id=new_record_id(),
            record_version=RECORD_VERSION,
            generated_at=utcnow_iso(),
            claim_id="c1",
            claim_text="p = mv",
            final_grade="hasan",
            grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
            chain=[ChainNodeAudit("src", "dataset", "reliable", "r")],
            weakest_link=WeakestLink("src", "reliable", "lowest grade"),
            source_documents=[SourceDocument("https://e/x")],
            human_oversight=[],
            environment=Environment("2.10.1", "3.12", "darwin"),
        )
        # The real exporter sets the self-hash before signing (see
        # audit/exporter.py); mirror that so verify sees a stored hash.
        rec.integrity.record_hash = canonical_hash(rec.to_dict(include_integrity=False))
        sign_detached(rec, hmac_signer(secret))
        if tamper:
            rec.claim_text = "tampered"
        path = tmp_path / "record.json"
        path.write_text(json.dumps(rec.to_dict()))
        return path

    def test_verify_with_correct_secret_passes(self, tmp_path, monkeypatch, capsys):
        path = self._write_signed_record(tmp_path, "s3cret")
        monkeypatch.delenv("ISNAD_SIGNING_SECRET", raising=False)
        code = cli_main._verify(["--record", str(path), "--hmac-secret", "s3cret"])
        assert code == 0
        assert "detached signature verified" in capsys.readouterr().out

    def test_verify_with_wrong_secret_fails(self, tmp_path, monkeypatch):
        path = self._write_signed_record(tmp_path, "s3cret")
        monkeypatch.delenv("ISNAD_SIGNING_SECRET", raising=False)
        code = cli_main._verify(["--record", str(path), "--hmac-secret", "other"])
        assert code == 1

    def test_verify_tampered_record_fails(self, tmp_path, monkeypatch):
        path = self._write_signed_record(tmp_path, "s3cret", tamper=True)
        monkeypatch.delenv("ISNAD_SIGNING_SECRET", raising=False)
        code = cli_main._verify(["--record", str(path), "--hmac-secret", "s3cret"])
        assert code == 1

    def test_verify_with_signature_but_no_secret_reports_unchecked(self, tmp_path, monkeypatch, capsys):
        path = self._write_signed_record(tmp_path, "s3cret")
        monkeypatch.delenv("ISNAD_SIGNING_SECRET", raising=False)
        code = cli_main._verify(["--record", str(path)])
        assert code == 1
        assert "forge-resistance NOT checked" in capsys.readouterr().out
