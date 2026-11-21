"""Event publisher/consumer: trace context crosses the queue; failures retry then dead-letter."""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from pipeline.events import NormalizedEvent
from pipeline.memory import InMemoryTransport
from pipeline.queue import EVENTS_TOPIC, EventConsumer, EventPublisher
from pipeline.sample import k8s_6395_tracked_no


def test_attributes_carry_traceparent_and_event_metadata() -> None:
    transport = InMemoryTransport()
    EventPublisher(transport).publish(k8s_6395_tracked_no())
    [message] = transport.pull(EVENTS_TOPIC, "s", 10, 0)
    assert message.attributes["traceparent"].startswith("00-")
    assert message.attributes["event_type"] == "work_item.label_changed"
    assert message.attributes["source"] == "github"


def test_consumer_span_continues_the_publisher_trace(spans: InMemorySpanExporter) -> None:
    transport = InMemoryTransport()
    seen_trace_ids: list[int] = []

    def handler(event: NormalizedEvent) -> None:
        seen_trace_ids.append(trace.get_current_span().get_span_context().trace_id)

    with trace.get_tracer(__name__).start_as_current_span("collector.poll") as root:
        EventPublisher(transport).publish(k8s_6395_tracked_no())
        root_trace_id = root.get_span_context().trace_id

    # Consume outside the publisher's context, as a separate process would.
    assert EventConsumer(transport, "worker", handler).poll_once() == 1

    by_name = {s.name: s for s in spans.get_finished_spans()}
    publish = by_name[f"{EVENTS_TOPIC} publish"]
    process = by_name[f"{EVENTS_TOPIC} process"]
    assert publish.kind is SpanKind.PRODUCER
    assert process.kind is SpanKind.CONSUMER
    assert publish.context.trace_id == process.context.trace_id == root_trace_id
    assert process.parent is not None
    assert process.parent.span_id == publish.context.span_id
    assert seen_trace_ids == [root_trace_id]  # handler runs inside the consumer span
    assert process.attributes is not None
    assert process.attributes["tpm.event.type"] == "work_item.label_changed"


def test_failed_handler_is_retried_then_dead_lettered(spans: InMemorySpanExporter) -> None:
    transport = InMemoryTransport()
    EventPublisher(transport).publish(k8s_6395_tracked_no())
    calls = 0

    def always_fails(event: NormalizedEvent) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("downstream unavailable")

    consumer = EventConsumer(transport, "worker", always_fails, max_delivery_attempts=3)
    for _ in range(5):
        consumer.poll_once()

    assert calls == 3
    assert consumer.stats == {"ok": 0, "failed": 3, "dead": 1}
    [dead] = transport.dead_letters[EVENTS_TOPIC]
    assert dead.delivery_attempt == 3
    assert transport.pending(EVENTS_TOPIC, "worker") == 0
    process_spans = [s for s in spans.get_finished_spans() if s.name.endswith("process")]
    assert all(s.status.status_code is StatusCode.ERROR for s in process_spans)


def test_transient_failure_succeeds_on_redelivery() -> None:
    transport = InMemoryTransport()
    EventPublisher(transport).publish(k8s_6395_tracked_no())
    attempts: list[int] = []

    def flaky(event: NormalizedEvent) -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("blip")

    consumer = EventConsumer(transport, "worker", flaky)
    consumer.poll_once()
    consumer.poll_once()
    assert consumer.stats == {"ok": 1, "failed": 1, "dead": 0}
    assert transport.pending(EVENTS_TOPIC, "worker") == 0


def test_malformed_message_does_not_crash_the_consumer() -> None:
    transport = InMemoryTransport()
    transport.publish(EVENTS_TOPIC, b"not json", {"event_type": "?"})
    consumer = EventConsumer(transport, "worker", lambda e: None, max_delivery_attempts=1)
    assert consumer.poll_once() == 0
    assert len(transport.dead_letters[EVENTS_TOPIC]) == 1


@pytest.mark.parametrize("subscriptions", [("worker", "api-cache")])
def test_each_subscription_gets_every_event(subscriptions: tuple[str, str]) -> None:
    transport = InMemoryTransport()
    EventPublisher(transport).publish(k8s_6395_tracked_no())
    for sub in subscriptions:
        assert EventConsumer(transport, sub, lambda e: None).poll_once() == 1
