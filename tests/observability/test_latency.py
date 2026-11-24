"""P3-M5 webhook latency: join receiver and API log lines, per stage."""

from __future__ import annotations

from observability.latency import summary, webhook_event_ids, webhook_latency


def test_summary_of_nothing_is_empty_not_zero() -> None:
    assert summary([]) == {"n": 0, "p50": None, "p95": None, "max": None}


def test_only_pushes_whose_event_came_through_the_receiver_count() -> None:
    receipts = [{"event_ids": ["w1", "w2"]}, {"event_ids": []}, {}]
    assert webhook_event_ids(receipts) == {"w1", "w2"}
    pushes = [
        {"event_id": "w1", "seconds_since_occurred": 6.0, "seconds_since_observed": 5.0},
        {"event_id": "w1", "seconds_since_occurred": 7.0, "seconds_since_observed": 6.0},
        {"event_id": "polled", "seconds_since_occurred": 200.0, "seconds_since_observed": 9.0},
        {"event_id": "w2", "seconds_since_occurred": 12.0, "seconds_since_observed": 10.0},
        {"event_id": None, "seconds_since_occurred": 1.0, "seconds_since_observed": 1.0},
        {"event_id": "w2", "seconds_since_notified": 3.0},  # old-format line: no times
    ]
    out = webhook_latency(receipts, pushes)
    assert out["pushes"] == 3  # two pages pushed w1; the polled event is excluded
    assert out["unique_events"] == 2
    assert out["total_seconds"]["n"] == 2
    assert out["total_seconds"]["max"] == 12.0  # first push of each event: 6 and 12
    assert out["github_to_receiver_seconds"]["max"] == 2.0  # 12 - 10
    assert out["receiver_to_push_seconds"]["max"] == 10.0
    assert out["meets_target"] is True


def test_no_webhook_pushes_means_no_verdict() -> None:
    out = webhook_latency([], [{"event_id": "x", "seconds_since_occurred": 1.0}])
    assert out["unique_events"] == 0
    assert out["meets_target"] is None


def test_a_slow_p95_misses_the_target() -> None:
    receipts = [{"event_ids": [f"e{i}" for i in range(20)]}]
    pushes = [
        {"event_id": f"e{i}", "seconds_since_occurred": 45.0, "seconds_since_observed": 40.0}
        for i in range(20)
    ]
    assert webhook_latency(receipts, pushes)["meets_target"] is False


def test_every_webhook_event_is_timed_to_the_first_push_after_it_was_stored() -> None:
    from datetime import UTC, datetime, timedelta

    from observability.latency import per_event_latency

    t0 = datetime(2026, 11, 24, 3, 0, tzinfo=UTC)
    s = timedelta(seconds=1)
    receipts = [(t0 + 2 * s, {"event_ids": ["a", "b"]}), (t0 + 30 * s, {"event_ids": ["c"]})]
    stored = [
        (t0 + 3 * s, {"event_id": "a", "occurred_at": t0.isoformat()}),
        (t0 + 3 * s, {"event_id": "b", "occurred_at": t0.isoformat()}),  # same batch as a
        (t0 + 4 * s, {"event_id": "polled", "occurred_at": t0.isoformat()}),  # not a webhook
        (t0 + 31 * s, {"event_id": "c", "occurred_at": (t0 + 29 * s).isoformat()}),
        (t0 + 99 * s, {"event_id": "never pushed", "occurred_at": t0.isoformat()}),
    ]
    receipts.append((t0 + 98 * s, {"event_ids": ["never pushed"]}))
    pushes = [t0 + 6 * s, t0 + 35 * s]
    out = per_event_latency(receipts, stored, pushes)
    assert out["events"] == 3  # a and b (one push), c; not the polled one or the unpushed one
    assert out["total_seconds"]["max"] == 6.0  # a, b: 0 -> push at 6 s; c: 29 -> 35 s
    assert out["github_to_receiver_seconds"]["max"] == 2.0
    assert out["receiver_to_push_seconds"]["max"] == 5.0  # c: received 30, pushed 35
    assert out["meets_target"] is True
