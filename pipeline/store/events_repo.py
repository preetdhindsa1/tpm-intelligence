"""Append and read the immutable event log."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pipeline.events import EventPayload, NormalizedEvent, Source, SubjectKind, SubjectRef
from pipeline.store.models import EventRecord


def _row(event: NormalizedEvent) -> dict[str, object]:
    return {
        "event_id": uuid.UUID(event.event_id),
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "source": event.source.value,
        "subject_kind": event.subject.kind.value,
        "subject_key": event.subject.external_key,
        "occurred_at": event.occurred_at,
        "observed_at": event.observed_at,
        "payload": event.payload.model_dump(mode="json"),
    }


def append_events(session: Session, events: Iterable[NormalizedEvent]) -> int:
    """Insert events, skipping any ``event_id`` already stored. Return how many were new.

    Idempotent, so at-least-once queue delivery and re-polls are safe.
    """
    rows = [_row(e) for e in events]
    if not rows:
        return 0
    stmt = (
        insert(EventRecord)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(EventRecord.id)
    )
    return len(session.execute(stmt).all())


def events_for_subject(
    session: Session, subject: SubjectRef, *, as_of: datetime | None = None
) -> Sequence[EventRecord]:
    """Events about ``subject`` in ``occurred_at`` order.

    With ``as_of``, only events that **occurred strictly before** it are returned: the
    rule backtests depend on (CLAUDE.md section 6).
    """
    stmt = (
        select(EventRecord)
        .where(
            EventRecord.subject_kind == subject.kind.value,
            EventRecord.subject_key == subject.external_key,
        )
        .order_by(EventRecord.occurred_at, EventRecord.id)
    )
    if as_of is not None:
        stmt = stmt.where(EventRecord.occurred_at < as_of)
    return session.scalars(stmt).all()


_PAYLOAD = TypeAdapter(EventPayload)


def to_event(row: EventRecord) -> NormalizedEvent:
    """Rebuild a :class:`NormalizedEvent` from a stored row."""
    return NormalizedEvent(
        event_id=str(row.event_id),
        schema_version=row.schema_version,
        source=Source(row.source),
        subject=SubjectRef(
            kind=SubjectKind(row.subject_kind),
            source=Source(row.source),
            external_key=row.subject_key,
        ),
        occurred_at=row.occurred_at,
        observed_at=row.observed_at,
        payload=_PAYLOAD.validate_python(row.payload),
    )


def iter_events(
    session: Session, *, batch_size: int = 5000, project: str | None = None
) -> Iterator[NormalizedEvent]:
    """Stream stored events in ``occurred_at`` order; only ``project``'s when given (ADR-0018)."""
    team = None
    if project is not None:
        from connectors.load import team_for_project

        team = team_for_project(project)
    stmt = select(EventRecord).order_by(EventRecord.occurred_at, EventRecord.id)
    for row in session.scalars(stmt.execution_options(yield_per=batch_size)):
        event = to_event(row)
        if team is None or team.owns(event.subject.external_key):
            yield event
