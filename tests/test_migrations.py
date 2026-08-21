"""Test the Alembic migration graph is well-formed: a single head, no gaps.

The codebase ships Alembic migrations as the upgrade path for existing
databases.  A regression here is catastrophic (``alembic upgrade head``
errors with "multiple heads"), and it happened once already — grade-freshness
(3a8fc4ac1b05) and content-snapshots (3937bac5b5a1) both branched off the
initial schema.  The merge migration (5c1e2f3a4b01) rejoins them; this test
pins that invariant.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_alembic_has_single_head():
    """``alembic heads`` must report exactly one head."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    heads = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    # Each head line is "<rev> (head)".  Exactly one.
    assert len(heads) == 1, f"expected 1 head, got {len(heads)}: {heads}"


def test_alembic_upgrade_head_succeeds_on_fresh_db(tmp_path):
    """A fresh DB can be migrated to head with no errors."""
    db_path = tmp_path / "migration_test.db"
    url = f"sqlite:///{db_path}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={"ISNAD_DATABASE_URL": url, "PATH": __import__("os").environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr

    # The migrated schema must contain the columns both migrations add.
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    narrator_cols = [r[1] for r in conn.execute("PRAGMA table_info(narrator_registry)")]
    chain_cols = [r[1] for r in conn.execute("PRAGMA table_info(chain_links)")]
    conn.close()

    assert "graded_at" in narrator_cols
    assert "valid_until" in narrator_cols
    assert "input_snapshot" in chain_cols
    assert "output_snapshot" in chain_cols
