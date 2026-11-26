"""Audit log, tenant limits, and deletion on request (Wave 6, ADR-0035, #234)

- ``audit_log``: every admin action, append-only, under row-level security.
- ``tenants`` gains its AI budget and team limit; the demo keeps $2/day (CLAUDE.md
  section 8).
- The append-only triggers (events, forecast snapshots, readiness decisions, retro runs,
  audit log) now allow DELETE in one case only: the tenant-deletion function's own
  transaction, which sets ``app.deleting_tenant`` to the tenant its session is scoped to.
  UPDATE and TRUNCATE stay refused, and an ordinary session still cannot edit history.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-27 20:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MATCH = "tenant_id = current_setting('app.tenant_id', true)"
# Deleting this transaction's own tenant, through the deletion function (connectors/admin).
DELETING = (
    "TG_OP = 'DELETE' AND COALESCE(current_setting('app.deleting_tenant', true), '') <> '' "
    "AND current_setting('app.deleting_tenant', true) = current_setting('app.tenant_id', true)"
)
GUARDS = {  # function -> its refusal, as before
    "tpm_reject_event_mutation": (
        "RAISE EXCEPTION 'events is append-only (% rejected)', TG_OP "
        "USING ERRCODE = 'restrict_violation';"
    ),
    "forbid_snapshot_change": (
        "RAISE EXCEPTION 'forecast snapshots are append-only (ADR-0015): % on % refused', "
        "TG_OP, TG_TABLE_NAME;"
    ),
    "forbid_readiness_decision_change": (
        "RAISE EXCEPTION 'readiness decisions are append-only (ADR-0032): % refused', TG_OP;"
    ),
    "forbid_retro_run_change": (
        "RAISE EXCEPTION 'retro runs are append-only (ADR-0032): % refused', TG_OP;"
    ),
    "forbid_audit_change": (
        "RAISE EXCEPTION 'the audit log is append-only (ADR-0035): % refused', TG_OP;"
    ),
}


def _function(name: str, refusal: str, *, deletable: bool) -> str:
    allow = (
        f"IF {DELETING} THEN IF TG_LEVEL = 'ROW' THEN RETURN OLD; END IF; RETURN NULL; END IF;"
        if deletable
        else ""
    )
    return (
        f"CREATE OR REPLACE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ "
        f"BEGIN {allow} {refusal} END; $$"
    )


def upgrade() -> None:
    op.add_column("tenants", sa.Column("ai_daily_budget_usd", sa.Numeric(8, 2),
                                       server_default="0.50", nullable=False))  # fmt: skip
    op.add_column("tenants", sa.Column("max_teams", sa.Integer, server_default="3",
                                       nullable=False))  # fmt: skip
    op.execute("UPDATE tenants SET ai_daily_budget_usd = 2.00, max_teams = 50 WHERE id = 'demo'")
    # Final "tenant deleted" entries live here, outside the deleted tenant.
    op.execute("INSERT INTO tenants (id, name) VALUES ('system', 'System') ON CONFLICT DO NOTHING")
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("tenant_id", sa.String(32),
                  sa.ForeignKey("tenants.id", name=op.f("fk_audit_log_tenant_id_tenants")),
                  nullable=False,
                  server_default=sa.text("NULLIF(current_setting('app.tenant_id', true), '')")),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_login", sa.String(64), nullable=False),
        sa.Column("actor_role", sa.String(16), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("target", sa.String(200), nullable=False),
        sa.Column("details", JSONB, server_default="{}", nullable=False),
    )  # fmt: skip
    op.create_index(op.f("ix_audit_log_tenant_id"), "audit_log", ["tenant_id", "id"])
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON audit_log USING ({MATCH}) WITH CHECK ({MATCH})")
    for name, refusal in GUARDS.items():
        op.execute(_function(name, refusal, deletable=True))
    op.execute(
        "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION forbid_audit_change()"
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.execute("DROP FUNCTION IF EXISTS forbid_audit_change()")
    for name, refusal in GUARDS.items():
        if name != "forbid_audit_change":
            op.execute(_function(name, refusal, deletable=False))
    op.execute("DELETE FROM tenants WHERE id = 'system'")
    op.drop_column("tenants", "max_teams")
    op.drop_column("tenants", "ai_daily_budget_usd")
