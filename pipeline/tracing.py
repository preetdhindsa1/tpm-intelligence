"""Trace-context propagation through queue message attributes (CLAUDE.md section 9).

The publisher injects W3C ``traceparent``/``tracestate`` into message attributes; the
consumer extracts them and starts its span as a child, so one trace runs from the
collector through the queue to the worker (and on to the API).
Span names and attributes follow the OTel messaging semantic conventions.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from typing import TYPE_CHECKING

from opentelemetry import propagate, trace
from opentelemetry.trace import Span, SpanKind

if TYPE_CHECKING:
    from pipeline.events import NormalizedEvent
    from pipeline.queue import ReceivedMessage

_tracer = trace.get_tracer("pipeline.queue")


def inject_context(attributes: MutableMapping[str, str]) -> None:
    """Write the active trace context into ``attributes`` (in place)."""
    propagate.inject(attributes)


@contextmanager
def publish_span(system: str, topic: str, event: NormalizedEvent) -> Iterator[Span]:
    """PRODUCER span around a publish; inject context *inside* it."""
    with _tracer.start_as_current_span(
        f"{topic} publish",
        kind=SpanKind.PRODUCER,
        attributes={
            "messaging.system": system,
            "messaging.operation.type": "publish",
            "messaging.destination.name": topic,
            "tpm.event.id": event.event_id,
            "tpm.event.type": event.event_type,
            "tpm.event.source": event.source.value,
            "tpm.subject.key": event.subject.external_key,
        },
    ) as span:
        yield span


@contextmanager
def consume_span(
    system: str, topic: str, subscription: str, message: ReceivedMessage
) -> Iterator[Span]:
    """CONSUMER span whose parent is the context carried in ``message.attributes``."""
    parent = propagate.extract(_as_carrier(message.attributes))
    with _tracer.start_as_current_span(
        f"{topic} process",
        context=parent,
        kind=SpanKind.CONSUMER,
        attributes={
            "messaging.system": system,
            "messaging.operation.type": "process",
            "messaging.destination.name": topic,
            "messaging.destination.subscription.name": subscription,
            "messaging.message.id": message.message_id,
            "messaging.message.delivery_attempt": message.delivery_attempt,
            "tpm.event.id": message.attributes.get("event_id", ""),
            "tpm.event.type": message.attributes.get("event_type", ""),
        },
    ) as span:
        yield span


def _as_carrier(attributes: Mapping[str, str]) -> dict[str, str]:
    return dict(attributes)
