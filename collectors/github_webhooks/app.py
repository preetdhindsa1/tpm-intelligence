"""GitHub webhook receiver (P3-M5, ADR-0020): verify, de-duplicate, normalize, publish.

One endpoint, ``POST /github``, behind a public URL. Every request must carry a valid
``X-Hub-Signature-256``; anything else gets 401 and is counted. Accepted deliveries are
normalized into the same events the poller emits and published to the queue, where the
API's worker stores them and pushes the dashboard update. The receiver answers inside
GitHub's 10-second limit and stores nothing itself.

* **Repeat deliveries** (GitHub retries, manual redelivery) are skipped by
  ``X-GitHub-Delivery``. Event IDs are deterministic, so a repeat that slips through
  (for example after a restart) is still stored once by the worker.
* **Only allowed repositories** are accepted: a signed delivery from a repository no team
  lists is acknowledged and dropped.
* **No per-person data** beyond what the poller already keeps (CLAUDE.md section 10).
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Collection, Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from opentelemetry import metrics

from collectors.github_webhooks.signature import verify
from pipeline.events import NormalizedEvent

logger = logging.getLogger("collectors.github_webhooks")
_meter = metrics.get_meter(__name__)
_deliveries = _meter.create_counter(
    "webhook.deliveries", description="Webhook deliveries by outcome", unit="{delivery}"
)

MAX_BODY_BYTES = 5 * 1024 * 1024  # GitHub caps payloads at 25 MB; ours are far smaller
Normalizer = Callable[[str, dict[str, Any], datetime], Sequence[NormalizedEvent]]


class RecentDeliveries:
    """The last ``size`` delivery IDs, to skip GitHub's retries cheaply."""

    def __init__(self, size: int = 10_000) -> None:
        self._ids: OrderedDict[str, None] = OrderedDict()
        self._size = size

    def seen(self, delivery_id: str) -> bool:
        """Record ``delivery_id``; True if it was already recorded."""
        if delivery_id in self._ids:
            self._ids.move_to_end(delivery_id)
            return True
        self._ids[delivery_id] = None
        if len(self._ids) > self._size:
            self._ids.popitem(last=False)
        return False


def _outcome(response: Response, outcome: str, event: str) -> Response:
    _deliveries.add(1, {"outcome": outcome, "github_event": event})
    return response


def create_app(
    *,
    secret: str,
    publish: Callable[[NormalizedEvent], object],
    normalize: Normalizer,
    allowed_repos: Collection[str],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    flush: Callable[[], object] | None = None,
) -> FastAPI:
    """Build the receiver. ``secret`` must be non-empty: without it nothing is accepted.

    ``flush`` (telemetry export) runs after each delivery is handled and before the answer
    goes out, while Cloud Run still gives the instance CPU. The request's own server span
    ends after that, so it goes out with the next delivery's flush.
    """
    app = FastAPI(title="Program Intelligence Platform webhook receiver", version="0.1.0")

    if flush is not None:
        flush_now = flush

        @app.middleware("http")
        async def flush_telemetry(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            response = await call_next(request)
            if request.url.path == "/github":
                try:
                    await run_in_threadpool(flush_now)
                except Exception:  # telemetry must never fail a delivery
                    logger.warning("telemetry flush failed", exc_info=True)
            return response

    recent = RecentDeliveries()
    allowed = {r.lower() for r in allowed_repos}

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness (Cloud Run reserves paths ending in z)."""
        return {"status": "ok"}

    @app.post("/github")
    async def github(request: Request) -> Response:
        event = request.headers.get("X-GitHub-Event", "")
        delivery = request.headers.get("X-GitHub-Delivery", "")
        length = int(request.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return _outcome(Response(status_code=413), "too_large", event)
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return _outcome(Response(status_code=413), "too_large", event)
        if not verify(secret, body, request.headers.get("X-Hub-Signature-256")):
            logger.warning("webhook signature rejected", extra={"github_event": event})
            return _outcome(Response(status_code=401), "bad_signature", event)
        if event == "ping":
            return _outcome(Response(content="pong", status_code=200), "ping", event)
        if not delivery or recent.seen(delivery):
            return _outcome(Response(status_code=202), "repeat", event)
        try:
            payload = json.loads(body)
        except ValueError:
            return _outcome(Response(status_code=400), "bad_json", event)
        repo = str((payload.get("repository") or {}).get("full_name", "")).lower()
        if repo not in allowed:
            logger.info("webhook from a repository no team lists", extra={"repo": repo})
            return _outcome(Response(status_code=202), "repo_not_allowed", event)
        events = normalize(event, payload, now())
        for e in events:
            publish(e)
        logger.info(
            "webhook received",
            extra={"github_event": event, "repo": repo, "events_published": len(events)},
        )
        return _outcome(
            Response(content=json.dumps({"events": len(events)}), status_code=202),
            "accepted" if events else "ignored",
            event,
        )

    return app
