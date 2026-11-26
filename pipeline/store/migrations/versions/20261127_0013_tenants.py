"""Tenants and members; tenant_id on every row (Wave 6, ADR-0034, #230)

Existing rows become the public ``demo`` tenant. Natural unique keys gain ``tenant_id`` as
their first column, so two tenants may hold the same public PR, event or RAID key.

The column default stays ``'demo'`` in this revision so the app keeps working before
request scoping lands (#231). The next revision replaces it with the session's tenant, so a
write that has not set its tenant fails instead of landing in the demo.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-27 09:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table except alembic_version. sync_cursors and ai_results get tenant_id in their
# primary key instead of a separate index.
TABLES = (
    "releases", "work_items", "work_item_releases", "work_item_relations", "pull_requests",
    "reviews", "review_rounds", "check_runs", "links", "events", "snapshots", "sync_cursors",
    "ai_usage", "ai_results", "risk_notes", "exec_updates", "link_suggestions",
    "sim_calibrations", "sim_scenarios", "forecast_snapshot_runs", "forecast_snapshots",
    "raid_items", "raid_history", "readiness_decisions", "retro_runs",
)  # fmt: skip
PK_TABLES = {"sync_cursors": "stream", "ai_results": "fingerprint"}
# (table, old constraint, new constraint, columns after tenant_id)
UNIQUES = (
    ("releases", "uq_releases_source_project_name",
     "uq_releases_tenant_id_source_project_name", ["source", "project", "name"]),
    ("work_items", "uq_work_items_source_external_key",
     "uq_work_items_tenant_id_source_external_key", ["source", "external_key"]),
    ("pull_requests", "uq_pull_requests_repo_number",
     "uq_pull_requests_tenant_id_repo_number", ["repo", "number"]),
    ("events", "uq_events_event_id", "uq_events_tenant_id_event_id", ["event_id"]),
    ("snapshots", "uq_snapshots_kind_subject_kind_subject_key_as_of",
     "uq_snapshots_tenant_id_kind_subject_kind_subject_key_as_of",
     ["kind", "subject_kind", "subject_key", "as_of"]),
    ("link_suggestions", "uq_link_suggestions_input", "uq_link_suggestions_input",
     ["release_key", "pull_request_key", "input_sha", "prompt_version"]),
    ("sim_scenarios", "uq_sim_scenarios_release_key_name",
     "uq_sim_scenarios_tenant_id_release_key_name", ["release_key", "name"]),
    ("forecast_snapshot_runs", "uq_forecast_snapshot_runs_release_key_snapshot_date_mod_ae5c",
     "uq_forecast_snapshot_runs_tenant_release_date_model",
     ["release_key", "snapshot_date", "model_version"]),
    ("raid_items", "uq_raid_items_key", "uq_raid_items_tenant_id_key", ["key"]),
    ("raid_items", "uq_raid_items_raid_id", "uq_raid_items_tenant_id_raid_id", ["raid_id"]),
)  # fmt: skip
# Append-only tables refuse UPDATE; adding a column with a default does not fire row
# triggers, so these need no exception here.


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("public", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.CheckConstraint("id ~ '^[a-z0-9][a-z0-9-]{1,31}$'", name=op.f("ck_tenants_id_slug")),
    )  # fmt: skip
    op.execute("INSERT INTO tenants (id, name, public) VALUES ('demo', 'Public demo', true)")
    op.create_table(
        "members",
        sa.Column("tenant_id", sa.String(32),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE",
                                name=op.f("fk_members_tenant_id_tenants")),
                  primary_key=True),
        sa.Column("login", sa.String(64), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.CheckConstraint("role IN ('reader', 'approver', 'owner')",
                           name=op.f("ck_members_role")),
    )  # fmt: skip
    for table in TABLES:
        # A constant default does not rewrite the table (Postgres 11+), even for events.
        op.add_column(
            table,
            sa.Column("tenant_id", sa.String(32), server_default=sa.text("'demo'"),
                      nullable=False),
        )  # fmt: skip
        op.create_foreign_key(
            op.f(f"fk_{table}_tenant_id_tenants"), table, "tenants", ["tenant_id"], ["id"]
        )
        if table in PK_TABLES:
            op.drop_constraint(f"pk_{table}", table, type_="primary")
            op.create_primary_key(f"pk_{table}", table, ["tenant_id", PK_TABLES[table]])
        else:
            op.create_index(op.f(f"ix_{table}_tenant_id"), table, ["tenant_id"])
    for table, old, new, cols in UNIQUES:
        op.drop_constraint(old, table, type_="unique")
        op.create_unique_constraint(new, table, ["tenant_id", *cols])


def downgrade() -> None:
    for table, old, new, cols in reversed(UNIQUES):
        op.drop_constraint(new, table, type_="unique")
        op.create_unique_constraint(old, table, cols)
    for table in reversed(TABLES):
        if table in PK_TABLES:
            op.drop_constraint(f"pk_{table}", table, type_="primary")
            op.create_primary_key(f"pk_{table}", table, [PK_TABLES[table]])
        else:
            op.drop_index(op.f(f"ix_{table}_tenant_id"), table_name=table)
        op.drop_constraint(op.f(f"fk_{table}_tenant_id_tenants"), table, type_="foreignkey")
        op.drop_column(table, "tenant_id")
    op.drop_table("members")
    op.drop_table("tenants")
