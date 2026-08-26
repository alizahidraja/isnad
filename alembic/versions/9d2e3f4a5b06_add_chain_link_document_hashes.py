"""add_chain_link_document_hashes

Revision ID: 9d2e3f4a5b06
Revises: 7a1f2b3c4d05
Create Date: 2026-08-27

Adds a JSON column for retrieved-document content hashes on chain_links, so the
madār (shared-document) correlation check (#125) can round-trip through the
normalized link table, not just the denormalized narrator_chain JSONB copy.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d2e3f4a5b06"
down_revision: Union[str, Sequence[str], None] = "7a1f2b3c4d05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chain_links",
        sa.Column(
            "document_hashes",
            sa.JSON(),
            nullable=False,
            server_default="[]",
            comment="Retrieved-document content hashes (madār correlation check, #125)",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chain_links", "document_hashes")
