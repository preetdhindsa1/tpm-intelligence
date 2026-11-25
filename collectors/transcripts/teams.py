"""Microsoft Teams meeting transcripts via Microsoft Graph (ADR-0030). Not yet live-verified.

App registration with the application permission ``OnlineMeetingTranscript.Read.All``
(``MS_TENANT_ID``, ``MS_CLIENT_ID``, ``MS_CLIENT_SECRET``). The tenant admin must enable
Graph access to transcripts and grant an application access policy to the organizer
(``New-CsApplicationAccessPolicy`` / ``Grant-CsApplicationAccessPolicy``). Lists with
``getAllTranscripts`` for one organizer and reads each transcript's content as WebVTT.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from collectors.http import HttpClient
from collectors.transcripts.model import Transcript, parse_vtt

GRAPH = "https://graph.microsoft.com/v1.0"


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def item_to_transcript(item: dict[str, Any], vtt: str) -> Transcript:
    """A ``callTranscript`` resource plus its VTT content."""
    created = _parse_time(item["createdDateTime"])
    ended = _parse_time(item["endDateTime"]) if item.get("endDateTime") else created
    return Transcript(
        meeting_id=str(item.get("meetingId") or item["id"]),
        title="Teams meeting",
        started_at=created,
        ended_at=max(created, ended),
        cues=tuple(parse_vtt(vtt)),
    )


class TeamsReader:
    """Reads transcripts for ``kind: teams_organizer`` sources."""

    def __init__(
        self, tenant_id: str, client_id: str, client_secret: str, http: HttpClient | None = None
    ) -> None:
        self._http = http or HttpClient(GRAPH)
        token = self._http.request(
            "POST",
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        ).json()
        self._auth = {"Authorization": f"Bearer {token['access_token']}"}

    def transcripts(self, organizer: str, since: datetime, now: datetime) -> Iterator[Transcript]:
        url: str | None = (
            f"{GRAPH}/users/{organizer}/onlineMeetings/getAllTranscripts("
            f"meetingOrganizerUserId='{organizer}',startDateTime={_iso(since)},endDateTime={_iso(now)})"
        )
        while url:
            body = self._http.get(url, headers=self._auth).json()
            for item in body.get("value", []):
                content = item.get("transcriptContentUrl") or (
                    f"{GRAPH}/users/{organizer}/onlineMeetings/{item['meetingId']}/transcripts/{item['id']}/content"
                )
                vtt = self._http.get(content, headers={**self._auth, "Accept": "text/vtt"}).text
                yield item_to_transcript(item, vtt)
            url = body.get("@odata.nextLink")

    def close(self) -> None:
        self._http.close()
