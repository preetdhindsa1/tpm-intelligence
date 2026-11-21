"""Worker consumes queued events and stops cleanly."""

from __future__ import annotations

import threading

from pipeline.memory import InMemoryTransport
from pipeline.queue import EVENTS_TOPIC, EventPublisher
from pipeline.sample import k8s_6395_tracked_no
from pipeline.worker import SUBSCRIPTION, run


def test_run_returns_immediately_when_stopped() -> None:
    stop = threading.Event()
    stop.set()
    assert run(stop, InMemoryTransport()) == 0


def test_run_handles_published_events_until_stopped() -> None:
    transport = InMemoryTransport()
    publisher = EventPublisher(transport)
    publisher.publish(k8s_6395_tracked_no())
    publisher.publish(k8s_6395_tracked_no())  # duplicate delivery must be harmless
    stop = threading.Event()
    timer = threading.Timer(0.05, stop.set)
    timer.start()
    handled = run(stop, transport, poll_timeout_s=0.0)
    timer.join()
    assert handled == 2
    assert transport.pending(EVENTS_TOPIC, SUBSCRIPTION) == 0
