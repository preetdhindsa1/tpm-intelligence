"""Retro runs: each computed retro, append-only (Wave 5, ADR-0032 addendum 2)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-26 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FORBID = """
CREATE FUNCTION forbid_retro_run_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'retro runs are append-only (ADR-0032): % refused', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "retro_runs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("release_key", sa.String(128), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("body", JSONB, nullable=False),
    )
    op.create_index(op.f("ix_retro_runs_release_key"), "retro_runs", ["release_key", "id"])
    op.execute(FORBID)
    op.execute(
        "CREATE TRIGGER retro_runs_append_only BEFORE UPDATE OR DELETE ON retro_runs "
        "FOR EACH ROW EXECUTE FUNCTION forbid_retro_run_change()"
    )


def downgrade() -> None:
    op.drop_table("retro_runs")
    op.execute("DROP FUNCTION IF EXISTS forbid_retro_run_change()")
