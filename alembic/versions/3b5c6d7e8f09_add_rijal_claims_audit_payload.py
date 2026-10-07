"""add_rijal_claims_audit_payload

Revision ID: 3b5c6d7e8f09
Revises: 2a4b5c6d7e08
Create Date: 2026-09-11

Persist the canonical AuditRecord payload (non-integrity fields) so the stored
audit_record_hash and audit_signature can be recomputed and verified on read —
the serving-path "tamper-detecting" claim was previously unverifiable because the
record that was hashed and signed was discarded.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3b5c6d7e8f09"
down_revision: str | Sequence[str] | None = "2a4b5c6d7e08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rijal_claims",
        sa.Column("audit_payload", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rijal_claims", "audit_payload")
