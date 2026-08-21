"""merge_grade_freshness_and_content_snapshots

Merge the two parallel migration heads created when grade-freshness
(3a8fc4ac1b05, PR #12) and chain-link content snapshots (3937bac5b5a1,
PR #14) both branched off the initial schema (bcf1da0dec28).

Both migrations are additive and touch different tables, so the merge
itself makes no schema changes — it only rejoins the two heads so that
``alembic upgrade head`` resolves to a single head again.

Revision ID: 5c1e2f3a4b01
Revises: 3a8fc4ac1b05, 3937bac5b5a1
Create Date: 2026-08-21 00:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "5c1e2f3a4b01"
down_revision: str | Sequence[str] | None = ("3a8fc4ac1b05", "3937bac5b5a1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rejoin the two parallel heads — no schema changes required."""


def downgrade() -> None:
    """Split the merged head back into its two parents (no-op)."""
