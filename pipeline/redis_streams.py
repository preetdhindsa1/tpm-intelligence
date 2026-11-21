"""Redis Streams transport (local development and tests).

Mapping to Pub/Sub concepts:

* topic        -> stream ``tpm:stream:<topic>``
* subscription -> consumer group on that stream (created from ID ``0`` so a worker
  that starts after the collector still sees earlier messages)
* ack          -> ``XACK``
* nack         -> ``XCLAIM ... IDLE <visibility> JUSTID`` so the message becomes
  eligible for reclaim straight away (JUSTID does not bump the delivery counter)
* redelivery   -> ``XAUTOCLAIM`` of messages idle longer than the visibility timeout;
  Redis counts deliveries, which gives us ``delivery_attempt``
* dead letter  -> copy to ``tpm:stream:<topic>:dead-letter`` then ``XACK``
"""

from __future__ import annotations

import os
import socket
from collections.abc import Mapping
from typing import Any, cast

import redis

from pipeline.queue import ReceivedMessage

_ATTR_PREFIX = b"a:"
_DATA_FIELD = b"data"


def stream_key(topic: str) -> str:
    """Redis key holding ``topic``."""
    return f"tpm:stream:{topic}"


def dead_letter_key(topic: str) -> str:
    """Redis key holding dead-lettered messages for ``topic``."""
    return f"{stream_key(topic)}:dead-letter"


class RedisStreamsTransport:
    """:class:`pipeline.queue.Transport` backed by Redis Streams."""

    system = "redis"

    def __init__(
        self,
        client: redis.Redis,
        *,
        consumer_name: str | None = None,
        visibility_timeout_s: float = 60.0,
        max_stream_length: int = 500_000,
    ) -> None:
        self._r = client
        self._consumer = consumer_name or f"{socket.gethostname()}-{os.getpid()}"
        self._visibility_ms = int(visibility_timeout_s * 1000)
        self._maxlen = max_stream_length
        self._groups: set[tuple[str, str]] = set()

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> RedisStreamsTransport:
        """Connect using a ``redis://`` URL."""
        return cls(redis.Redis.from_url(url, decode_responses=False), **kwargs)

    # ------------------------------------------------------------ publish

    def publish(self, topic: str, data: bytes, attributes: Mapping[str, str]) -> str:
        """``XADD`` with the body and one field per attribute."""
        fields: dict[bytes, bytes] = {_DATA_FIELD: data}
        for key, value in attributes.items():
            fields[_ATTR_PREFIX + key.encode()] = value.encode()
        message_id = self._r.xadd(
            stream_key(topic),
            fields,  # type: ignore[arg-type]
            maxlen=self._maxlen,
            approximate=True,
        )
        return _decode(message_id)

    # ------------------------------------------------------------ consume

    def _ensure_group(self, topic: str, subscription: str) -> None:
        if (topic, subscription) in self._groups:
            return
        try:
            self._r.xgroup_create(stream_key(topic), subscription, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._groups.add((topic, subscription))

    def pull(
        self, topic: str, subscription: str, max_messages: int, timeout_s: float
    ) -> list[ReceivedMessage]:
        """Reclaim timed-out/nacked messages first, then read new ones."""
        self._ensure_group(topic, subscription)
        key = stream_key(topic)

        reclaimed = self._reclaim(key, subscription, max_messages)
        remaining = max_messages - len(reclaimed)
        if remaining <= 0:
            return reclaimed

        block_ms = max(1, int(timeout_s * 1000)) if not reclaimed else None
        response = self._r.xreadgroup(
            subscription, self._consumer, {key: ">"}, count=remaining, block=block_ms
        )
        fresh = [
            self._to_message(message_id, fields, delivery_attempt=1)
            for _stream, entries in cast(list[Any], response or [])
            for message_id, fields in entries
        ]
        return reclaimed + fresh

    def _reclaim(self, key: str, subscription: str, count: int) -> list[ReceivedMessage]:
        result = self._r.xautoclaim(
            key, subscription, self._consumer, self._visibility_ms, start_id="0-0", count=count
        )
        entries = [(mid, fields) for mid, fields in result[1] if fields is not None]
        messages: list[ReceivedMessage] = []
        for message_id, fields in entries:
            pending = cast(
                list[dict[str, Any]],
                self._r.xpending_range(key, subscription, min=message_id, max=message_id, count=1),
            )
            attempts = int(pending[0]["times_delivered"]) if pending else 1
            messages.append(self._to_message(message_id, fields, delivery_attempt=attempts))
        return messages

    @staticmethod
    def _to_message(
        message_id: bytes | str, fields: Mapping[bytes, bytes], *, delivery_attempt: int
    ) -> ReceivedMessage:
        mid = _decode(message_id)
        attributes = {
            k[len(_ATTR_PREFIX) :].decode(): v.decode()
            for k, v in fields.items()
            if k.startswith(_ATTR_PREFIX)
        }
        return ReceivedMessage(
            message_id=mid,
            data=fields[_DATA_FIELD],
            attributes=attributes,
            delivery_attempt=delivery_attempt,
            ack_id=mid,
        )

    def ack(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """``XACK`` the message."""
        self._r.xack(stream_key(topic), subscription, message.ack_id)

    def nack(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Make the message immediately eligible for reclaim by any consumer."""
        self._r.xclaim(
            stream_key(topic),
            subscription,
            self._consumer,
            min_idle_time=0,
            message_ids=[message.ack_id],
            idle=self._visibility_ms,
            justid=True,
        )

    def dead_letter(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Copy to the dead-letter stream (with failure metadata), then ack."""
        fields: dict[bytes, bytes] = {_DATA_FIELD: message.data}
        for key, value in message.attributes.items():
            fields[_ATTR_PREFIX + key.encode()] = value.encode()
        fields[b"a:dead_letter.subscription"] = subscription.encode()
        fields[b"a:dead_letter.original_id"] = message.message_id.encode()
        fields[b"a:dead_letter.attempts"] = str(message.delivery_attempt).encode()
        self._r.xadd(dead_letter_key(topic), fields)  # type: ignore[arg-type]
        self.ack(topic, subscription, message)

    def backlog(self, topic: str, subscription: str) -> int:
        """Messages delivered but not acked plus not yet delivered (for the backlog alert)."""
        self._ensure_group(topic, subscription)
        for group in self._r.xinfo_groups(stream_key(topic)):
            if _decode(group["name"]) == subscription:
                lag = group.get("lag") or 0
                return int(group["pending"]) + int(lag)
        return 0


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value
