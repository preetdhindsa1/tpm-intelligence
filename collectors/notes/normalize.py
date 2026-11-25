"""Meetings → normalized conversation events (ADR-0030). Pure, no I/O."""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime, time, timedelta

from collectors.notes.parse import Meeting
from pipeline.events import (
    ConversationKind,
    ConversationSegmentObserved,
    NormalizedEvent,
    Source,
    SubjectKind,
    SubjectRef,
    new_event,
)


def occurred_at(meeting: Meeting, fallback: datetime) -> datetime:
    """When the notes count as known: the end of the meeting day, UTC.

    The notes give a date but no time (meetings run in APAC and EMEA slots), so a replay
    of an earlier moment never sees them before the day is over (CLAUDE.md section 6).
    """
    if meeting.meeting_date is None:
        return fallback
    return datetime.combine(meeting.meeting_date + timedelta(days=1), time(), tzinfo=UTC)


def to_events(
    meetings: list[Meeting],
    *,
    project: str,
    document_id: str,
    title: str,
    url: str,
    release_key: str | None,
    observed_at: datetime,
) -> list[NormalizedEvent]:
    """One event per meeting. Its identity includes the text hash, so an edit is a new event."""
    seen: Counter[str] = Counter()
    events = []
    for m in meetings:
        day = m.meeting_date.isoformat() if m.meeting_date else f"week-{m.week}"
        seen[day] += 1
        key = f"{project}:notes/{document_id}/{day}/{seen[day]}"
        digest = hashlib.sha256(m.text.encode()).hexdigest()
        payload = ConversationSegmentObserved(
            kind=ConversationKind.MEETING_NOTES,
            container=document_id,
            container_title=title,
            heading=m.heading,
            text=m.text,
            text_sha256=digest,
            meeting_date=m.meeting_date,
            release_key=release_key,
            url=url,
        )
        events.append(
            new_event(
                source=Source.GOOGLE_DRIVE,
                subject=SubjectRef(
                    kind=SubjectKind.CONVERSATION, source=Source.GOOGLE_DRIVE, external_key=key
                ),
                occurred_at=occurred_at(m, observed_at),
                payload=payload,
                identity=(digest,),
                observed_at=observed_at,
            )
        )
    return events
