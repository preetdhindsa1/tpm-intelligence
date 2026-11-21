"""In-memory transport with the same semantics as the real backends.

For unit tests and single-process demos only: not durable, not shared across processes.
"""

from __future__ import annotations

import itertools
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass, field

from pipeline.queue import ReceivedMessage


@dataclass
class _Stored:
    message_id: str
    data: bytes
    attributes: dict[str, str]
    attempts: int = 0


@dataclass
class InMemoryTransport:
    """Every subscription sees every message published to its topic (fan-out)."""

    system: str = "memory"
    _ids: itertools.count[int] = field(default_factory=lambda: itertools.count(1))
    _log: dict[str, list[_Stored]] = field(default_factory=lambda: defaultdict(list))
    _queues: dict[tuple[str, str], deque[_Stored]] = field(default_factory=dict)
    _in_flight: dict[tuple[str, str], dict[str, _Stored]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    dead_letters: dict[str, list[ReceivedMessage]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def _queue(self, topic: str, subscription: str) -> deque[_Stored]:
        key = (topic, subscription)
        if key not in self._queues:
            # Like a Redis group created at ID 0: start with the full history.
            self._queues[key] = deque(
                _Stored(m.message_id, m.data, dict(m.attributes)) for m in self._log[topic]
            )
        return self._queues[key]

    def publish(self, topic: str, data: bytes, attributes: Mapping[str, str]) -> str:
        """Append to the topic log and to every existing subscription."""
        message_id = str(next(self._ids))
        self._log[topic].append(_Stored(message_id, data, dict(attributes)))
        for (t, _sub), queue in self._queues.items():
            if t == topic:
                queue.append(_Stored(message_id, data, dict(attributes)))
        return message_id

    def pull(
        self, topic: str, subscription: str, max_messages: int, timeout_s: float
    ) -> list[ReceivedMessage]:
        """Return immediately with what is queued (``timeout_s`` is ignored)."""
        queue = self._queue(topic, subscription)
        out: list[ReceivedMessage] = []
        while queue and len(out) < max_messages:
            stored = queue.popleft()
            stored.attempts += 1
            self._in_flight[(topic, subscription)][stored.message_id] = stored
            out.append(
                ReceivedMessage(
                    message_id=stored.message_id,
                    data=stored.data,
                    attributes=dict(stored.attributes),
                    delivery_attempt=stored.attempts,
                    ack_id=stored.message_id,
                )
            )
        return out

    def ack(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Forget the in-flight message."""
        self._in_flight[(topic, subscription)].pop(message.ack_id, None)

    def nack(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Put the message back at the front of the queue."""
        stored = self._in_flight[(topic, subscription)].pop(message.ack_id, None)
        if stored is not None:
            self._queue(topic, subscription).appendleft(stored)

    def dead_letter(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Record the message as dead-lettered and drop it."""
        self.dead_letters[topic].append(message)
        self.ack(topic, subscription, message)

    def pending(self, topic: str, subscription: str) -> int:
        """Queued plus in-flight messages for a subscription."""
        return len(self._queue(topic, subscription)) + len(self._in_flight[(topic, subscription)])
