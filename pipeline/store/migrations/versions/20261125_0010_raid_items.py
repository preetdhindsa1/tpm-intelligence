"""RAID items and their append-only history (Wave 4, ADR-0030 addendum 2)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-25 22:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "raid_items",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("key", sa.String(32), nullable=False),
        sa.Column("release_key", sa.String(128), nullable=False),
        sa.Column("workstream", sa.String(16), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("quote", sa.Text, nullable=False),
        sa.Column("document_id", sa.String(128), nullable=False),
        sa.Column("meeting_date", sa.String(10), nullable=False),
        sa.Column("owner", sa.String(120)),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("review", sa.String(16), nullable=False, server_default="suggested"),
        sa.Column("raid_id", sa.String(32)),
        sa.Column("links", JSONB, nullable=False, server_default="[]"),
        sa.Column("merge_into", sa.BigInteger, sa.ForeignKey("raid_items.id")),
        sa.Column("merge_reason", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("key", name=op.f("uq_raid_items_key")),
        sa.UniqueConstraint("raid_id", name=op.f("uq_raid_items_raid_id")),
        sa.CheckConstraint(
            "type IN ('risk', 'action', 'issue', 'decision', 'question')",
            name=op.f("ck_raid_items_type"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'closed', 'superseded')",
            name=op.f("ck_raid_items_status"),
        ),
        sa.CheckConstraint(
            "review IN ('suggested', 'confirmed', 'edited', 'rejected')",
            name=op.f("ck_raid_items_review"),
        ),
        # A RAID ID exactly when a person confirmed or edited the item (ADR-0030 add. 2).
        sa.CheckConstraint(
            "(review IN ('confirmed', 'edited')) = (raid_id IS NOT NULL)",
            name=op.f("ck_raid_items_id_on_confirm"),
        ),
    )
    op.create_index(op.f("ix_raid_items_release_key"), "raid_items", ["release_key", "review"])
    op.create_table(
        "raid_history",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("item_id", sa.BigInteger, sa.ForeignKey("raid_items.id"), nullable=False),
        sa.Column("at", TZ, nullable=False),
        sa.Column("actor", sa.String(16), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("changes", JSONB, nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text),
        sa.Column("by_login", sa.String(64)),  # audit only; never returned by the API
        sa.CheckConstraint(
            "actor IN ('extractor', 'approver')", name=op.f("ck_raid_history_actor")
        ),
        sa.CheckConstraint(
            "action <> 'rejected' OR length(trim(coalesce(reason, ''))) > 0",
            name=op.f("ck_raid_history_reject_reason"),
        ),
    )
    op.create_index(op.f("ix_raid_history_item_id"), "raid_history", ["item_id", "id"])


def downgrade() -> None:
    op.drop_table("raid_history")
    op.drop_table("raid_items")
