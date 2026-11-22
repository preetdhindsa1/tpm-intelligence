"""Simulator calibrations and saved scenarios

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-22 16:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sim_calibrations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("release_key", sa.String(length=128), nullable=False),
        sa.Column("source_releases", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sim_calibrations")),
    )
    op.create_index(
        op.f("ix_sim_calibrations_release_key_created_at"),
        "sim_calibrations",
        ["release_key", "created_at"],
        unique=False,
    )
    op.create_table(
        "sim_scenarios",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("release_key", sa.String(length=128), nullable=False),
        sa.Column("calibration_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["calibration_id"],
            ["sim_calibrations.id"],
            name=op.f("fk_sim_scenarios_calibration_id_sim_calibrations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sim_scenarios")),
        sa.UniqueConstraint("release_key", "name", name=op.f("uq_sim_scenarios_release_key_name")),
    )


def downgrade() -> None:
    op.drop_table("sim_scenarios")
    op.drop_index(op.f("ix_sim_calibrations_release_key_created_at"), table_name="sim_calibrations")
    op.drop_table("sim_calibrations")
