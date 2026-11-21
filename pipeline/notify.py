"""Worker -> API "events stored" notifications (shared message format).

One small JSON message per newly stored event, carrying the W3C trace context of the
consumer span, so the API's live update continues the collector's trace.
"""

from __future__ import annotations

import json

from opentelemetry import propagate
from opentelemetry.context import Context

CHANNEL = "tpm:events-stored"


def notification(event_id: str, subject: str) -> str:
    """Message body with the current trace context injected."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return json.dumps({"event_id": event_id, "subject": subject, **carrier})


def context_of(message: str | bytes) -> Context:
    """Trace context carried in a notification (empty context if malformed)."""
    try:
        carrier = json.loads(message)
    except (ValueError, TypeError):
        carrier = {}
    if not isinstance(carrier, dict):
        carrier = {}
    return propagate.extract({k: str(v) for k, v in carrier.items()})
