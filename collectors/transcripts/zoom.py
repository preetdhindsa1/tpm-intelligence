"""Zoom cloud-recording transcripts (ADR-0030). Not yet live-verified.

Server-to-Server OAuth app (``ZOOM_ACCOUNT_ID``, ``ZOOM_CLIENT_ID``, ``ZOOM_CLIENT_SECRET``)
with read-only recording scopes. Lists a user's cloud recordings
(``GET /v2/users/{user}/recordings``, at most a month per request) and downloads each
``TRANSCRIPT`` file (WebVTT) with the access token. Needs cloud recording with audio
transcripts on the account (expected: a paid plan).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from collectors.http import HttpClient
from collectors.transcripts.model import Transcript, parse_vtt

API = "https://api.zoom.us/v2"
AUTH_URL = "https://zoom.us/oauth/token"


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def meeting_to_transcript(meeting: dict[str, Any], vtt: str) -> Transcript:
    """A listed meeting plus its downloaded VTT."""
    start = _parse_time(meeting["start_time"])
    return Transcript(
        meeting_id=str(meeting.get("uuid") or meeting["id"]),
        title=str(meeting.get("topic") or "Zoom meeting"),
        started_at=start,
        ended_at=start + timedelta(minutes=int(meeting.get("duration") or 0)),
        cues=tuple(parse_vtt(vtt)),
    )


def transcript_file(meeting: dict[str, Any]) -> dict[str, Any] | None:
    """The meeting's transcript file, if Zoom made one."""
    return next(
        (f for f in meeting.get("recording_files", []) if f.get("file_type") == "TRANSCRIPT"), None
    )


class ZoomReader:
    """Reads transcripts for ``kind: zoom_user`` sources."""

    def __init__(
        self, account_id: str, client_id: str, client_secret: str, http: HttpClient | None = None
    ) -> None:
        self._http = http or HttpClient(API)
        token = self._http.request(
            "POST",
            AUTH_URL,
            params={"grant_type": "account_credentials", "account_id": account_id},
            auth=(client_id, client_secret),
        ).json()
        self._auth = {"Authorization": f"Bearer {token['access_token']}"}

    def _meetings(self, user: str, start: datetime, end: datetime) -> Iterator[dict[str, Any]]:
        frm = start
        while frm < end:
            to = min(frm + timedelta(days=30), end)
            page = ""
            while True:
                body = self._http.get(
                    f"{API}/users/{user}/recordings",
                    headers=self._auth,
                    params={
                        "from": frm.date().isoformat(),
                        "to": to.date().isoformat(),
                        "page_size": 300,
                        **({"next_page_token": page} if page else {}),
                    },
                ).json()
                yield from body.get("meetings", [])
                page = body.get("next_page_token") or ""
                if not page:
                    break
            frm = to

    def transcripts(self, user: str, since: datetime, now: datetime) -> Iterator[Transcript]:
        for meeting in self._meetings(user, since, now):
            f = transcript_file(meeting)
            if f is None:
                continue
            vtt = self._http.get(f["download_url"], headers=self._auth).text
            yield meeting_to_transcript(meeting, vtt)

    def close(self) -> None:
        self._http.close()
