"""Conversation sources: allow slack, zoom, ms_teams and google_meet (ADR-0030)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-25 14:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "source IN ('github', 'jira', 'google_drive')"
NEW = "source IN ('github', 'jira', 'google_drive', 'slack', 'zoom', 'ms_teams', 'google_meet')"
TABLES = ("events", "pull_requests", "releases", "work_items")


def _swap(table: str, check: str) -> None:
    name = op.f(f"ck_{table}_source")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, check)


def upgrade() -> None:
    for table in TABLES:
        _swap(table, NEW)


def downgrade() -> None:
    op.execute("DELETE FROM events WHERE source IN ('slack', 'zoom', 'ms_teams', 'google_meet')")
    for table in TABLES:
        _swap(table, OLD)
