"""Meeting-notes collector (ADR-0030), on a trimmed copy of the real Kubernetes v1.38
release-team notes (names replaced by "[name]")."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from collectors.notes.normalize import occurred_at, to_events
from collectors.notes.parse import split_meetings
from collectors.notes.sync import collect
from connectors import load_team
from engine.projection import project
from pipeline.events import (
    ConversationKind,
    ConversationSegmentObserved,
    NormalizedEvent,
    Source,
    SubjectKind,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "notes"
TEXT = (FIXTURE / "k8s-v138-release-meeting-trimmed.txt").read_text(encoding="utf-8")
DOC = "1fkUQyLupx_jkPcXtWmxnmVVVMj7KHRizx_yBRxJMOw0"
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def _events(text: str = TEXT) -> list[NormalizedEvent]:
    return to_events(
        split_meetings(text),
        project="kubernetes",
        document_id=DOC,
        title="Kubernetes v1.38 Release Team Meeting",
        url=f"https://docs.google.com/document/d/{DOC}",
        release_key="kubernetes:v1.38",
        observed_at=NOW,
    )


def test_one_segment_per_real_meeting_heading() -> None:
    meetings = split_meetings(TEXT)
    assert [(m.week, m.meeting_date) for m in meetings] == [
        (13, date(2026, 11, 25)),
        (13, date(2026, 11, 23)),
        (12, date(2026, 11, 18)),
        (8, date(2026, 10, 21)),  # heading inside a bullet
        (10, date(2026, 11, 4)),  # "Weekday" instead of the day name
        (1, date(2026, 9, 2)),  # "Wednesday, 2nd September"
    ]
    assert meetings[1].heading == "Week 13 \u2013 Monday 23 November 2026 Burndown Meeting"


def test_template_and_header_are_not_meetings() -> None:
    texts = " ".join(m.text for m in split_meetings(TEXT))
    assert "Week N" not in texts
    assert "Meeting Update Template" not in texts
    assert "Zoom: Click Here" not in texts


def test_text_is_verbatim_and_ends_at_the_next_heading() -> None:
    first = split_meetings(TEXT)[0]
    assert first.text.startswith("Week 13 \u2013 Wednesday 25 November 2026 Weekly Meeting")
    assert "* Code Freeze exceptions reviewed; two approved." in first.text
    assert "Burndown" not in first.text


def test_events_are_conversation_segments_owned_by_the_team() -> None:
    events = _events()
    assert len(events) == 6
    e = events[0]
    assert e.source is Source.GOOGLE_DRIVE
    assert e.subject.kind is SubjectKind.CONVERSATION
    assert e.subject.external_key == f"kubernetes:notes/{DOC}/2026-11-25/1"
    assert isinstance(e.payload, ConversationSegmentObserved)
    assert e.payload.kind is ConversationKind.MEETING_NOTES
    assert e.payload.release_key == "kubernetes:v1.38"
    assert load_team("kubernetes").owns(e.subject.external_key)
    assert NormalizedEvent.from_bytes(e.to_bytes()) == e


def test_notes_count_as_known_at_the_end_of_the_meeting_day() -> None:
    meeting = split_meetings(TEXT)[2]  # 18 November
    assert occurred_at(meeting, NOW) == datetime(2026, 11, 19, tzinfo=UTC)


def test_ids_are_stable_and_an_edit_is_a_new_event() -> None:
    assert [e.event_id for e in _events()] == [e.event_id for e in _events()]
    edited = _events(TEXT.replace("two approved", "three approved"))
    assert edited[0].event_id != _events()[0].event_id
    assert edited[1].event_id == _events()[1].event_id  # other meetings unchanged


def test_projection_ignores_conversations() -> None:
    world = project(_events(), NOW)
    assert world.features == {}
    assert world.pull_requests == {}


@dataclass
class _Publisher:
    events: list[NormalizedEvent] = field(default_factory=list)

    def publish(self, event: NormalizedEvent) -> str:
        self.events.append(event)
        return event.event_id


class _Fetcher:
    def __init__(self, text: str | None) -> None:
        self.text = text

    def fetch_text(self, document_id: str) -> str:
        if self.text is None:
            raise RuntimeError("HTTP 403")
        return self.text

    def document_url(self, document_id: str) -> str:
        return f"https://docs.google.com/document/d/{document_id}"


def test_collect_publishes_every_meeting_of_every_listed_document() -> None:
    team = load_team("kubernetes")
    assert [c.document_id for c in team.conversations] == [DOC]
    pub = _Publisher()
    stats = collect(team, _Fetcher(TEXT), pub)
    assert (stats.documents, stats.meetings, stats.published, stats.failed) == (1, 6, 6, [])
    assert pub.events[0].payload.release_key == "kubernetes:v1.38"  # type: ignore[union-attr]


def test_a_failed_document_is_counted_not_fatal() -> None:
    stats = collect(load_team("kubernetes"), _Fetcher(None), _Publisher())
    assert stats.failed == [DOC]
    assert stats.published == 0
