"""add_chain_link_content_snapshots

Revision ID: 3937bac5b5a1
Revises: bcf1da0dec28
Create Date: 2026-08-10 00:46:47.921312

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3937bac5b5a1'
down_revision: Union[str, Sequence[str], None] = 'bcf1da0dec28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'chain_links',
        sa.Column(
            'input_snapshot',
            sa.Text(),
            nullable=True,
            comment="Claim text state entering this link's transformation",
        ),
    )
    op.add_column(
        'chain_links',
        sa.Column(
            'output_snapshot',
            sa.Text(),
            nullable=True,
            comment="Claim text state leaving this link's transformation",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chain_links', 'output_snapshot')
    op.drop_column('chain_links', 'input_snapshot')
