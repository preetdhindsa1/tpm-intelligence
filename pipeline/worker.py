"""Pipeline worker: consumes normalized events from the queue.

M3: each event is appended to the Postgres event log (idempotent on ``event_id``).
M7 adds the projections and link -> engine -> forecast.
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from pipeline.events import NormalizedEvent
from pipeline.queue import EventConsumer, Handler, Transport

SERVICE_NAME = "tpm-worker"
SUBSCRIPTION = "worker"

logger = logging.getLogger("pipeline.worker")


def log_event(event: NormalizedEvent) -> None:
    """Log one event (used when no database is configured, e.g. unit tests)."""
    logger.info(
        "event stored",
        extra={
            "event_id": event.event_id,
            "event_type": event.event_type,
            "subject": event.subject.external_key,
            "occurred_at": event.occurred_at.isoformat(),
        },
    )


def store_events(
    factory: sessionmaker[Session], notify: Callable[[str], None] | None = None
) -> Handler:
    """Handler that appends each event to ``events`` (duplicates skipped).

    After a new event is stored, ``notify`` receives a small message carrying the current
    trace context (the consumer span), so the API's live update joins the same trace.
    """
    from pipeline.notify import notification
    from pipeline.store.events_repo import append_events
    from pipeline.store.session import session_scope

    def handle(event: NormalizedEvent) -> None:
        with session_scope(factory) as session:
            inserted = append_events(session, [event])
        log_event(event)
        if not inserted:
            logger.info("duplicate event skipped", extra={"event_id": event.event_id})
        elif notify is not None:
            notify(notification(event.event_id, event.subject.external_key))

    return handle


def run(
    stop: threading.Event,
    transport: Transport,
    *,
    handler: Callable[[NormalizedEvent], None] = log_event,
    poll_timeout_s: float = 2.0,
) -> int:
    """Consume until ``stop`` is set; return the number of events handled OK."""
    consumer = EventConsumer(transport=transport, subscription=SUBSCRIPTION, handler=handler)
    handled = 0
    while not stop.is_set():
        handled += consumer.poll_once(timeout_s=poll_timeout_s)
    return handled


def main() -> None:
    """Start telemetry, connect to the queue, consume until SIGTERM/SIGINT."""
    import os

    import redis

    from observability.telemetry import init_telemetry
    from pipeline.factory import create_transport
    from pipeline.notify import CHANNEL
    from pipeline.store.session import make_engine

    telemetry = init_telemetry(SERVICE_NAME)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logger.info("worker started", extra={"subscription": SUBSCRIPTION})
    try:
        client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

        def notify(message: str) -> None:
            client.publish(CHANNEL, message)

        handler = store_events(sessionmaker(make_engine()), notify=notify)
        run(stop, create_transport(), handler=handler)
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    main()
