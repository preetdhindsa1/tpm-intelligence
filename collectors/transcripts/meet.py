"""Google Meet transcripts via the Meet REST API (ADR-0030). Not yet live-verified.

User OAuth (``GOOGLE_MEET_CLIENT_ID``, ``GOOGLE_MEET_CLIENT_SECRET``,
``GOOGLE_MEET_REFRESH_TOKEN``) with ``meetings.space.readonly`` (a sensitive scope: the app
needs Google's verification before others can use it). Reads conference records, their
transcripts and the transcript entries, so no restricted Drive scope is needed. Google
deletes records and entries 30 days after the meeting, so run within that window.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from collectors.http import HttpClient
from collectors.transcripts.model import Cue, Transcript

API = "https://meet.googleapis.com/v2"
AUTH_URL = "https://oauth2.googleapis.com/token"


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def record_to_transcript(record: dict[str, Any], entries: list[dict[str, Any]]) -> Transcript:
    """A conference record plus its transcript entries (speaker = participant resource)."""
    start = _parse_time(record["startTime"])
    end = _parse_time(record["endTime"]) if record.get("endTime") else start
    return Transcript(
        meeting_id=str(record["name"]).split("/")[-1],
        title="Google Meet meeting",
        started_at=start,
        ended_at=end,
        cues=tuple(Cue(e.get("participant"), str(e.get("text") or "")) for e in entries),
    )


class MeetReader:
    """Reads transcripts for ``kind: google_meet`` sources (the authorized user's meetings)."""

    def __init__(
        self, client_id: str, client_secret: str, refresh_token: str, http: HttpClient | None = None
    ) -> None:
        self._http = http or HttpClient(API)
        token = self._http.request(
            "POST",
            AUTH_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        ).json()
        self._auth = {"Authorization": f"Bearer {token['access_token']}"}

    def _pages(
        self, path: str, key: str, params: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        token = ""
        while True:
            body = self._http.get(
                f"{API}/{path}",
                headers=self._auth,
                params={**(params or {}), **({"pageToken": token} if token else {})},
            ).json()
            yield from body.get(key, [])
            token = body.get("nextPageToken") or ""
            if not token:
                return

    def transcripts(self, _source: str, since: datetime, now: datetime) -> Iterator[Transcript]:
        start = since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        for record in self._pages(
            "conferenceRecords", "conferenceRecords", {"filter": f'start_time>="{start}"'}
        ):
            for t in self._pages(f"{record['name']}/transcripts", "transcripts"):
                if t.get("state") != "FILE_GENERATED":
                    continue
                entries = list(
                    self._pages(f"{t['name']}/entries", "transcriptEntries", {"pageSize": 100})
                )
                yield record_to_transcript(record, entries)

    def close(self) -> None:
        self._http.close()
