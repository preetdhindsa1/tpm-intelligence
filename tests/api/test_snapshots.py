"""Forecast snapshots (api/snapshots.py, ADR-0015) on the real #6395 fixtures."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from api.service import InMemoryEventSource, ReleaseService
from api.snapshots import (
    FeatureSnapshot,
    MemorySnapshotStore,
    SnapshotRun,
    build_snapshot,
    pick,
    recorder,
    score_merge_dates,
    score_odds,
    worth_recording,
)
from api.validation import Validation
from engine.forecast import DEFAULT_FORECAST, ForecastConfig, model_version
from tests.engine.conftest import K6395, fixture_events, utc

FAST = ForecastConfig(replications=5, sims=100)
AFTER_READD = utc(2026, 11, 21, 3)


def service(store: MemorySnapshotStore, when: datetime = AFTER_READD) -> ReleaseService:
    return ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=FAST,
        now=lambda: when,
        validation=lambda: Validation(False, "test"),
        date_validation=lambda: Validation(False, "test"),
        on_computed=recorder(store, FAST),
    )


def test_a_computed_view_is_recorded_once_a_day() -> None:
    store = MemorySnapshotStore()
    svc = service(store)
    svc.view("v1.38")
    svc.invalidate()
    svc.view("v1.38")  # recomputed the same day: not stored again
    [run] = store.runs("kubernetes:v1.38")
    assert run.model_version == model_version(FAST)
    assert run.snapshot_date.isoformat() == "2026-11-21"
    f = next(x for x in run.features if x.feature_key == K6395)
    assert f.in_release
    assert f.odds_status == "after_freeze"
    assert run.body["config"]["durations"] == "main"
    assert run.body["merge_date_validation"]["validated"] is False


def test_model_version_changes_with_any_setting() -> None:
    assert model_version(DEFAULT_FORECAST) != model_version(ForecastConfig(durations="all"))
    assert model_version(FAST) != model_version(DEFAULT_FORECAST)
    assert model_version(DEFAULT_FORECAST).startswith("forecast-m7.1+")


def test_finished_releases_are_not_recorded() -> None:
    store = MemorySnapshotStore()
    svc = service(store, when=utc(2027, 2, 1))  # after release day + 14 days
    v = svc.view("v1.38")
    assert not worth_recording(build_snapshot(v, FAST))
    assert store.runs("kubernetes:v1.38") == []


def _run(features: list[FeatureSnapshot], base_rate: float = 0.7) -> SnapshotRun:
    return SnapshotRun(
        "kubernetes:v1.39",
        utc(2027, 2, 1).date(),
        utc(2027, 2, 1),
        "forecast-m7.1+x",
        utc(2027, 3, 1),
        utc(2027, 4, 1),
        {"recalibration": {"base_rate": base_rate}},
        tuple(features),
    )


def _f(key: str, p: float | None, *, cdf: list[list[float]] | None = None) -> FeatureSnapshot:
    return FeatureSnapshot(
        key,
        True,
        "forecast",
        p,
        p,
        p,
        p,
        "forecast" if cdf else "done",
        None,
        0.0 if cdf else None,
        1.0 if cdf else None,
        2.0 if cdf else None,
        None,
        None,
        cdf or [],
    )


def test_odds_scored_against_outcomes_and_the_recorded_base_rate() -> None:
    run = _run([_f("a", 0.9), _f("b", 0.2)])
    s = score_odds(run, {"a": True, "b": False}, 28)
    assert s.n == 2
    assert s.brier == round((0.1**2 + 0.2**2) / 2, 4)
    assert s.brier_baseline == round((0.3**2 + 0.7**2) / 2, 4)
    assert s.skill is not None
    assert s.skill > 0


def test_merge_dates_scored_for_coverage_and_crps() -> None:
    cdf = [[0, 0.1, 0.1, 0.1], [1, 0.5, 0.5, 0.5], [2, 0.9, 0.9, 0.9]]
    run = _run([_f("a", None, cdf=cdf), _f("b", None, cdf=cdf)])
    s = score_merge_dates(run, {"a": 1.0, "b": float("inf")}, [5.0, 6.0], 7)
    assert s.n == 2
    assert s.coverage == 0.5  # a is inside 0-2; b never merged
    assert s.crps is not None
    assert s.crps_baseline is not None


def test_pick_takes_the_snapshot_nearest_a_lead_time() -> None:
    freeze = utc(2027, 3, 1)
    runs = [replace(_run([]), as_of=freeze - timedelta(days=d)) for d in (29, 15, 6)]
    assert pick(runs, freeze, 28) is runs[0]
    assert pick(runs, freeze, 7) is runs[2]
    assert pick(runs, freeze, 50) is None  # nothing within 2 days
