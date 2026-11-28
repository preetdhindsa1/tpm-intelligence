"""Index events by (tenant_id, id) (Wave 7, #258)

The API loads new events with ``id > last_id``. Under row-level security Postgres walked the
primary key past every newer row of every other tenant and filtered them out: with two
tenants of 391,486 events each, the older tenant's "anything new?" check removed 391,486
rows and took 575 ms, on every request. With this index the newest id of a tenant is an
index-only lookup (0.7 ms). Measured locally; docs/results/load-test-local-20261127.json.

Built concurrently so writes are not blocked on Cloud SQL.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-27 08:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "ix_events_tenant_id_id"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(NAME, "events", ["tenant_id", "id"], postgresql_concurrently=True,
                        if_not_exists=True)  # fmt: skip


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(NAME, "events", postgresql_concurrently=True, if_exists=True)
