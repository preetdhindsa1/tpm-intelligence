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
