"""add_grade_freshness

Adds the time-decay fields to narrator_registry so narrator grades can
expire and be flagged for re-check (the grade-expiry fix):

- graded_at:    when the current grade was last validated by evidence
- valid_until:  grade best-before (graded_at + volatility policy TTL)

Both are nullable: NULL graded_at/valid_until means the grade carries no
freshness clock (never graded, or active containment REJECTED).  Legacy
rows stay NULL and behave as before until they receive new evidence.

Revision ID: 3a8fc4ac1b05
Revises: bcf1da0dec28
Create Date: 2026-08-05 23:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a8fc4ac1b05"
down_revision: str | Sequence[str] | None = "bcf1da0dec28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add grade-freshness columns to narrator_registry."""
    op.add_column(
        "narrator_registry",
        sa.Column(
            "graded_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the current grade was last validated by evidence (UTC)",
        ),
    )
    op.add_column(
        "narrator_registry",
        sa.Column(
            "valid_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Grade best-before (graded_at + volatility TTL); NULL = never expires",
        ),
    )


def downgrade() -> None:
    """Remove the grade-freshness columns."""
    op.drop_column("narrator_registry", "valid_until")
    op.drop_column("narrator_registry", "graded_at")
