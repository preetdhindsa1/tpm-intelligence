"""Team configs per tenant (Wave 6, ADR-0035, #233)

The same body as a ``connectors/teams/<id>.yaml`` file, validated by ``TeamConfig`` on every
write and read. The public demo keeps its YAML files; other tenants live here. Row-level
security like every tenant table (ADR-0034).

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-27 18:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MATCH = "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "team_configs",
        sa.Column("tenant_id", sa.String(32),
                  sa.ForeignKey("tenants.id", name=op.f("fk_team_configs_tenant_id_tenants")),
                  primary_key=True,
                  server_default=sa.text("NULLIF(current_setting('app.tenant_id', true), '')")),
        sa.Column("team_id", sa.String(64), primary_key=True),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )  # fmt: skip
    op.execute("ALTER TABLE team_configs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE team_configs FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON team_configs USING ({MATCH}) WITH CHECK ({MATCH})"
    )


def downgrade() -> None:
    op.drop_table("team_configs")
