"""add_role_dimension

Adds per-role precision grading (issue #3): a ``role`` column joins the
``narrator_registry`` primary key and the ``narrator_evidence`` composite
foreign key, so a narrator can hold one *integrity* record per
``(narrator, domain)`` and multiple *precision* records per
``(narrator, role, domain)``.

- ``role = ""``  → the default/integrity record (legacy behaviour)
- ``role = "synthesis"`` etc. → a role-scoped precision record

SQLite cannot alter a primary/foreign key in place, so on SQLite the two
tables are recreated and their rows copied across; on PostgreSQL the columns
and constraints are altered in place.

Revision ID: 7a1f2b3c4d05
Revises: 5c1e2f3a4b01
Create Date: 2026-08-21 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a1f2b3c4d05"
down_revision: str | Sequence[str] | None = "5c1e2f3a4b01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REGISTRY_COLS = [
    "narrator_id",
    "domain_tag",
    "narrator_type",
    "grade",
    "adalah_grade",
    "dabt_grade",
    "known_error_rate",
    "model_version",
    "model_family",
    "upstream_source",
    "is_active",
    "graded_at",
    "valid_until",
]

_EVIDENCE_COLS = [
    "id",
    "narrator_id",
    "domain_tag",
    "evidence_type",
    "action",
    "description",
    "metadata_json",
    "created_at",
]


def _sqlite_recreate() -> None:
    """Recreate narrator_registry + narrator_evidence with role in the PK/FK."""
    # --- narrator_registry ---
    op.execute("ALTER TABLE narrator_registry RENAME TO _narrator_registry_old")
    op.create_table(
        "narrator_registry",
        sa.Column("narrator_id", sa.String(128), nullable=False),
        sa.Column("domain_tag", sa.String(128), nullable=False),
        sa.Column("role", sa.String(128), nullable=False, server_default=""),
        sa.Column("narrator_type", sa.String(32), nullable=False, server_default="model"),
        sa.Column("grade", sa.String(32), nullable=False, server_default="ungraded"),
        sa.Column("adalah_grade", sa.String(32), nullable=False, server_default="unassessed"),
        sa.Column("dabt_grade", sa.String(32), nullable=False, server_default="unassessed"),
        sa.Column("known_error_rate", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(128), nullable=True),
        sa.Column("model_family", sa.String(128), nullable=True),
        sa.Column("upstream_source", sa.String(256), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("narrator_id", "domain_tag", "role"),
    )
    cols = ", ".join(_REGISTRY_COLS)
    op.execute(
        f"INSERT INTO narrator_registry ({cols}, role) "
        f"SELECT {cols}, '' FROM _narrator_registry_old"
    )
    op.execute("DROP TABLE _narrator_registry_old")
    op.create_index("ix_narrator_registry_grade", "narrator_registry", ["grade"], unique=False)
    op.create_index(
        "ix_narrator_registry_is_active", "narrator_registry", ["is_active"], unique=False
    )

    # --- narrator_evidence ---
    op.execute("ALTER TABLE narrator_evidence RENAME TO _narrator_evidence_old")
    op.create_table(
        "narrator_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("narrator_id", sa.String(128), nullable=False),
        sa.Column("domain_tag", sa.String(128), nullable=False),
        sa.Column("role", sa.String(128), nullable=False, server_default=""),
        sa.Column("evidence_type", sa.String(32), nullable=False, server_default="eval_harness"),
        sa.Column("action", sa.String(16), nullable=False, server_default="neutral"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["narrator_id", "domain_tag", "role"],
            ["narrator_registry.narrator_id", "narrator_registry.domain_tag", "narrator_registry.role"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    cols = ", ".join(_EVIDENCE_COLS)
    op.execute(
        f"INSERT INTO narrator_evidence ({cols}, role) "
        f"SELECT {cols}, '' FROM _narrator_evidence_old"
    )
    op.execute("DROP TABLE _narrator_evidence_old")
    op.create_index(
        "ix_narrator_evidence_narrator",
        "narrator_evidence",
        ["narrator_id", "domain_tag", "role"],
        unique=False,
    )
    op.create_index(
        "ix_narrator_evidence_created", "narrator_evidence", ["created_at"], unique=False
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _sqlite_recreate()
        return

    # PostgreSQL: alter in place.
    op.add_column(
        "narrator_registry",
        sa.Column("role", sa.String(128), nullable=False, server_default=""),
    )
    op.add_column(
        "narrator_evidence",
        sa.Column("role", sa.String(128), nullable=False, server_default=""),
    )
    # Rebuild PK/FK to include role.
    with op.batch_alter_table("narrator_registry") as batch:
        batch.drop_constraint("narrator_registry_pkey", type_="primary")
        batch.create_primary_key("narrator_registry_pkey", ["narrator_id", "domain_tag", "role"])
    with op.batch_alter_table("narrator_evidence") as batch:
        batch.drop_constraint(
            "narrator_evidence_narrator_id_fkey", type_="foreignkey"
        )
        batch.create_foreign_key(
            "narrator_evidence_narrator_id_fkey",
            "narrator_registry",
            ["narrator_id", "domain_tag", "role"],
            ["narrator_id", "domain_tag", "role"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite downgrade: recreate without role (drop the role dimension).
        op.execute("ALTER TABLE narrator_registry RENAME TO _narrator_registry_old")
        op.create_table(
            "narrator_registry",
            sa.Column("narrator_id", sa.String(128), nullable=False),
            sa.Column("domain_tag", sa.String(128), nullable=False),
            sa.Column("narrator_type", sa.String(32), nullable=False),
            sa.Column("grade", sa.String(32), nullable=False),
            sa.Column("adalah_grade", sa.String(32), nullable=False),
            sa.Column("dabt_grade", sa.String(32), nullable=False),
            sa.Column("known_error_rate", sa.Float(), nullable=True),
            sa.Column("model_version", sa.String(128), nullable=True),
            sa.Column("model_family", sa.String(128), nullable=True),
            sa.Column("upstream_source", sa.String(256), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("narrator_id", "domain_tag"),
        )
        cols = ", ".join(_REGISTRY_COLS)
        op.execute(
            f"INSERT INTO narrator_registry ({cols}) "
            f"SELECT {cols} FROM _narrator_registry_old WHERE role = ''"
        )
        op.execute("DROP TABLE _narrator_registry_old")
        op.create_index("ix_narrator_registry_grade", "narrator_registry", ["grade"], unique=False)
        op.create_index(
            "ix_narrator_registry_is_active", "narrator_registry", ["is_active"], unique=False
        )

        op.execute("ALTER TABLE narrator_evidence RENAME TO _narrator_evidence_old")
        op.create_table(
            "narrator_evidence",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("narrator_id", sa.String(128), nullable=False),
            sa.Column("domain_tag", sa.String(128), nullable=False),
            sa.Column("evidence_type", sa.String(32), nullable=False),
            sa.Column("action", sa.String(16), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["narrator_id", "domain_tag"],
                ["narrator_registry.narrator_id", "narrator_registry.domain_tag"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        cols = ", ".join(_EVIDENCE_COLS)
        op.execute(
            f"INSERT INTO narrator_evidence ({cols}) "
            f"SELECT {cols} FROM _narrator_evidence_old WHERE role = ''"
        )
        op.execute("DROP TABLE _narrator_evidence_old")
        op.create_index(
            "ix_narrator_evidence_narrator",
            "narrator_evidence",
            ["narrator_id", "domain_tag"],
            unique=False,
        )
        op.create_index(
            "ix_narrator_evidence_created", "narrator_evidence", ["created_at"], unique=False
        )
        return

    # PostgreSQL downgrade.
    with op.batch_alter_table("narrator_evidence") as batch:
        batch.drop_constraint("narrator_evidence_narrator_id_fkey", type_="foreignkey")
        batch.create_foreign_key(
            "narrator_evidence_narrator_id_fkey",
            "narrator_registry",
            ["narrator_id", "domain_tag"],
            ["narrator_id", "domain_tag"],
            ondelete="CASCADE",
        )
    with op.batch_alter_table("narrator_registry") as batch:
        batch.drop_constraint("narrator_registry_pkey", type_="primary")
        batch.create_primary_key("narrator_registry_pkey", ["narrator_id", "domain_tag"])
    op.drop_column("narrator_evidence", "role")
    op.drop_column("narrator_registry", "role")
