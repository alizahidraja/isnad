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
        assert "Usage: isnad [serve|seed]" in capsys.readouterr().out

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
