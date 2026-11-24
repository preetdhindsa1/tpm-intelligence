"""Worker consumes queued events and stops cleanly."""

from __future__ import annotations

import threading
from typing import Any

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


def _store_with(monkeypatch: Any, inserted: int) -> tuple[list[str], list[str]]:
    """Run store_events once with a fake insert result; return (log messages, notices)."""
    import contextlib
    import logging

    import pipeline.store.events_repo as repo
    import pipeline.store.session as session_mod
    from pipeline.worker import store_events

    monkeypatch.setattr(repo, "append_events", lambda session, events: inserted)
    monkeypatch.setattr(session_mod, "session_scope", lambda factory: contextlib.nullcontext())
    messages: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    log = logging.getLogger("pipeline.worker")
    capture, old_level = Capture(level=logging.DEBUG), log.level
    log.addHandler(capture)
    log.setLevel(logging.DEBUG)
    notices: list[str] = []
    try:
        store_events(None, notify=notices.append)(k8s_6395_tracked_no())  # type: ignore[arg-type]
    finally:
        log.removeHandler(capture)
        log.setLevel(old_level)
    return messages, notices


def test_new_event_is_logged_as_stored_and_announced(monkeypatch: Any) -> None:
    from pipeline.notify import notice_of
    from pipeline.sample import k8s_6395_tracked_no

    messages, notices = _store_with(monkeypatch, inserted=1)
    assert messages == ["event stored"]
    assert len(notices) == 1
    event, notice = k8s_6395_tracked_no(), notice_of(notices[0])
    assert notice.event_id == event.event_id
    assert notice.occurred_at == event.occurred_at  # P3-M5: timed from the source
    assert notice.observed_at is not None  # the sample stamps a fresh observed time


def test_duplicate_is_not_logged_as_stored_nor_announced(monkeypatch: Any) -> None:
    messages, notices = _store_with(monkeypatch, inserted=0)
    assert messages == ["duplicate event skipped"]
    assert notices == []


def test_stopping_hands_back_the_rest_of_a_batch_at_once() -> None:
    """P3-M5: after a deploy, the old revision's unprocessed messages waited 60 s."""
    from pipeline.queue import EventConsumer

    transport = InMemoryTransport()
    publisher = EventPublisher(transport)
    for _ in range(3):
        publisher.publish(k8s_6395_tracked_no())
    stop = threading.Event()
    seen: list[str] = []

    def handler(event: Any) -> None:
        seen.append(event.event_id)
        stop.set()  # shutdown begins while the first message is being handled

    consumer = EventConsumer(transport=transport, subscription=SUBSCRIPTION, handler=handler)
    assert consumer.poll_once(max_messages=10, stop=stop) == 1
    assert len(seen) == 1
    # The other two are back in the queue now, not stuck until an ack deadline.
    assert len(transport.pull(EVENTS_TOPIC, SUBSCRIPTION, 10, 0)) == 2


class _FakeBatch:
    """Records what the consumer's fast path does; ``new`` decides which IDs were new."""

    def __init__(self, new: set[str] | None = None, fail: bool = False) -> None:
        self.new, self.fail = new, fail
        self.stored: list[list[str]] = []
        self.announced: list[str] = []
        self.traces: list[int] = []

    def store(self, events: Any) -> set[str]:
        if self.fail:
            raise RuntimeError("database down")
        ids = [e.event_id for e in events]
        self.stored.append(ids)
        return set(ids) if self.new is None else self.new

    def announce(self, event: Any) -> None:
        from opentelemetry import trace

        self.announced.append(event.event_id)
        self.traces.append(trace.get_current_span().get_span_context().trace_id)


def _three_events(transport: InMemoryTransport) -> list[str]:
    from pipeline.events import NormalizedEvent

    publisher = EventPublisher(transport)
    ids = []
    for i in range(3):
        event = k8s_6395_tracked_no()
        event = NormalizedEvent.model_validate(
            {**event.model_dump(), "event_id": f"00000000-0000-0000-0000-00000000000{i}"}
        )
        publisher.publish(event)
        ids.append(event.event_id)
    return ids


def test_batch_path_stores_once_announces_only_new_events_and_acks_all() -> None:
    from pipeline.queue import EventConsumer

    transport = InMemoryTransport()
    ids = _three_events(transport)
    batch = _FakeBatch(new={ids[0], ids[2]})  # the middle one was already stored
    handled: list[str] = []
    consumer = EventConsumer(
        transport=transport,
        subscription=SUBSCRIPTION,
        handler=lambda e: handled.append(e),
        batch=batch,
    )
    assert consumer.poll_once(max_messages=100) == 3
    assert batch.stored == [ids]  # one store for the whole batch
    assert batch.announced == [ids[0], ids[2]]
    assert handled == []  # the one-at-a-time path was not needed
    assert transport.pull(EVENTS_TOPIC, SUBSCRIPTION, 10, 0) == []  # all acked


def test_a_failed_batch_falls_back_to_one_message_at_a_time() -> None:
    from pipeline.queue import EventConsumer

    transport = InMemoryTransport()
    ids = _three_events(transport)
    handled: list[str] = []
    consumer = EventConsumer(
        transport=transport,
        subscription=SUBSCRIPTION,
        handler=lambda e: handled.append(e.event_id),
        batch=_FakeBatch(fail=True),
    )
    assert consumer.poll_once(max_messages=100) == 3
    assert handled == ids  # retries and dead-lettering stay on the proven path


def test_each_new_event_is_announced_inside_its_own_trace() -> None:
    """One trace from the collector to the page (CLAUDE.md section 9), batch or not."""
    from opentelemetry import trace

    from pipeline.queue import EventConsumer

    transport = InMemoryTransport()
    with trace.get_tracer("test").start_as_current_span("collector") as span:
        _three_events(transport)
        producer_trace = span.get_span_context().trace_id
    batch = _FakeBatch()
    EventConsumer(
        transport=transport, subscription=SUBSCRIPTION, handler=lambda e: None, batch=batch
    ).poll_once(max_messages=100)
    if producer_trace:  # 0 when no tracer provider is installed in this test run
        assert batch.traces == [producer_trace] * 3


def test_stopping_hands_back_a_whole_batch() -> None:
    from pipeline.queue import EventConsumer

    transport = InMemoryTransport()
    _three_events(transport)
    stop = threading.Event()
    stop.set()
    batch = _FakeBatch()
    consumer = EventConsumer(
        transport=transport, subscription=SUBSCRIPTION, handler=lambda e: None, batch=batch
    )
    assert consumer.poll_once(max_messages=100, stop=stop) == 0
    assert batch.stored == []
    assert len(transport.pull(EVENTS_TOPIC, SUBSCRIPTION, 10, 0)) == 3
