"""Live-update notifications from the worker to the API (for SSE).

The worker publishes one small message per stored event on a Redis channel, with the W3C
trace context of the event it just stored. The API debounces bursts (a backfill stores
thousands of events) and hands the first message's trace context to the SSE handler, so
the API's recompute joins the trace that started in the collector.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from opentelemetry.context import Context

from pipeline.notify import CHANNEL, context_of

HEARTBEAT_S = 15.0
DEBOUNCE_S = 1.0


class Updates(Protocol):
    """Yields a trace context per (debounced) update, or None as a heartbeat."""

    def subscribe(
        self, is_disconnected: Callable[[], Awaitable[bool]]
    ) -> AsyncIterator[Context | None]:
        """Iterate until the client disconnects."""
        ...


async def _debounced(
    queue: asyncio.Queue[str],
    is_disconnected: Callable[[], Awaitable[bool]],
    heartbeat_s: float,
    debounce_s: float,
) -> AsyncIterator[Context | None]:
    while not await is_disconnected():
        try:
            first = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
        except TimeoutError:
            yield None
            continue
        await asyncio.sleep(debounce_s)
        while not queue.empty():  # coalesce the burst
            queue.get_nowait()
        yield context_of(first)


@dataclass
class InMemoryUpdates:
    """For tests: call ``publish`` to simulate the worker."""

    heartbeat_s: float = HEARTBEAT_S
    debounce_s: float = 0.0
    _queues: list[asyncio.Queue[str]] = field(default_factory=list)

    def publish(self, message: str) -> None:
        """Deliver to every subscriber."""
        for q in self._queues:
            q.put_nowait(message)

    async def subscribe(
        self, is_disconnected: Callable[[], Awaitable[bool]]
    ) -> AsyncIterator[Context | None]:
        """Iterate debounced updates."""
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._queues.append(queue)
        try:
            async for ctx in _debounced(queue, is_disconnected, self.heartbeat_s, self.debounce_s):
                yield ctx
        finally:
            self._queues.remove(queue)


class RedisUpdates:
    """Redis pub/sub subscriber."""

    def __init__(
        self, url: str, *, heartbeat_s: float = HEARTBEAT_S, debounce_s: float = DEBOUNCE_S
    ) -> None:
        self._url = url
        self._heartbeat_s = heartbeat_s
        self._debounce_s = debounce_s

    async def subscribe(
        self, is_disconnected: Callable[[], Awaitable[bool]]
    ) -> AsyncIterator[Context | None]:
        """Iterate debounced updates from the Redis channel."""
        import redis.asyncio as aioredis

        client = aioredis.Redis.from_url(self._url)
        pubsub = client.pubsub()
        await pubsub.subscribe(CHANNEL)
        queue: asyncio.Queue[str] = asyncio.Queue()

        async def pump() -> None:
            async for msg in pubsub.listen():
                if msg.get("type") == "message":
                    data = msg["data"]
                    queue.put_nowait(data.decode() if isinstance(data, bytes) else str(data))

        task = asyncio.create_task(pump())
        try:
            async for ctx in _debounced(
                queue, is_disconnected, self._heartbeat_s, self._debounce_s
            ):
                yield ctx
        finally:
            task.cancel()
            await pubsub.unsubscribe(CHANNEL)
            await client.aclose()
