"""Meeting-transcript connectors (ADR-0030). Payloads are synthetic, shaped like the
Zoom, Microsoft Graph and Google Meet documented responses; no live accounts yet."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

from collectors.http import HttpClient
from collectors.transcripts.meet import MeetReader
from collectors.transcripts.model import Cue, Transcript, parse_vtt, render
from collectors.transcripts.sync import collect, transcript_event
from collectors.transcripts.teams import TeamsReader
from collectors.transcripts.zoom import ZoomReader
from connectors import load_team
from connectors.schema import MeetSource, TeamConfig, TeamsOrganizerSource, ZoomUserSource
from pipeline.events import ConversationKind, ConversationSegmentObserved, NormalizedEvent, Source

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)

TEAMS_VTT = """WEBVTT

0f1e2d3c-1
00:00:01.000 --> 00:00:04.000
<v Alex Example>We agreed to cut feature X from this release.</v>

0f1e2d3c-2
00:00:04.500 --> 00:00:06.000
<v Sam Sample>Risk: docs may slip a week.</v>

0f1e2d3c-3
00:00:06.500 --> 00:00:07.000
<v Sam Sample>Action on me.</v>
"""

ZOOM_VTT = """WEBVTT

1
00:00:01.200 --> 00:00:03.900
Alex Example: Decision: freeze stays on Friday.

NOTE this is a comment

