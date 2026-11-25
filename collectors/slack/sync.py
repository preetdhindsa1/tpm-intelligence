"""Collect the Slack channels a team lists, once (ADR-0030)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from opentelemetry import trace

from collectors.slack.normalize import is_conversation, message_event
from connectors.schema import SlackChannelSource, TeamConfig
from pipeline.events import NormalizedEvent, release_key

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("collectors.slack")


class Reader(Protocol):
    def history(self, channel: str, oldest: str) -> Iterator[dict[str, Any]]: ...

    def replies(self, channel: str, thread_ts: str) -> Iterator[dict[str, Any]]: ...


class Publisher(Protocol):
    def publish(self, event: NormalizedEvent) -> str: ...


@dataclass
class Stats:
    channels: int = 0
    messages: int = 0
    published: int = 0
    failed: list[str] = field(default_factory=list)


def collect(
    team: TeamConfig,
    reader: Reader,
    publisher: Publisher,
    *,
    since: timedelta,
    now: datetime | None = None,
) -> Stats:
    """Messages (and their thread replies) from the last ``since``, one event each.

    Event IDs are deterministic, so overlapping windows publish duplicates the store
    skips. A channel that fails (e.g. the bot was not added) is counted, the rest run.
    """
    stats = Stats()
    now = now or datetime.now(UTC)
    oldest = f"{(now - since).timestamp():.6f}"
    for src in (c for c in team.conversations if isinstance(c, SlackChannelSource)):
        rel = release_key(team.project, src.release) if src.release else None
        with tracer.start_as_current_span("slack.collect_channel") as span:
            span.set_attribute("slack.channel", src.channel_id)
            try:
                messages = []
                for msg in reader.history(src.channel_id, oldest):
                    messages.append(msg)
                    if int(msg.get("reply_count") or 0) > 0:
                        replies = list(reader.replies(src.channel_id, str(msg["ts"])))
                        messages.extend(r for r in replies if r.get("ts") != msg.get("ts"))
            except Exception:
                logger.exception("slack: could not read channel %s", src.channel_id)
                stats.failed.append(src.channel_id)
                continue
            kept = [m for m in messages if is_conversation(m)]
            for m in kept:
                publisher.publish(
                    message_event(m, project=team.project, channel=src.channel_id, title=src.title,
                                  release_key=rel, observed_at=now)
                )  # fmt: skip
            span.set_attribute("slack.messages", len(kept))
            stats.channels += 1
            stats.messages += len(messages)
            stats.published += len(kept)
    return stats
