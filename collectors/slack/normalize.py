"""Slack messages → conversation events (ADR-0030). Pure, no I/O."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from collectors.conversation import segment_event
from pipeline.events import ConversationKind, NormalizedEvent, Source

# Join/leave/topic notices and the like are not conversation; threads broadcast to the
# channel are.
_KEEP_SUBTYPES = {None, "thread_broadcast"}


def ts_to_datetime(ts: str) -> datetime:
    """Slack ``ts`` ("1732530000.123456") as an aware UTC datetime."""
    return datetime.fromtimestamp(float(ts), tz=UTC)


def is_conversation(message: dict[str, Any]) -> bool:
    """People's messages only: no channel notices, no bot posts, nothing empty."""
    return (
        message.get("subtype") in _KEEP_SUBTYPES
        and not message.get("bot_id")
        and bool((message.get("text") or "").strip())
    )


def message_event(
    message: dict[str, Any],
    *,
    project: str,
    channel: str,
    title: str,
    release_key: str | None,
    observed_at: datetime,
) -> NormalizedEvent:
    """One message. The key carries the channel and ``ts``, which Slack keeps stable."""
    ts = str(message["ts"])
    at = ts_to_datetime(ts)
    thread = message.get("thread_ts")
    heading = f"{title} · {at:%Y-%m-%d %H:%M} UTC" + (
        " · thread reply" if thread and thread != ts else ""
    )
    return segment_event(
        source=Source.SLACK,
        kind=ConversationKind.CHAT,
        key=f"{project}:slack/{channel}/{ts}",
        container=channel,
        container_title=title,
        heading=heading,
        text=str(message["text"]),
        occurred_at=at,
        observed_at=observed_at,
        release_key=release_key,
        url=f"https://slack.com/app_redirect?channel={channel}&message_ts={ts}",
    )
