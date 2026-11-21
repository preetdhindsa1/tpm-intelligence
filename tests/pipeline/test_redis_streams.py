"""Redis Streams transport contract.

Runs against fakeredis (unit) and, with ``-m integration``, a real Redis at ``REDIS_URL``.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator

import fakeredis
import pytest
import redis

from pipeline.events import NormalizedEvent
from pipeline.queue import EventConsumer, EventPublisher
from pipeline.redis_streams import RedisStreamsTransport, dead_letter_key, stream_key
from pipeline.sample import k8s_6395_tracked_no

VISIBILITY_S = 0.2


@pytest.fixture(
    params=[
        pytest.param("fake", id="fakeredis"),
        pytest.param("real", id="redis", marks=pytest.mark.integration),
    ]
)
def client(request: pytest.FixtureRequest) -> Iterator[redis.Redis]:
    if request.param == "fake":
        yield fakeredis.FakeRedis()
        return
    real = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/15"))
    try:
        real.ping()
    except redis.ConnectionError:
        pytest.skip("Redis not reachable at REDIS_URL")
    yield real


@pytest.fixture
def topic(client: redis.Redis) -> Iterator[str]:
    name = f"test-{uuid.uuid4().hex[:8]}"
    yield name
    client.delete(stream_key(name), dead_letter_key(name))


def make(client: redis.Redis, consumer: str = "c1") -> RedisStreamsTransport:
    return RedisStreamsTransport(client, consumer_name=consumer, visibility_timeout_s=VISIBILITY_S)


def test_publish_pull_ack(client: redis.Redis, topic: str) -> None:
    t = make(client)
    mid = t.publish(topic, b"hello", {"k": "v", "traceparent": "00-abc"})
    [m] = t.pull(topic, "sub", 10, 0.05)
    assert (m.message_id, m.data, m.delivery_attempt) == (mid, b"hello", 1)
    assert m.attributes == {"k": "v", "traceparent": "00-abc"}
    t.ack(topic, "sub", m)
    assert t.backlog(topic, "sub") == 0
    assert t.pull(topic, "sub", 10, 0.05) == []


def test_group_created_late_still_sees_earlier_messages(client: redis.Redis, topic: str) -> None:
    t = make(client)
    t.publish(topic, b"early", {})
    assert [m.data for m in t.pull(topic, "late-sub", 10, 0.05)] == [b"early"]


def test_unacked_message_is_redelivered_after_visibility_timeout(
    client: redis.Redis, topic: str
) -> None:
    crashed, survivor = make(client, "crashed"), make(client, "survivor")
    crashed.publish(topic, b"x", {})
    [first] = crashed.pull(topic, "sub", 10, 0.05)  # worker dies before ack
    assert survivor.pull(topic, "sub", 10, 0.05) == []  # not yet timed out
    time.sleep(VISIBILITY_S * 1.5)
    [again] = survivor.pull(topic, "sub", 10, 0.05)
    assert again.message_id == first.message_id
    assert again.delivery_attempt == 2


def test_nack_makes_message_available_immediately(client: redis.Redis, topic: str) -> None:
    t = make(client)
    t.publish(topic, b"x", {})
    [m] = t.pull(topic, "sub", 10, 0.05)
    t.nack(topic, "sub", m)
    [again] = t.pull(topic, "sub", 10, 0.05)
    assert again.message_id == m.message_id
    assert again.delivery_attempt == 2


def test_dead_letter_copies_and_acks(client: redis.Redis, topic: str) -> None:
    t = make(client)
    t.publish(topic, b"poison", {"event_type": "x"})
    [m] = t.pull(topic, "sub", 10, 0.05)
    t.dead_letter(topic, "sub", m)
    assert t.backlog(topic, "sub") == 0
    [(_, fields)] = client.xrange(dead_letter_key(topic))
    assert fields[b"data"] == b"poison"
    assert fields[b"a:dead_letter.attempts"] == b"1"
    assert fields[b"a:event_type"] == b"x"


def test_end_to_end_with_event_consumer(client: redis.Redis, topic: str) -> None:
    t = make(client)
    EventPublisher(t, topic=topic).publish(k8s_6395_tracked_no())
    received: list[NormalizedEvent] = []
    consumer = EventConsumer(t, "worker", received.append, topic=topic)
    assert consumer.poll_once(timeout_s=0.05) == 1
    [event] = received
    assert event.event_id == k8s_6395_tracked_no().event_id
    assert event.payload == k8s_6395_tracked_no().payload
