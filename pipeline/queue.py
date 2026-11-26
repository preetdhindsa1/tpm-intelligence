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
import threading
import time
from collections.abc import Callable, Mapping, Sequence
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
    from pipeline.store.tenancy import current_tenant

    tenant = current_tenant.get()
    if tenant is None:  # a collector must say whose data this is (ADR-0034)
        raise RuntimeError("no tenant: cannot publish an event without one")
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": str(event.schema_version),
        "source": event.source.value,
        "tenant_id": tenant,
    }


def message_tenant(message: ReceivedMessage) -> str:
    """The tenant a message's event belongs to. Messages published before tenants existed
    carry none, and they were all the public demo's."""
    from pipeline.store.tenancy import DEMO, valid

    return valid(message.attributes.get("tenant_id") or DEMO)


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


class BatchStore(Protocol):
    """Stores a pulled batch at once (the worker's fast path)."""

    def store(self, events: Sequence[NormalizedEvent]) -> set[str]:
        """Store all events in one transaction; return the IDs that were new."""
        ...

    def announce(self, event: NormalizedEvent) -> None:
        """Called for each new event, inside that event's consumer span."""
        ...


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
    # Fast path: store a whole pulled batch in one transaction and ack it in one call. One
    # event at a time kept up with about 500 events a minute; a poll of Kubernetes and Kafka
    # plus the hourly Jira sync built a 5,000-message backlog that delayed webhooks by up to
    # 14 minutes (2026-11-24). Any batch failure falls back to one message at a time, which
    # keeps retries and dead-lettering exactly as before.
    batch: BatchStore | None = None
    _stats: dict[str, int] = field(default_factory=lambda: {"ok": 0, "failed": 0, "dead": 0})

    def poll_once(
        self,
        max_messages: int = 10,
        timeout_s: float = 1.0,
        stop: threading.Event | None = None,
    ) -> int:
        """Pull one batch and process it; return how many messages were handled OK.

        If ``stop`` is set part-way (the process is shutting down), the rest of the batch
        is handed back at once (nack) instead of waiting out the ack deadline: after a
        deploy, the old revision's unacked messages were redelivered only after 60 s
        (2026-11-24, P3-M5).
        """
        messages = self.transport.pull(self.topic, self.subscription, max_messages, timeout_s)
        if self.batch is not None and messages:
            if stop is not None and stop.is_set():
                for message in messages:
                    self.transport.nack(self.topic, self.subscription, message)
                return 0
            stored = self._store_batches(self.batch, messages)
            if stored is not None:
                return stored
        handled = 0
        for i, message in enumerate(messages):
            if stop is not None and stop.is_set():
                for rest in messages[i:]:
                    self.transport.nack(self.topic, self.subscription, rest)
                break
            handled += self._process(message)
        return handled

    def _store_batches(self, batch: BatchStore, messages: Sequence[ReceivedMessage]) -> int | None:
        """One batch per tenant, each stored for its own tenant (ADR-0034)."""
        from pipeline.store.tenancy import use_tenant

        groups: dict[str, list[ReceivedMessage]] = {}
        try:
            for message in messages:
                groups.setdefault(message_tenant(message), []).append(message)
        except ValueError:  # a malformed tenant: one at a time, so it dead-letters alone
            return None
        done = 0
        for tenant, group in groups.items():
            with use_tenant(tenant):
                stored = self._store_batch(batch, group)
            # A failed group falls back to one message at a time (retries, dead letters).
            done += stored if stored is not None else self._one_by_one(group)
        return done

    def _one_by_one(self, messages: Sequence[ReceivedMessage]) -> int:
        return sum(self._process(m) for m in messages)

    def _store_batch(self, batch: BatchStore, messages: Sequence[ReceivedMessage]) -> int | None:
        """Store and ack a batch at once; None means "fall back to one at a time"."""
        start = time.perf_counter()
        try:
            events = [NormalizedEvent.from_bytes(m.data) for m in messages]
            new_ids = batch.store(events)
        except Exception:
            logger.warning(
                "batch store failed; processing one message at a time",
                extra={"messages": len(messages)},
                exc_info=True,
            )
            return None
        elapsed = (time.perf_counter() - start) / len(messages)
        for message, event in zip(messages, events, strict=True):
            labels = {"topic": self.topic, "event_type": message.attributes.get("event_type", "")}
            # The consumer span per message keeps one trace from the collector to the page.
            with consume_span(self.transport.system, self.topic, self.subscription, message):
                if event.event_id in new_ids:
                    try:
                        batch.announce(event)
                    except Exception:  # stored already; a failed notice must not lose acks
                        logger.warning("announce failed", exc_info=True)
            _processed.add(1, labels)
            _duration.record(elapsed, labels)
        ack_many = getattr(self.transport, "ack_many", None)
        if ack_many is not None:
            ack_many(self.topic, self.subscription, list(messages))
        else:
            for message in messages:
                self.transport.ack(self.topic, self.subscription, message)
        self._stats["ok"] += len(messages)
        return len(messages)

    def _process(self, message: ReceivedMessage) -> bool:
        labels = {"topic": self.topic, "event_type": message.attributes.get("event_type", "")}
        start = time.perf_counter()
        with consume_span(self.transport.system, self.topic, self.subscription, message) as span:
            try:
                from pipeline.store.tenancy import use_tenant

                event = NormalizedEvent.from_bytes(message.data)
                with use_tenant(message_tenant(message)):  # stored for the event's tenant
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
