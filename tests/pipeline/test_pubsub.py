"""Pub/Sub transport: request shapes against fake clients; real emulator when available."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from pipeline.events import NormalizedEvent
from pipeline.pubsub import PubSubTransport, dead_letter_topic
from pipeline.queue import EventConsumer, EventPublisher, ReceivedMessage
from pipeline.sample import k8s_6395_tracked_no


@dataclass
class _Future:
    value: str

    def result(self, timeout: float | None = None) -> str:
        return self.value


@dataclass
class FakePublisher:
    calls: list[tuple[str, bytes, dict[str, str]]] = field(default_factory=list)

    def publish(self, topic: str, data: bytes, **attrs: str) -> _Future:
        self.calls.append((topic, data, attrs))
        return _Future(str(len(self.calls)))


@dataclass
class FakeSubscriber:
    requests: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    to_return: list[Any] = field(default_factory=list)

    def pull(self, request: dict[str, Any], timeout: float) -> Any:
        self.requests.append(("pull", request))
        return type("R", (), {"received_messages": self.to_return})()

    def acknowledge(self, request: dict[str, Any]) -> None:
        self.requests.append(("ack", request))

    def modify_ack_deadline(self, request: dict[str, Any]) -> None:
        self.requests.append(("modack", request))


def _received(delivery_attempt: int) -> Any:
    msg = type("M", (), {"message_id": "m1", "data": b"d", "attributes": {"a": "b"}})()
    fields = {"message": msg, "ack_id": "ack-1", "delivery_attempt": delivery_attempt}
    return type("RM", (), fields)()


def _transport() -> tuple[PubSubTransport, FakePublisher, FakeSubscriber]:
    pub, sub = FakePublisher(), FakeSubscriber()
    return PubSubTransport("demo-project", publisher=pub, subscriber=sub), pub, sub


def test_publish_uses_full_topic_path_and_attributes() -> None:
    t, pub, _ = _transport()
    assert t.publish("normalized-events", b"x", {"traceparent": "00-a"}) == "1"
    topic_path = "projects/demo-project/topics/normalized-events"
    assert pub.calls == [(topic_path, b"x", {"traceparent": "00-a"})]


@pytest.mark.parametrize(("raw_attempt", "expected"), [(0, 1), (3, 3)])
def test_pull_maps_messages_and_delivery_attempt(raw_attempt: int, expected: int) -> None:
    t, _, sub = _transport()
    sub.to_return = [_received(raw_attempt)]
    [m] = t.pull("normalized-events", "worker", 5, 1.0)
    assert m == ReceivedMessage("m1", b"d", {"a": "b"}, expected, "ack-1")
    assert sub.requests[0] == (
        "pull",
        {"subscription": "projects/demo-project/subscriptions/worker", "max_messages": 5},
    )


def test_nack_sets_deadline_zero_and_dead_letter_republishes_then_acks() -> None:
    t, pub, sub = _transport()
    m = ReceivedMessage("m1", b"d", {"a": "b"}, 5, "ack-1")
    t.nack("normalized-events", "worker", m)
    t.dead_letter("normalized-events", "worker", m)
    assert sub.requests[0][1]["ack_deadline_seconds"] == 0
    topic, data, attrs = pub.calls[0]
    assert topic.endswith("/topics/" + dead_letter_topic("normalized-events"))
    assert (data, attrs["dead_letter.attempts"], attrs["a"]) == (b"d", "5", "b")
    assert sub.requests[1] == (
        "ack",
        {"subscription": "projects/demo-project/subscriptions/worker", "ack_ids": ["ack-1"]},
    )


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("PUBSUB_EMULATOR_HOST"), reason="PUBSUB_EMULATOR_HOST not set")
def test_round_trip_against_emulator() -> None:
    from google.cloud import pubsub_v1

    project = "tpm-local"
    topic, sub = f"t-{uuid.uuid4().hex[:8]}", f"s-{uuid.uuid4().hex[:8]}"
    publisher, subscriber = pubsub_v1.PublisherClient(), pubsub_v1.SubscriberClient()
    publisher.create_topic(name=f"projects/{project}/topics/{topic}")
    subscriber.create_subscription(
        name=f"projects/{project}/subscriptions/{sub}", topic=f"projects/{project}/topics/{topic}"
    )
    t = PubSubTransport(project, publisher=publisher, subscriber=subscriber)
    EventPublisher(t, topic=topic).publish(k8s_6395_tracked_no())
    received: list[NormalizedEvent] = []
    consumer = EventConsumer(t, sub, received.append, topic=topic)
    for _ in range(10):
        if consumer.poll_once(timeout_s=5.0):
            break
    assert [e.event_id for e in received] == [k8s_6395_tracked_no().event_id]


def test_empty_subscription_deadline_is_no_messages_not_a_failure() -> None:
    from google.api_core.exceptions import DeadlineExceeded

    class TimingOut(FakeSubscriber):
        def pull(self, request: dict[str, Any], timeout: float) -> Any:
            raise DeadlineExceeded("Deadline Exceeded")

    transport = PubSubTransport("demo-project", publisher=FakePublisher(), subscriber=TimingOut())
    assert transport.pull("events", "worker", 10, 2.0) == []
