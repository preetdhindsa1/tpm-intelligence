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
