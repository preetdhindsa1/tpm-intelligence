"""Forecast snapshots: daily, append-only record of every forecast (ADR-0015)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-22 21:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Stored forecasts are evidence for a later, unseen test: they must never change.
FORBID = """
CREATE FUNCTION forbid_snapshot_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'forecast snapshots are append-only (ADR-0015): % on % refused',
        TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "forecast_snapshot_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("release_key", sa.String(length=128), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("code_freeze_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forecast_snapshot_runs")),
        sa.UniqueConstraint(
            "release_key",
            "snapshot_date",
            "model_version",
            name=op.f("uq_forecast_snapshot_runs_release_key_snapshot_date_model_version"),
        ),
    )
    op.create_table(
        "forecast_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("feature_key", sa.String(length=128), nullable=False),
        sa.Column("in_release", sa.Boolean(), nullable=False),
        sa.Column("odds_status", sa.String(length=32), nullable=False),
        sa.Column("probability", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("raw_probability", sa.Float(), nullable=True),
        sa.Column("merge_status", sa.String(length=32), nullable=False),
        sa.Column("done_day", sa.Float(), nullable=True),
        sa.Column("p10", sa.Float(), nullable=True),
        sa.Column("p50", sa.Float(), nullable=True),
        sa.Column("p90", sa.Float(), nullable=True),
        sa.Column("by_freeze", sa.Float(), nullable=True),
        sa.Column("by_release", sa.Float(), nullable=True),
        sa.Column("cdf", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["forecast_snapshot_runs.id"],
            name=op.f("fk_forecast_snapshots_run_id_forecast_snapshot_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forecast_snapshots")),
        sa.UniqueConstraint(
            "run_id", "feature_key", name=op.f("uq_forecast_snapshots_run_id_feature_key")
        ),
    )
    op.execute(FORBID)
    for table in ("forecast_snapshot_runs", "forecast_snapshots"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_snapshot_change()"
        )


def downgrade() -> None:
    for table in ("forecast_snapshots", "forecast_snapshot_runs"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.drop_table("forecast_snapshots")
    op.drop_table("forecast_snapshot_runs")
    op.execute("DROP FUNCTION IF EXISTS forbid_snapshot_change()")
