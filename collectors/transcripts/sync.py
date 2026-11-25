"""Collect meeting transcripts for a team's listed sources, once (ADR-0030)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from opentelemetry import trace

from collectors.conversation import segment_event
from collectors.transcripts.model import Transcript, render
from connectors.schema import MeetSource, TeamConfig, TeamsOrganizerSource, ZoomUserSource
from pipeline.events import ConversationKind, NormalizedEvent, Source, release_key

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("collectors.transcripts")

# Config kind -> event source; the container is who the meetings belong to.
SOURCE = {
    "zoom_user": Source.ZOOM,
    "teams_organizer": Source.MS_TEAMS,
    "google_meet": Source.GOOGLE_MEET,
}


class Reader(Protocol):
    def transcripts(
        self, container: str, since: datetime, now: datetime
    ) -> Iterator[Transcript]: ...


class Publisher(Protocol):
    def publish(self, event: NormalizedEvent) -> str: ...


@dataclass
class Stats:
    sources: int = 0
    meetings: int = 0
    published: int = 0
    failed: list[str] = field(default_factory=list)


def _container(src: ZoomUserSource | TeamsOrganizerSource | MeetSource) -> str:
    if isinstance(src, ZoomUserSource):
        return src.user
    if isinstance(src, TeamsOrganizerSource):
        return src.organizer_id
    return "me"


def transcript_event(
    t: Transcript,
    *,
    source: Source,
    project: str,
    container: str,
    title: str,
    release: str | None,
    observed_at: datetime,
) -> NormalizedEvent | None:
    """One meeting transcript as a conversation segment, dated when the meeting ended.

    None when there is no speech to keep.
    """
    text = render(t.cues)
    if not text:
        return None
    return segment_event(
        source=source,
        kind=ConversationKind.MEETING_TRANSCRIPT,
        key=f"{project}:{source.value}/{container}/{t.meeting_id}",
        container=container,
        container_title=title,
        heading=f"{title} · {t.title} · {t.started_at:%Y-%m-%d %H:%M} UTC",
        text=text,
        occurred_at=t.ended_at,
        observed_at=observed_at,
        meeting_date=t.started_at.date(),
        release_key=release_key(project, release) if release else None,
    )


def collect(
    team: TeamConfig,
    kind: str,
    reader: Reader,
    publisher: Publisher,
    *,
    since: timedelta,
    now: datetime | None = None,
) -> Stats:
    """Every transcript of the team's ``kind`` sources from the last ``since``.

    Overlapping windows are safe (deterministic event IDs). A source that fails is
    counted and logged; the rest still run.
    """
    stats = Stats()
    now = now or datetime.now(UTC)
    source = SOURCE[kind]
    for src in team.conversations:
        if src.kind != kind or not isinstance(
            src, ZoomUserSource | TeamsOrganizerSource | MeetSource
        ):
            continue
        container = _container(src)
        with tracer.start_as_current_span("transcripts.collect_source") as span:
            span.set_attribute("transcripts.source", source.value)
            try:
                transcripts = list(reader.transcripts(container, now - since, now))
            except Exception:
                logger.exception("transcripts: could not read %s %s", source.value, container)
                stats.failed.append(f"{source.value}:{container}")
                continue
            for t in transcripts:
                event = transcript_event(
                    t,
                    source=source,
                    project=team.project,
                    container=container,
                    title=src.title,
                    release=src.release,
                    observed_at=now,
                )
                if event is not None:
                    publisher.publish(event)
                    stats.published += 1
            span.set_attribute("transcripts.meetings", len(transcripts))
            stats.sources += 1
            stats.meetings += len(transcripts)
    return stats
