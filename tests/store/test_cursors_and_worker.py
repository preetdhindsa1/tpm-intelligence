"""Cursor store and worker event storage against real Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from pipeline.sample import k8s_6395_tracked_no
from pipeline.store.cursors import PostgresCursorStore
from pipeline.store.models import EventRecord
from pipeline.worker import store_events

pytestmark = pytest.mark.integration

T = datetime(2026, 11, 21, 12, tzinfo=UTC)


def test_cursor_lifecycle(engine: Engine) -> None:
    store = PostgresCursorStore(sessionmaker(engine))
    stream = "test:cursor-lifecycle"
    assert store.get(stream) is None
    assert store.record_failure(stream, "boom", T) == 1
    assert store.record_failure(stream, "boom again", T) == 2  # alert threshold
    assert store.get(stream) is None  # failures never move the cursor
    store.record_success(stream, "2026-11-21T00:33:58Z", T)
    assert store.get(stream) == "2026-11-21T00:33:58Z"
    assert store.record_failure(stream, "boom", T) == 1  # reset by the success


def test_worker_stores_events_idempotently(engine: Engine) -> None:
    handle = store_events(sessionmaker(engine))
    event = k8s_6395_tracked_no()
    handle(event)
    handle(event)  # redelivery
    with engine.connect() as conn:
        count = conn.execute(
            select(func.count())
            .select_from(EventRecord)
            .where(EventRecord.event_id == event.event_id)
        ).scalar_one()
    assert count == 1


def test_in_process_worker_stores_and_announces(
    engine: Engine, db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cloud option B (ADR-0017): the API runs the worker in a thread, no Redis."""
    import threading
    import uuid

    from pipeline.memory import InMemoryTransport
    from pipeline.queue import EventPublisher
    from pipeline.worker import start_in_background

    monkeypatch.setenv("DATABASE_URL", db_url)
    from pipeline.queue import EVENTS_TOPIC
    from pipeline.worker import SUBSCRIPTION

    transport = InMemoryTransport()
    transport.pull(EVENTS_TOPIC, SUBSCRIPTION, 1, 0)  # subscribe before publishing
    # A fresh event id: the worker announces only events it had not stored before.
    event = k8s_6395_tracked_no().model_copy(update={"event_id": str(uuid.uuid4())})
    announced = threading.Event()
    messages: list[str] = []

    def notify(message: str) -> None:
        messages.append(message)
        announced.set()

    stop = start_in_background(notify, transport)
    try:
        EventPublisher(transport).publish(event)
        assert announced.wait(10), "the in-process worker did not announce the event"
    finally:
        stop.set()
    with sessionmaker(engine)() as s:
        stored = s.scalar(
            select(func.count())
            .select_from(EventRecord)
            .where(EventRecord.event_id == event.event_id)
        )
    assert stored == 1
    assert event.event_id in messages[0]