2
00:00:04.000 --> 00:00:05.000
Sam Sample: Agreed.
"""


def test_vtt_speakers_from_teams_voice_tags_and_zoom_prefixes() -> None:
    assert parse_vtt(TEAMS_VTT)[0] == Cue(
        "Alex Example", "We agreed to cut feature X from this release."
    )
    zoom = parse_vtt(ZOOM_VTT)
    assert [c.speaker for c in zoom] == ["Alex Example", "Sam Sample"]
    assert zoom[0].text == "Decision: freeze stays on Friday."


def test_render_replaces_names_with_speaker_numbers_and_joins_runs() -> None:
    text = render(parse_vtt(TEAMS_VTT))
    assert text == (
        "Speaker 1: We agreed to cut feature X from this release.\n"
        "Speaker 2: Risk: docs may slip a week. Action on me."
    )
    assert "Alex" not in text
    assert "Sam" not in text


def _transcript(cues: tuple[Cue, ...]) -> Transcript:
    start = datetime(2026, 11, 24, 16, 0, tzinfo=UTC)
    return Transcript("m-1", "Release sync", start, start + timedelta(minutes=30), cues)


def test_a_transcript_is_one_meeting_segment_dated_at_the_end() -> None:
    e = transcript_event(
        _transcript(tuple(parse_vtt(ZOOM_VTT))),
        source=Source.ZOOM,
        project="kubernetes",
        container="pm@example.com",
        title="Release team",
        release="v1.38",
        observed_at=NOW,
    )
    assert e is not None
    assert e.subject.external_key == "kubernetes:zoom/pm@example.com/m-1"
    assert e.occurred_at == datetime(2026, 11, 24, 16, 30, tzinfo=UTC)
    p = e.payload
    assert isinstance(p, ConversationSegmentObserved)
    assert p.kind is ConversationKind.MEETING_TRANSCRIPT
    assert p.release_key == "kubernetes:v1.38"
    assert p.text.startswith("Speaker 1: Decision: freeze stays on Friday.")
    assert load_team("kubernetes").owns(e.subject.external_key)
    empty = transcript_event(
        _transcript(()),
        source=Source.ZOOM,
        project="kubernetes",
        container="u",
        title="t",
        release=None,
        observed_at=NOW,
    )
    assert empty is None


def _http(handler: Callable[[httpx.Request], httpx.Response]) -> HttpClient:
    return HttpClient(
        "https://example.invalid", transport=httpx.MockTransport(handler), instrument=False
    )


def test_zoom_reader_lists_recordings_and_downloads_transcripts() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "zoom.us" and req.url.path == "/oauth/token":
            assert req.url.params["grant_type"] == "account_credentials"
            return httpx.Response(200, json={"access_token": "z-tok", "expires_in": 3600})
        assert req.headers["Authorization"] == "Bearer z-tok"
        if req.url.path.endswith("/recordings"):
            return httpx.Response(
                200,
                json={
                    "next_page_token": "",
                    "meetings": [
                        {
                            "uuid": "abc==",
                            "id": 1,
                            "topic": "Release sync",
                            "start_time": "2026-11-24T16:00:00Z",
                            "duration": 30,
                            "recording_files": [
                                {"file_type": "MP4", "download_url": "https://zoom.us/rec/v"},
                                {
                                    "file_type": "TRANSCRIPT",
                                    "download_url": "https://zoom.us/rec/t",
                                },
                            ],
                        },
                        {
                            "uuid": "def==",
                            "id": 2,
                            "topic": "No transcript",
                            "start_time": "2026-11-23T16:00:00Z",
                            "recording_files": [
                                {"file_type": "MP4", "download_url": "https://zoom.us/rec/v2"}
                            ],
                        },
                    ],
                },
            )
        assert req.url.path == "/rec/t"
        return httpx.Response(200, text=ZOOM_VTT)

    reader = ZoomReader("acct", "id", "secret", _http(handler))
    [t] = list(reader.transcripts("pm@example.com", NOW - timedelta(days=10), NOW))
    assert (t.meeting_id, t.title) == ("abc==", "Release sync")
    assert t.ended_at == datetime(2026, 11, 24, 16, 30, tzinfo=UTC)
    assert len(t.cues) == 2


def test_teams_reader_follows_next_links_and_reads_vtt() -> None:
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "login.microsoftonline.com":
            assert b"client_credentials" in req.content
            return httpx.Response(200, json={"access_token": "t-tok"})
        seen.append(str(req.url))
        if "getAllTranscripts" in str(req.url):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "tr1",
                            "meetingId": "mtg1",
                            "createdDateTime": "2026-11-24T16:40:00Z",
                            "transcriptContentUrl": "https://graph.microsoft.com/v1.0/c/tr1",
                        }
                    ],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
                },
            )
        if req.url.path.endswith("/next"):
            return httpx.Response(200, json={"value": []})
        assert req.headers["Accept"] == "text/vtt"
        return httpx.Response(200, text=TEAMS_VTT)

    reader = TeamsReader("tenant", "id", "secret", _http(handler))
    [t] = list(reader.transcripts("organizer-oid", NOW - timedelta(days=30), NOW))
    assert t.meeting_id == "mtg1"
    assert t.ended_at == datetime(2026, 11, 24, 16, 40, tzinfo=UTC)
    assert "meetingOrganizerUserId='organizer-oid'" in seen[0]
    assert seen[-1].endswith("/next")


def test_meet_reader_reads_only_generated_transcripts() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "oauth2.googleapis.com":
            assert b"refresh_token" in req.content
            return httpx.Response(200, json={"access_token": "g-tok"})
        path = req.url.path
        if path == "/v2/conferenceRecords":
            return httpx.Response(
                200,
                json={
                    "conferenceRecords": [
                        {
                            "name": "conferenceRecords/rec1",
                            "startTime": "2026-11-24T16:00:00Z",
                            "endTime": "2026-11-24T16:25:00Z",
                            "space": "spaces/s1",
                        }
                    ]
                },
            )
        if path == "/v2/conferenceRecords/rec1/transcripts":
            return httpx.Response(
                200,
                json={
                    "transcripts": [
                        {
                            "name": "conferenceRecords/rec1/transcripts/t1",
                            "state": "FILE_GENERATED",
                        },
                        {"name": "conferenceRecords/rec1/transcripts/t2", "state": "STARTED"},
                    ]
                },
            )
        assert path == "/v2/conferenceRecords/rec1/transcripts/t1/entries"
        return httpx.Response(
            200,
            json={
                "transcriptEntries": [
                    {
                        "participant": "conferenceRecords/rec1/participants/p1",
                        "text": "Decision: ship Friday.",
                    },
                    {
                        "participant": "conferenceRecords/rec1/participants/p2",
                        "text": "Risk: CI is flaky.",
                    },
                ]
            },
        )

    reader = MeetReader("id", "secret", "refresh", _http(handler))
    [t] = list(reader.transcripts("me", NOW - timedelta(days=30), NOW))
    assert t.meeting_id == "rec1"
    assert render(t.cues) == "Speaker 1: Decision: ship Friday.\nSpeaker 2: Risk: CI is flaky."


@dataclass
class _Publisher:
    events: list[NormalizedEvent] = field(default_factory=list)

    def publish(self, event: NormalizedEvent) -> str:
        self.events.append(event)
        return event.event_id


class _Reader:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def transcripts(self, container: str, since: datetime, now: datetime) -> Iterator[Transcript]:
        if self.fail:
            raise RuntimeError("HTTP 403 No application access policy found for this app.")
        return iter([_transcript(tuple(parse_vtt(TEAMS_VTT)))])


def _team(*sources: ZoomUserSource | TeamsOrganizerSource | MeetSource) -> TeamConfig:
    return load_team("kubernetes").model_copy(update={"conversations": sources})


def test_collect_publishes_each_listed_source_of_one_kind() -> None:
    team = _team(
        TeamsOrganizerSource(kind="teams_organizer", organizer_id="oid-1", title="Release team"),
        ZoomUserSource(kind="zoom_user", user="pm@example.com", title="Zoom"),
    )
    pub = _Publisher()
    stats = collect(team, "teams_organizer", _Reader(), pub, since=timedelta(days=30), now=NOW)
    assert (stats.sources, stats.meetings, stats.published) == (1, 1, 1)
    assert pub.events[0].source is Source.MS_TEAMS
    assert pub.events[0].subject.external_key == "kubernetes:ms_teams/oid-1/m-1"


def test_a_source_that_fails_is_counted_not_fatal() -> None:
    team = _team(MeetSource(kind="google_meet", title="Meet"))
    stats = collect(
        team, "google_meet", _Reader(fail=True), _Publisher(), since=timedelta(days=1), now=NOW
    )
    assert stats.failed == ["google_meet:me"]
