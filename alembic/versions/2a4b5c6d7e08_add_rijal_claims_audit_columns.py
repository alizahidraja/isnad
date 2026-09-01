"""add_rijal_claims_audit_columns

Revision ID: 2a4b5c6d7e08
Revises: 1c2d3e4f5a07
Create Date: 2026-08-30

Persist the serving-path audit evidence on rijal_claims so it survives a
restart: the emitted AuditRecord self-hash, the detached signature (if signed),
and the human-oversight entries recorded at review resolution (issue #189/#193).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2a4b5c6d7e08"
down_revision: str | Sequence[str] | None = "1c2d3e4f5a07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rijal_claims",
        sa.Column("audit_record_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "rijal_claims",
        sa.Column("audit_signature", sa.Text(), nullable=True),
    )
    op.add_column(
        "rijal_claims",
        sa.Column("human_oversight", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("rijal_claims", "human_oversight")
    op.drop_column("rijal_claims", "audit_signature")
    op.drop_column("rijal_claims", "audit_record_hash")
