"""ReleaseService caching: cheap release listing and single-flight view computation.

Regression for 2026-11-21: ``GET /releases`` built a full view (projection, assessment and
Monte Carlo forecast) for every release, and concurrent requests each recomputed the same
view, so the dashboard home page hung for minutes on a cold cache.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.service import InMemoryEventSource, ReleaseService, ReleaseView
from api.validation import Validation
from engine.forecast import ForecastConfig
from tests.engine.conftest import fixture_events, utc

FAST = ForecastConfig(replications=5, sims=100)
AFTER_READD = utc(2026, 11, 21, 3)


def make_service(now: datetime = AFTER_READD) -> ReleaseService:
    return ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=FAST,
        now=lambda: now,
        validation=lambda: Validation(False, "test: not validated"),
    )


def test_release_list_runs_no_forecast(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()

    def no_compute(key: str) -> ReleaseView:
        raise AssertionError(f"/releases must not compute a full view ({key})")

    monkeypatch.setattr(service, "_compute", no_compute)
    [release] = TestClient(create_app(service=service)).get("/releases").json()
    assert release["name"] == "v1.38"
    assert release["code_freeze_at"] == "2026-11-17T12:00:00Z"


def test_release_list_counts_match_full_view() -> None:
    service = make_service()
    client = TestClient(create_app(service=service))
    [listed] = client.get("/releases").json()
    full = client.get("/releases/v1.38/features").json()["release"]
    assert listed == full  # #6395 and #2570: both re-added after Code Freeze
    assert listed["features_ever_in_release"] == 2


def test_release_list_is_cached_until_new_events() -> None:
    source = InMemoryEventSource(list(fixture_events()))
    held_back = source.events.pop()
    service = ReleaseService(source, forecast=FAST, now=lambda: AFTER_READD)
    first = service.releases()
    assert service.releases() is first
    source.events.append(held_back)
    assert service.releases() is not first


def test_concurrent_view_requests_compute_once(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    real_compute = service._compute
    calls: list[str] = []

    def slow_compute(key: str) -> ReleaseView:
        calls.append(key)
        time.sleep(0.2)  # long enough for the other threads to arrive while it runs
        return real_compute(key)

    monkeypatch.setattr(service, "_compute", slow_compute)
    results: list[ReleaseView] = []
    threads = [
        threading.Thread(target=lambda: results.append(service.view("v1.38"))) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls == ["kubernetes:v1.38"]
    assert len(results) == 4
    assert all(r is results[0] for r in results)
