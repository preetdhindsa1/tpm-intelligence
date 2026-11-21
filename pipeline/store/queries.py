"""Read helpers for current state."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline.store.models import WorkItem, WorkItemRelease


def active_work_items(session: Session, release_id: int) -> Sequence[WorkItem]:
    """Work items currently in a release. Removed memberships are excluded (CLAUDE.md §6)."""
    stmt = (
        select(WorkItem)
        .join(WorkItemRelease, WorkItemRelease.work_item_id == WorkItem.id)
        .where(WorkItemRelease.release_id == release_id, WorkItemRelease.status == "active")
        .order_by(WorkItem.external_key)
    )
    return session.scalars(stmt).all()
