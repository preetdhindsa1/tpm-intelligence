"""Live-update notifications from the worker to the API (for SSE).

The worker publishes one small message per stored event, with the W3C trace context of
the event it just stored: on a Redis channel when it runs as its own service (local
Docker), or in-process when the API runs it (cloud, ADR-0017). The API debounces bursts
(a backfill stores thousands of events) and hands the first message's trace context to
the SSE handler, so the API's recompute joins the trace that started in the collector,
with the first event's source times so the push can be timed end to end (P3-M5).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from pipeline.notify import CHANNEL, Notice, notice_of

HEARTBEAT_S = 15.0
DEBOUNCE_S = 1.0


def push_timing(notice: Notice, pushed_at: datetime) -> dict[str, object]:
    """Seconds from the first event's source time and collector time to the push (P3-M5).

    ``occurred_at`` is the source's clock (GitHub, whole seconds), so the first figure is
    accurate to about a second and assumes the clocks agree.
    """
    timing: dict[str, object] = {"event_id": notice.event_id, "batched": notice.batched}
    if notice.occurred_at is not None:
        timing["seconds_since_occurred"] = round(
            (pushed_at - notice.occurred_at).total_seconds(), 2
        )
    if notice.observed_at is not None:
        timing["seconds_since_observed"] = round(
            (pushed_at - notice.observed_at).total_seconds(), 2
        )
    return timing


class Updates(Protocol):
    """Yields a :class:`Notice` per (debounced) update, or None as a heartbeat."""

    def subscribe(
        self, is_disconnected: Callable[[], Awaitable[bool]]
    ) -> AsyncIterator[Notice | None]:
        """Iterate until the client disconnects."""
        ...


async def _debounced(
    queue: asyncio.Queue[str],
    is_disconnected: Callable[[], Awaitable[bool]],
    heartbeat_s: float,
    debounce_s: float,
) -> AsyncIterator[Notice | None]:
    while not await is_disconnected():
        try:
            first = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
        except TimeoutError:
            yield None
            continue
        await asyncio.sleep(debounce_s)
        batched = 1
        while not queue.empty():  # coalesce the burst
            queue.get_nowait()
            batched += 1
        yield notice_of(first, batched)


@dataclass
class InMemoryUpdates:
    """Updates within one process: tests, and the cloud API running the worker in-process.

    ``publish`` may be called from any thread (the worker runs in its own): each message is
    handed to the subscriber's event loop with ``call_soon_threadsafe``.
    """

    heartbeat_s: float = HEARTBEAT_S
    debounce_s: float = 0.0
    _queues: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]] = field(
        default_factory=list
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def publish(self, message: str) -> None:
        """Deliver to every subscriber."""
        with self._lock:
            targets = list(self._queues)
        for loop, q in targets:
            if not loop.is_closed():
                loop.call_soon_threadsafe(q.put_nowait, message)

    async def subscribe(
        self, is_disconnected: Callable[[], Awaitable[bool]]
    ) -> AsyncIterator[Notice | None]:
        """Iterate debounced updates."""
        queue: asyncio.Queue[str] = asyncio.Queue()
        entry = (asyncio.get_running_loop(), queue)
        with self._lock:
            self._queues.append(entry)
        try:
            async for ctx in _debounced(queue, is_disconnected, self.heartbeat_s, self.debounce_s):
                yield ctx
        finally:
            with self._lock:
                self._queues.remove(entry)


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
    ) -> AsyncIterator[Notice | None]:
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
