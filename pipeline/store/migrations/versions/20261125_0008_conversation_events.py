"""Conversation events: allow source google_drive and subject kind conversation (ADR-0030)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-25 12:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_SOURCES = "source IN ('github', 'jira')"
NEW_SOURCES = "source IN ('github', 'jira', 'google_drive')"
OLD_KINDS = "subject_kind IN ('work_item', 'pull_request', 'release')"
NEW_KINDS = "subject_kind IN ('work_item', 'pull_request', 'release', 'conversation')"

# Every table whose check is built from pipeline.events.Source / SubjectKind.
SOURCE_TABLES = ("events", "pull_requests", "releases", "work_items")
KIND_TABLES = ("events", "snapshots")


def _swap(table: str, column: str, check: str) -> None:
    name = op.f(f"ck_{table}_{column}")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, check)


def upgrade() -> None:
    for table in SOURCE_TABLES:
        _swap(table, "source", NEW_SOURCES)
    for table in KIND_TABLES:
        _swap(table, "subject_kind", NEW_KINDS)


def downgrade() -> None:
    op.execute("DELETE FROM events WHERE subject_kind = 'conversation'")
    for table in SOURCE_TABLES:
        _swap(table, "source", OLD_SOURCES)
    for table in KIND_TABLES:
        _swap(table, "subject_kind", OLD_KINDS)
