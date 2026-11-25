"""Slack collector (ADR-0030). Payloads are synthetic, shaped like Slack's documented
``conversations.history`` / ``conversations.replies`` responses (no live workspace yet)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from collectors.http import HttpClient
from collectors.slack.client import API, SlackClient, SlackError
from collectors.slack.normalize import is_conversation, message_event, ts_to_datetime
from collectors.slack.sync import collect
from connectors import load_team
from connectors.schema import SlackChannelSource, TeamConfig
from pipeline.events import ConversationKind, ConversationSegmentObserved, NormalizedEvent, Source

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
PARENT = {"ts": "1764064800.000100", "user": "U1", "text": "Decision: we cut feature X from 4.5.0.",
          "reply_count": 1, "thread_ts": "1764064800.000100"}  # fmt: skip
REPLY = {"ts": "1764065400.000200", "user": "U2", "text": "Risk: docs may slip a week.",
         "thread_ts": "1764064800.000100"}  # fmt: skip
JOIN = {
    "ts": "1764061200.000300",
    "subtype": "channel_join",
    "user": "U3",
    "text": "<@U3> has joined",
}
BOT = {"ts": "1764061300.000400", "bot_id": "B1", "text": "CI is green"}


def _team() -> TeamConfig:
    src = SlackChannelSource(
        kind="slack_channel", channel_id="C0RELEASE", title="#release", release="v1.38"
    )
    return load_team("kubernetes").model_copy(update={"conversations": (src,)})


def test_only_peoples_messages_count() -> None:
    assert is_conversation(PARENT)
    assert is_conversation(REPLY)
    assert not is_conversation(JOIN)
    assert not is_conversation(BOT)
    assert not is_conversation({"ts": "1.0", "text": "  "})


def test_a_message_becomes_one_chat_segment() -> None:
    e = message_event(REPLY, project="kubernetes", channel="C0RELEASE", title="#release",
                      release_key="kubernetes:v1.38", observed_at=NOW)  # fmt: skip
    assert e.source is Source.SLACK
    assert e.subject.external_key == "kubernetes:slack/C0RELEASE/1764065400.000200"
    assert e.occurred_at == ts_to_datetime("1764065400.000200")
    p = e.payload
    assert isinstance(p, ConversationSegmentObserved)
    assert p.kind is ConversationKind.CHAT
    assert p.text == "Risk: docs may slip a week."
    assert p.heading.endswith("· thread reply")
    assert load_team("kubernetes").owns(e.subject.external_key)
    changed = {**REPLY, "text": "Risk: docs may slip two weeks."}
    edited = message_event(
        changed,
        project="kubernetes",
        channel="C0RELEASE",
        title="#release",
        release_key=None,
        observed_at=NOW,
    )
    assert edited.event_id != e.event_id


@dataclass
class _Publisher:
    events: list[NormalizedEvent] = field(default_factory=list)

    def publish(self, event: NormalizedEvent) -> str:
        self.events.append(event)
        return event.event_id


class _Reader:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.oldest: str | None = None

    def history(self, channel: str, oldest: str) -> Iterator[dict[str, Any]]:
        if self.fail:
            raise SlackError("conversations.history: not_in_channel")
        self.oldest = oldest
        return iter([PARENT, JOIN, BOT])

    def replies(self, channel: str, thread_ts: str) -> Iterator[dict[str, Any]]:
        return iter([PARENT, REPLY])  # Slack returns the parent first


def test_collect_reads_threads_without_duplicating_the_parent() -> None:
    reader, pub = _Reader(), _Publisher()
    stats = collect(_team(), reader, pub, since=timedelta(days=14), now=NOW)
    texts = [e.payload.text for e in pub.events]  # type: ignore[union-attr]
    assert texts == ["Decision: we cut feature X from 4.5.0.", "Risk: docs may slip a week."]
    assert (stats.channels, stats.messages, stats.published, stats.failed) == (1, 4, 2, [])
    assert reader.oldest == f"{(NOW - timedelta(days=14)).timestamp():.6f}"
    assert pub.events[0].payload.release_key == "kubernetes:v1.38"  # type: ignore[union-attr]


def test_a_channel_the_bot_cannot_read_is_counted_not_fatal() -> None:
    stats = collect(_team(), _Reader(fail=True), _Publisher(), since=timedelta(days=1), now=NOW)
    assert stats.failed == ["C0RELEASE"]
    assert stats.published == 0


def _client(pages: list[dict[str, Any]], seen: list[httpx.Request]) -> SlackClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=pages[len(seen) - 1])

    return SlackClient(
        "xoxb-test", HttpClient(API, transport=httpx.MockTransport(handler), instrument=False)
    )


def test_client_follows_cursors() -> None:
    seen: list[httpx.Request] = []
    pages = [
        {"ok": True, "messages": [PARENT], "response_metadata": {"next_cursor": "c2"}},
        {"ok": True, "messages": [REPLY], "response_metadata": {"next_cursor": ""}},
    ]
    msgs = list(_client(pages, seen).history("C0RELEASE", "0"))
    assert [m["ts"] for m in msgs] == [PARENT["ts"], REPLY["ts"]]
    assert seen[0].url.path == "/api/conversations.history"
    assert seen[1].url.params["cursor"] == "c2"


def test_client_raises_slack_errors() -> None:
    with pytest.raises(SlackError, match="not_in_channel"):
        list(_client([{"ok": False, "error": "not_in_channel"}], []).history("C0RELEASE", "0"))
