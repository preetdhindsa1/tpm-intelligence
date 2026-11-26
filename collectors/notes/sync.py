"""Collect a team's meeting-notes documents once (ADR-0030)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from opentelemetry import trace

from collectors.notes.normalize import to_events
from collectors.notes.parse import split_meetings, split_retro
from connectors.schema import GoogleDocSource, TeamConfig
from pipeline.events import NormalizedEvent, release_key

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("collectors.notes")


class Fetcher(Protocol):
    def fetch_text(self, document_id: str) -> str: ...

    def document_url(self, document_id: str) -> str: ...


class Publisher(Protocol):
    def publish(self, event: NormalizedEvent) -> str: ...


@dataclass
class Stats:
    documents: int = 0
    meetings: int = 0
    published: int = 0
    failed: list[str] = field(default_factory=list)


def collect(team: TeamConfig, fetcher: Fetcher, publisher: Publisher) -> Stats:
    """Fetch every notes document the team lists and publish one event per meeting.

    Event IDs are deterministic, so running this again publishes duplicates the store
    skips. A document that fails is counted and logged, and the others still run.
    """
    stats = Stats()
    now = datetime.now(UTC)
    for source in (c for c in team.conversations if isinstance(c, GoogleDocSource)):
        with tracer.start_as_current_span("notes.collect_document") as span:
            span.set_attribute("notes.document_id", source.document_id)
            try:
                text = fetcher.fetch_text(source.document_id)
            except Exception:
                logger.exception("notes: could not read document %s", source.document_id)
                stats.failed.append(source.document_id)
                continue
            split = split_retro if source.layout == "retro" else split_meetings
            meetings = split(text)
            events = to_events(
                meetings,
                project=team.project,
                document_id=source.document_id,
                title=source.title,
                url=fetcher.document_url(source.document_id),
                release_key=release_key(team.project, source.release) if source.release else None,
                observed_at=now,
            )
            for event in events:
                publisher.publish(event)
            span.set_attribute("notes.meetings", len(meetings))
            stats.documents += 1
            stats.meetings += len(meetings)
            stats.published += len(events)
    return stats
