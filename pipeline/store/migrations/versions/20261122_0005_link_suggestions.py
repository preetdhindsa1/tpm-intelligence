"""AI link suggestions and their review

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "link_suggestions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("release_key", sa.String(length=128), nullable=False),
        sa.Column("pull_request_key", sa.String(length=256), nullable=False),
        sa.Column("feature_key", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_sha", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'confirmed', 'rejected', 'none', 'dropped')",
            name=op.f("ck_link_suggestions_status"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('confirmed', 'rejected') OR "
            "(decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name=op.f("ck_link_suggestions_decision_has_person"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('suggested', 'confirmed', 'rejected') OR feature_key IS NOT NULL",
            name=op.f("ck_link_suggestions_link_has_feature"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_link_suggestions")),
        sa.UniqueConstraint(
            "release_key",
            "pull_request_key",
            "input_sha",
            "prompt_version",
            name=op.f("uq_link_suggestions_input"),
        ),
    )
    op.create_index(
        op.f("ix_link_suggestions_release_key_status"),
        "link_suggestions",
        ["release_key", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_link_suggestions_release_key_status"), table_name="link_suggestions")
    op.drop_table("link_suggestions")
