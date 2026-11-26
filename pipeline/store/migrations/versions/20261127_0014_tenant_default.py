"""tenant_id defaults to the session's tenant, not the demo (Wave 6, ADR-0034, #231)

Every transaction sets ``app.tenant_id`` (pipeline/store/tenancy.py). A write from a session
that did not set it now fails (NOT NULL) instead of landing in the public demo. ``NULLIF``
because a pooled connection reads the setting as '' after a scoped transaction ended.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-27 12:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "releases", "work_items", "work_item_releases", "work_item_relations", "pull_requests",
    "reviews", "review_rounds", "check_runs", "links", "events", "snapshots", "sync_cursors",
    "ai_usage", "ai_results", "risk_notes", "exec_updates", "link_suggestions",
    "sim_calibrations", "sim_scenarios", "forecast_snapshot_runs", "forecast_snapshots",
    "raid_items", "raid_history", "readiness_decisions", "retro_runs",
)  # fmt: skip


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN tenant_id "
            "SET DEFAULT NULLIF(current_setting('app.tenant_id', true), '')"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET DEFAULT 'demo'")
