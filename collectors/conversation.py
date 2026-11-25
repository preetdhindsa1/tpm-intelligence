"""One builder for every conversation connector's events (ADR-0030). Pure, no I/O.

Slack, Zoom, Microsoft Teams, Google Meet and meeting-notes documents all publish
``conversation.segment_observed``, so the RAID extractor never depends on the source.
The text is kept verbatim (quotes are checked against it word for word) and its hash
is part of the event identity, so an edited message or transcript is a new event.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

from pipeline.events import (
    ConversationKind,
    ConversationSegmentObserved,
    NormalizedEvent,
    Source,
    SubjectKind,
    SubjectRef,
    new_event,
)


def sha256(text: str) -> str:
    """Hex SHA-256 of the text, as stored in ``text_sha256``."""
    return hashlib.sha256(text.encode()).hexdigest()


def segment_event(
    *,
    source: Source,
    kind: ConversationKind,
    key: str,
    container: str,
    container_title: str,
    heading: str,
    text: str,
    occurred_at: datetime,
    observed_at: datetime,
    meeting_date: date | None = None,
    release_key: str | None = None,
    url: str | None = None,
) -> NormalizedEvent:
    """A conversation segment. ``key`` must start with ``<project>:`` so the team owns it."""
    digest = sha256(text)
    return new_event(
        source=source,
        subject=SubjectRef(kind=SubjectKind.CONVERSATION, source=source, external_key=key),
        occurred_at=occurred_at.astimezone(UTC),
        payload=ConversationSegmentObserved(
            kind=kind,
            container=container,
            container_title=container_title,
            heading=heading,
            text=text,
            text_sha256=digest,
            meeting_date=meeting_date,
            release_key=release_key,
            url=url,
        ),
        identity=(digest,),
        observed_at=observed_at,
    )
