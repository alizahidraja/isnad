"""add_rijal_claims_verdict_columns

Revision ID: 1c2d3e4f5a07
Revises: 9d2e3f4a5b06
Create Date: 2026-08-29

Persist ``content_verdict`` and ``action`` on rijal_claims so a restart
rehydration is faithful instead of re-deriving a CONTRADICTION as UNVERIFIABLE
(which silently upgraded a held SAHIH × CONTRADICTION → REVIEW to
SERVE_WITH_CAVEAT).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c2d3e4f5a07"
down_revision: Union[str, Sequence[str], None] = "9d2e3f4a5b06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rijal_claims",
        sa.Column("content_verdict", sa.String(32), nullable=True),
    )
    op.add_column(
        "rijal_claims",
        sa.Column("action", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rijal_claims", "action")
    op.drop_column("rijal_claims", "content_verdict")
