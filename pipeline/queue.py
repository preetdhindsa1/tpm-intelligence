"""Queue abstraction: one interface, Redis Streams locally and Pub/Sub in the cloud.

Two layers:

* :class:`Transport`: the minimal byte-level contract each backend implements
  (publish, pull, ack, nack). Backends live in ``pipeline.redis_streams`` and
  ``pipeline.pubsub``.
* :class:`EventPublisher` / :class:`EventConsumer`: typed :class:`NormalizedEvent`
  handling on top of any transport, with OpenTelemetry trace context carried in message
  attributes (see ``pipeline.tracing``).

Delivery is **at-least-once**. Handlers must be idempotent (``event_id`` is
deterministic for that reason). A handler exception means *nack*: the message is
redelivered and, after ``max_delivery_attempts``, moved to the dead-letter topic.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from opentelemetry import metrics
from opentelemetry.trace import Status, StatusCode

from pipeline.events import NormalizedEvent
from pipeline.tracing import consume_span, inject_context, publish_span

logger = logging.getLogger(__name__)

EVENTS_TOPIC = "normalized-events"
DEFAULT_MAX_DELIVERY_ATTEMPTS = 5

_meter = metrics.get_meter(__name__)
_published = _meter.create_counter("queue.messages.published", unit="{message}")
_processed = _meter.create_counter("queue.messages.processed", unit="{message}")
_failed = _meter.create_counter("queue.messages.failed", unit="{message}")
_dead_lettered = _meter.create_counter("queue.messages.dead_lettered", unit="{message}")
_duration = _meter.create_histogram("queue.message.process.duration", unit="s")


@dataclass(frozen=True)
class ReceivedMessage:
    """A message pulled from a subscription, not yet acknowledged."""

    message_id: str
    data: bytes
    attributes: Mapping[str, str]
    delivery_attempt: int
    ack_id: str


class Transport(Protocol):
    """Byte-level queue backend."""

    system: str  # OTel ``messaging.system`` value, e.g. "redis" or "gcp_pubsub"

    def publish(self, topic: str, data: bytes, attributes: Mapping[str, str]) -> str:
        """Publish one message; return its backend message ID."""
        ...

    def pull(
        self, topic: str, subscription: str, max_messages: int, timeout_s: float
    ) -> list[ReceivedMessage]:
        """Return up to ``max_messages``, waiting at most ``timeout_s`` for the first."""
        ...

    def ack(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Mark a message as processed."""
        ...

    def nack(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Return a message for redelivery."""
        ...

    def dead_letter(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Move a message that keeps failing out of the main subscription."""
        ...


def _event_attributes(event: NormalizedEvent) -> dict[str, str]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": str(event.schema_version),
        "source": event.source.value,
    }


@dataclass
class EventPublisher:
    """Publishes :class:`NormalizedEvent` with the current trace context attached."""

    transport: Transport
    topic: str = EVENTS_TOPIC

    def publish(self, event: NormalizedEvent) -> str:
        """Publish ``event`` inside a PRODUCER span; return the backend message ID."""
        attributes = _event_attributes(event)
        with publish_span(self.transport.system, self.topic, event) as span:
            inject_context(attributes)
            message_id = self.transport.publish(self.topic, event.to_bytes(), attributes)
            span.set_attribute("messaging.message.id", message_id)
        _published.add(1, {"topic": self.topic, "event_type": event.event_type})
        return message_id


Handler = Callable[[NormalizedEvent], None]


@dataclass
class EventConsumer:
    """Pulls events and runs ``handler`` for each inside a CONSUMER span.

    The span continues the trace started by the publisher, so one trace covers
    collector -> queue -> worker.
    """

    transport: Transport
    subscription: str
    handler: Handler
    topic: str = EVENTS_TOPIC
    max_delivery_attempts: int = DEFAULT_MAX_DELIVERY_ATTEMPTS
    _stats: dict[str, int] = field(default_factory=lambda: {"ok": 0, "failed": 0, "dead": 0})

    def poll_once(self, max_messages: int = 10, timeout_s: float = 1.0) -> int:
        """Pull one batch and process it; return how many messages were handled OK."""
        messages = self.transport.pull(self.topic, self.subscription, max_messages, timeout_s)
        return sum(self._process(message) for message in messages)

    def _process(self, message: ReceivedMessage) -> bool:
        labels = {"topic": self.topic, "event_type": message.attributes.get("event_type", "")}
        start = time.perf_counter()
        with consume_span(self.transport.system, self.topic, self.subscription, message) as span:
            try:
                event = NormalizedEvent.from_bytes(message.data)
                self.handler(event)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                _failed.add(1, labels)
                self._stats["failed"] += 1
                if message.delivery_attempt >= self.max_delivery_attempts:
                    logger.error(
                        "dead-lettering message after repeated failures",
                        extra={
                            "message_id": message.message_id,
                            "attempts": message.delivery_attempt,
                        },
                    )
                    self.transport.dead_letter(self.topic, self.subscription, message)
                    _dead_lettered.add(1, labels)
                    self._stats["dead"] += 1
                else:
                    logger.warning(
                        "handler failed; message will be redelivered",
                        extra={
                            "message_id": message.message_id,
                            "attempt": message.delivery_attempt,
                        },
                        exc_info=True,
                    )
                    self.transport.nack(self.topic, self.subscription, message)
                return False
            self.transport.ack(self.topic, self.subscription, message)
        _processed.add(1, labels)
        _duration.record(time.perf_counter() - start, labels)
        self._stats["ok"] += 1
        return True

    @property
    def stats(self) -> Mapping[str, int]:
        """Counts of processed / failed / dead-lettered messages in this process."""
        return dict(self._stats)
