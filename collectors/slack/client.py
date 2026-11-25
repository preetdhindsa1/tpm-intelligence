"""Read-only Slack Web API client (ADR-0030).

Needs a bot token (``SLACK_BOT_TOKEN``) with ``channels:history`` (and ``groups:history``
for private channels); the bot reads only channels it has been added to. Calls go through
the shared HTTP client, which honours ``429`` and ``Retry-After``
(``conversations.history`` is Tier 3, "50+ per minute"). Slack reports most errors as
HTTP 200 with ``"ok": false``, raised here as :class:`SlackError`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from collectors.http import HttpClient

API = "https://slack.com/api"
PAGE = 200


class SlackError(Exception):
    """Slack answered ``ok: false`` (e.g. ``not_in_channel``, ``invalid_auth``)."""


class SlackClient:
    """Pages through channel history and thread replies."""

    def __init__(self, token: str, http: HttpClient | None = None) -> None:
        self._http = http or HttpClient(API, headers={"Authorization": f"Bearer {token}"})

    def _get(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = self._http.get(f"/{method}", params=params).json()
        if not body.get("ok"):
            raise SlackError(f"{method}: {body.get('error', 'unknown error')}")
        return body

    def _pages(self, method: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        cursor = None
        while True:
            body = self._get(
                method, {**params, "limit": PAGE, **({"cursor": cursor} if cursor else {})}
            )
            yield from body.get("messages", [])
            cursor = (body.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return

    def history(self, channel: str, oldest: str) -> Iterator[dict[str, Any]]:
        """Top-level messages in ``channel`` newer than ``oldest`` (a Slack ``ts``)."""
        return self._pages("conversations.history", {"channel": channel, "oldest": oldest})

    def replies(self, channel: str, thread_ts: str) -> Iterator[dict[str, Any]]:
        """A thread: its parent first, then the replies."""
        return self._pages("conversations.replies", {"channel": channel, "ts": thread_ts})

    def close(self) -> None:
        self._http.close()
