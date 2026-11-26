"""Publish one real-shaped event to check queue + trace propagation end to end.

Usage (inside the Compose stack)::

    docker compose exec worker python -m pipeline.sample

The event is the real Code Freeze removal of Kubernetes enhancement #6395:
``tracked/no`` added at 2026-11-17T12:05:58Z (GitHub issue events API).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from opentelemetry import trace

from pipeline.events import (
    ChangeAction,
    NormalizedEvent,
    Source,
    SubjectKind,
    SubjectRef,
    WorkItemLabelChanged,
    new_event,
)
from pipeline.queue import EventPublisher

SERVICE_NAME = "tpm-sample-publisher"

logger = logging.getLogger("pipeline.sample")


def k8s_6395_tracked_no() -> NormalizedEvent:
    """#6395 labelled ``tracked/no`` at Code Freeze (real timestamp)."""
    occurred = datetime(2026, 11, 17, 12, 5, 58, tzinfo=UTC)
    return new_event(
        source=Source.GITHUB,
        subject=SubjectRef(
            kind=SubjectKind.WORK_ITEM,
            source=Source.GITHUB,
            external_key="kubernetes/enhancements#6395",
        ),
        occurred_at=occurred,
        payload=WorkItemLabelChanged(action=ChangeAction.ADDED, label="tracked/no"),
        identity=("tracked/no", "added", occurred.isoformat()),
    )


def main() -> None:
    """Publish the sample inside a root span and print the trace ID."""
    from observability.telemetry import init_telemetry
    from pipeline.factory import create_transport

    telemetry = init_telemetry(SERVICE_NAME)
    publisher = EventPublisher(create_transport())
    with trace.get_tracer(__name__).start_as_current_span("sample.publish") as span:
        message_id = publisher.publish(k8s_6395_tracked_no())
        trace_id = format(span.get_span_context().trace_id, "032x")
    logger.info("sample published", extra={"message_id": message_id})
    telemetry.shutdown()
    print(f"published message {message_id}; trace_id={trace_id}")


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        main()
