"""Event -> dashboard latency for the webhook path, from the services' own logs (P3-M5).

Pure functions: the caller reads the log lines (``scripts/measure_webhook_latency.py``).

* The webhook receiver logs ``webhook received`` with the IDs of the events it published.
* The API logs ``live update pushed`` for every push to an open page, with the first event
  of the batch and seconds since that event happened at GitHub (``occurred_at``) and
  since the receiver saw it (``observed_at``).

A push counts for the webhook path when its event ID came through the receiver. Per stage:

* GitHub -> receiver: ``since_occurred - since_observed`` (GitHub's delivery time; GitHub's
  clock, whole seconds, so about +-1 s).
* receiver -> push: ``since_observed`` (queue, store, recompute, send).
* total: ``since_occurred``, the end-to-end figure the 30 s target is about.

Several open pages push the same update, so the summary counts pushes and unique events;
the percentiles are over unique events (the first push of each), which is what a viewer
waits for.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np

TARGET_P95_S = 30.0  # CLAUDE.md section 9: event -> dashboard p95 < 30 s (webhooks)


def summary(values: list[float]) -> dict[str, float | int | None]:
    """n, p50, p95 and max, rounded to 0.01 s (None when empty)."""
    if not values:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    a = np.array(values, dtype=float)
    return {
        "n": len(values),
        "p50": round(float(np.percentile(a, 50)), 2),
        "p95": round(float(np.percentile(a, 95)), 2),
        "max": round(float(a.max()), 2),
    }


def webhook_event_ids(receipts: Iterable[Mapping[str, Any]]) -> set[str]:
    """Event IDs the receiver published, from ``webhook received`` payloads."""
    ids: set[str] = set()
    for r in receipts:
        ids.update(str(e) for e in r.get("event_ids") or [])
    return ids


def webhook_latency(
    receipts: Iterable[Mapping[str, Any]], pushes: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Per-stage latency of pushes whose first event came through the webhook receiver.

    ``receipts`` and ``pushes`` are the JSON payloads of the two log lines, pushes in time
    order (oldest first).
    """
    via_webhook = webhook_event_ids(receipts)
    first: dict[str, Mapping[str, Any]] = {}
    all_pushes = 0
    for p in pushes:
        event_id = p.get("event_id")
        if not event_id or str(event_id) not in via_webhook:
            continue
        if p.get("seconds_since_occurred") is None or p.get("seconds_since_observed") is None:
            continue
        all_pushes += 1
        first.setdefault(str(event_id), p)
    total = [float(p["seconds_since_occurred"]) for p in first.values()]
    after_receipt = [float(p["seconds_since_observed"]) for p in first.values()]
    delivery = [t - r for t, r in zip(total, after_receipt, strict=True)]
    p95 = summary(total)["p95"]
    return {
        "pushes": all_pushes,
        "unique_events": len(first),
        "total_seconds": summary(total),
        "github_to_receiver_seconds": summary(delivery),
        "receiver_to_push_seconds": summary(after_receipt),
        "target_p95_seconds": TARGET_P95_S,
        "meets_target": None if p95 is None else bool(p95 < TARGET_P95_S),
    }
