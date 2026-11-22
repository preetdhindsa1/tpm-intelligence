"""executive updates

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-22 09:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=False)


def upgrade() -> None:
    op.create_table(
        "exec_updates",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("release_key", sa.String(length=128), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        _json("header"),
        _json("sections"),
        _json("facts"),
        _json("counts"),
        _json("removed"),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("trimmed_for_length", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("edited", sa.Boolean(), server_default="false", nullable=False),
        _json("warnings"),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("approved_with_warnings", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("approved_while_stale", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'rejected')", name=op.f("ck_exec_updates_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exec_updates")),
    )
    op.create_index(
        op.f("ix_exec_updates_release_key_id"), "exec_updates", ["release_key", "id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_exec_updates_release_key_id"), table_name="exec_updates")
    op.drop_table("exec_updates")
