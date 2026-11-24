"""Worker -> API "events stored" notifications (shared message format).

One small JSON message per newly stored event, carrying the W3C trace context of the
consumer span, so the API's live update continues the collector's trace. It also carries
when the event happened at the source (``occurred_at``) and when a collector saw it
(``observed_at``), so the push can be timed from the source (P3-M5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from opentelemetry import propagate
from opentelemetry.context import Context

CHANNEL = "tpm:events-stored"


def notification(
    event_id: str,
    subject: str,
    *,
    occurred_at: datetime | None = None,
    observed_at: datetime | None = None,
) -> str:
    """Message body with the current trace context injected."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    body: dict[str, str] = {"event_id": event_id, "subject": subject, **carrier}
    if occurred_at is not None:
        body["occurred_at"] = occurred_at.isoformat()
    if observed_at is not None:
        body["observed_at"] = observed_at.isoformat()
    return json.dumps(body)


@dataclass(frozen=True)
class Notice:
    """One (debounced) update for the API: the first stored event of a burst."""

    context: Context
    event_id: str | None = None
    occurred_at: datetime | None = None
    observed_at: datetime | None = None
    batched: int = 1  # notifications coalesced into this update


def _time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def notice_of(message: str | bytes, batched: int = 1) -> Notice:
    """The notice in a notification (empty context and no times if malformed)."""
    try:
        body = json.loads(message)
    except (ValueError, TypeError):
        body = {}
    if not isinstance(body, dict):
        body = {}
    event_id = body.get("event_id")
    return Notice(
        context=context_of(message),
        event_id=str(event_id) if event_id else None,
        occurred_at=_time(body.get("occurred_at")),
        observed_at=_time(body.get("observed_at")),
        batched=batched,
    )


def context_of(message: str | bytes) -> Context:
    """Trace context carried in a notification (empty context if malformed)."""
    try:
        carrier = json.loads(message)
    except (ValueError, TypeError):
        carrier = {}
    if not isinstance(carrier, dict):
        carrier = {}
    return propagate.extract({k: str(v) for k, v in carrier.items()})
