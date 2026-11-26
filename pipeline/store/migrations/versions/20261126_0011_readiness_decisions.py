"""Readiness go/no-go decisions, append-only (Wave 5, ADR-0032)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-26 10:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
FORBID = """
CREATE FUNCTION forbid_readiness_decision_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'readiness decisions are append-only (ADR-0032): % refused', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "readiness_decisions",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("release_key", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("decided_at", TZ, nullable=False),
        sa.Column("facts_as_of", TZ, nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),  # what the rules said then
        sa.Column("by_login", sa.String(64), nullable=False),  # audit only; never returned
        sa.CheckConstraint(
            "decision IN ('go', 'no_go', 'defer')", name=op.f("ck_readiness_decisions_decision")
        ),
        sa.CheckConstraint("length(trim(note)) >= 3", name=op.f("ck_readiness_decisions_note")),
    )
    op.create_index(
        op.f("ix_readiness_decisions_release_key"), "readiness_decisions", ["release_key", "id"]
    )
    op.execute(FORBID)
    op.execute(
        "CREATE TRIGGER readiness_decisions_append_only BEFORE UPDATE OR DELETE ON "
        "readiness_decisions FOR EACH ROW EXECUTE FUNCTION forbid_readiness_decision_change()"
    )


def downgrade() -> None:
    op.drop_table("readiness_decisions")
    op.execute("DROP FUNCTION IF EXISTS forbid_readiness_decision_change()")
