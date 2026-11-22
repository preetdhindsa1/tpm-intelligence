"""risk notes

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-22 08:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_notes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("release_key", sa.String(length=128), nullable=False),
        sa.Column("feature_key", sa.String(length=256), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("claims", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_notes")),
    )
    op.create_index(
        op.f("ix_risk_notes_release_key_feature_key_id"),
        "risk_notes",
        ["release_key", "feature_key", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_risk_notes_release_key_feature_key_id"), table_name="risk_notes")
    op.drop_table("risk_notes")
