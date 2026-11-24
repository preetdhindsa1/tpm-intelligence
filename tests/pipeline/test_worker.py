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
