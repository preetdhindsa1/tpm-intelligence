"""Row-level security on every tenant table (Wave 6, ADR-0034, #232)

Each table shows and accepts only rows of the session's tenant (``app.tenant_id``, set per
transaction by pipeline/store/tenancy.py). With no tenant set, the setting reads as NULL or
'' and the policy matches no row: reads return nothing and writes are refused.

FORCE applies the policies to the table owner too. On Cloud SQL the application user owns
the tables but is not a superuser, so the policies bind it. A Postgres superuser (the local
Docker user) still bypasses them; the CI isolation tests connect as a non-superuser role.

``tenants`` has no policy: the API reads it to resolve a request's tenant before one is
set, and it holds names only.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-27 15:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "releases", "work_items", "work_item_releases", "work_item_relations", "pull_requests",
    "reviews", "review_rounds", "check_runs", "links", "events", "snapshots", "sync_cursors",
    "ai_usage", "ai_results", "risk_notes", "exec_updates", "link_suggestions",
    "sim_calibrations", "sim_scenarios", "forecast_snapshot_runs", "forecast_snapshots",
    "raid_items", "raid_history", "readiness_decisions", "retro_runs", "members",
)  # fmt: skip
POLICY = "tenant_isolation"
MATCH = "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {POLICY} ON {table} USING ({MATCH}) WITH CHECK ({MATCH})")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
